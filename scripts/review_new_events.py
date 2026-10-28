"""Prepare and audit bounded new-occurrence reviews in a private staging directory.

This command never changes the checkout, pushes, dispatches, or sends mail.
The Mac reviewer supplies page-context evidence; staging re-fetches that context
and uses the existing apply_review transaction. Promotion is a separate gate.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from . import build_lp_events as builder
from . import event_identity_registry as ids
from .validate_external_events import validate_payload
from .venue_web_discovery_extract import extract_with_requests_bs4

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "NemuKei/market-stats-viewer"
WORKFLOW = ".github/workflows/update_signals_venue_web_discovery.yml"
OFFICIAL = {"venue_official", "artist_official", "promoter_official", "ticket_official"}
DAILY_LIMIT = 50
JST = ZoneInfo("Asia/Tokyo")
AUTO_REASON = "Mac official occurrence check:"


def stamp(value: str) -> datetime:
    ids.require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value), "UTC timestamp ending in Z required")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def write_json(path: Path, value: dict) -> None:
    ids.atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n", replace=False)


def observation_key(observation: dict) -> str:
    return ids.observation_identity_key(observation)


def ingestion_receipt(run: dict, *, now: str, ancestor, inbox_at_head: bytes, current_inbox: bytes) -> dict:
    """A clock tick is not evidence that the current inbox was ingested."""
    ids.require(run.get("repository", {}).get("full_name", "").lower() == REPOSITORY.lower(), "wrong ingestion repository")
    ids.require(run.get("path") == WORKFLOW and run.get("head_branch") == "main", "wrong ingestion workflow/branch")
    ids.require(run.get("status") == "completed" and run.get("conclusion") == "success", "ingestion has not succeeded")
    sha = run.get("head_sha", "")
    ids.require(isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{40}", sha) and ancestor(sha), "ingestion revision is not an ancestor")
    age = stamp(now) - stamp(run["updated_at"])
    ids.require(timedelta(0) <= age <= timedelta(hours=24), "ingestion receipt is stale or future dated")
    ids.require(inbox_at_head == current_inbox, "current inbox was not covered by this ingestion")
    return {"run_id": run["id"], "head_sha": sha, "completed_at_utc": run["updated_at"], "inbox_sha256": ids.digest(current_inbox)}


def read_ingestion(run_id: int, now: str) -> dict:
    ids.require(run_id > 0, "positive ingestion run ID required")
    run = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPOSITORY}/actions/runs/{run_id}"], text=True))
    sha = run.get("head_sha", "")
    ids.require(isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{40}", sha), "invalid ingestion SHA")
    inbox = "data/venue_discovery_inbox.json"
    return ingestion_receipt(run, now=now,
        ancestor=lambda ref: subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", ref, "HEAD"]).returncode == 0,
        inbox_at_head=subprocess.check_output(["git", "-C", str(ROOT), "show", f"{sha}:{inbox}"]),
        current_inbox=(ROOT / inbox).read_bytes())


def initial_state(payload: dict, registry: dict, *, now: str, source_sha: str) -> dict:
    _, held = ids.resolve_rows(payload["events"], registry)
    future = [h for h in held if h["identity"]["event_end_date"] >= payload["as_of_date"]]
    return {"schema_version": 1, "baseline_at_utc": now, "baseline_source_commit": source_sha,
        "mail_send_enabled": False, "mail_baseline_required": True,
        "observed": {observation_key(h): {"cohort": "backlog", "first_observed_at_utc": now} for h in future},
        "daily_new": {}, "batches": []}


def validate_state(state: dict, registry: dict) -> None:
    ids.require(set(state) == {"schema_version", "baseline_at_utc", "baseline_source_commit", "mail_send_enabled", "mail_baseline_required", "observed", "daily_new", "batches"}, "invalid review state schema")
    ids.require(state["schema_version"] == 1 and state["mail_send_enabled"] is False and state["mail_baseline_required"] is True, "mail boundary must remain closed")
    stamp(state["baseline_at_utc"])
    ids.require(re.fullmatch(r"[a-f0-9]{40}", state["baseline_source_commit"]), "invalid baseline commit")
    ids.require(isinstance(state["observed"], dict) and isinstance(state["daily_new"], dict) and isinstance(state["batches"], list), "invalid review state collections")
    for key, value in state["observed"].items():
        ids.require(ids.HASH.fullmatch(key) and set(value) == {"cohort", "first_observed_at_utc"} and value["cohort"] in {"backlog", "daily"}, "invalid cohort")
        stamp(value["first_observed_at_utc"])
    for day, keys in state["daily_new"].items():
        date.fromisoformat(day)
        ids.require(isinstance(keys, list) and keys == sorted(set(keys)) and all(key in state["observed"] for key in keys), "invalid daily discovery inventory")
    relations = {r["request_sha256"]: r for r in registry["relations"]}
    seen_ids, seen_requests, counts = set(), set(), {}
    for batch in state["batches"]:
        ids.require(set(batch) == {"day_jst", "staged_at_utc", "ingestion", "items"}, "invalid batch schema")
        date.fromisoformat(batch["day_jst"])
        ids.require(stamp(batch["staged_at_utc"]).astimezone(JST).date().isoformat() == batch["day_jst"], "batch day mismatch")
        ids.require(isinstance(batch["items"], list) and batch["items"], "empty committed batch")
        for item in batch["items"]:
            ids.require(set(item) == {"event_uid", "fingerprint", "observation_key", "cohort", "request_sha256"}, "invalid batch item")
            uid = item["event_uid"]
            ids.require(uid not in seen_ids and item["observation_key"] in state["observed"], "duplicate or unknown batch occurrence")
            seen_ids.add(uid)
            ids.require(item["cohort"] == state["observed"][item["observation_key"]]["cohort"], "cohort changed")
            relation = relations.get(item["request_sha256"])
            ids.require(relation and relation["kind"] == "new" and not relation["previous_ids"] and relation["next_ids"] == [uid] and relation["candidates"] == [{"event_uid": uid, "fingerprint": item["fingerprint"]}], "state does not match reviewed registry journal")
            seen_requests.add(item["request_sha256"])
        counts[batch["day_jst"]] = counts.get(batch["day_jst"], 0) + len(batch["items"])
    ids.require(all(count <= DAILY_LIMIT for count in counts.values()), "daily review quota exceeded")
    ids.require(seen_requests == {r["request_sha256"] for r in registry["relations"] if r["evidence"]["reason"].startswith(AUTO_REASON)}, "review state lost automated transactions; do not reinitialize the quota")


def duplicate_occurrence(identity: dict, other: dict) -> bool:
    if (identity["event_date"], identity["venue_name"]) != (other["event_date"], other["venue_name"]):
        return False
    artist = builder.normalize_key_part(identity["artist_name"])
    same_artist = bool(artist) and artist == builder.normalize_key_part(other["artist_name"])
    same_title = builder.supplemental_titles_match(identity["title"], other["title"])
    return (same_artist or same_title) and builder.start_times_compatible(identity["event_start_time"], other["event_start_time"])


def prepare(payload: dict, registry: dict, state: dict, *, now: str, cohort: str = "backlog", limit: int = DAILY_LIMIT,
            publishable_keys: set[str] | None = None, published_identities: list[dict] | None = None) -> dict:
    validate_payload(payload)
    ids.validate_registry(registry)
    validate_state(state, registry)
    ids.require(type(limit) is int and 1 <= limit <= DAILY_LIMIT and cohort in {"backlog", "daily"}, "invalid review limit/cohort")
    ids.require(stamp(now) >= stamp(state["baseline_at_utc"]), "review clock moved backwards")
    ids.require(payload["as_of_date"] == stamp(now).astimezone(JST).date().isoformat(), "candidate day must be current JST day")
    resolved, held = ids.resolve_rows(payload["events"], registry)
    future = [h for h in held if h["identity"]["event_end_date"] >= payload["as_of_date"]]
    rows = {row["event_key"]: row for row in payload["events"]}
    updated = deepcopy(state)
    day = stamp(now).astimezone(JST).date().isoformat()
    discovered = set(updated["daily_new"].get(day, []))
    for h in future:
        key = observation_key(h)
        if key not in updated["observed"]:
            # An old source newly entering the preview is still backlog. Missing
            # source timestamps are conservative; they must never become mail-new.
            first_seen = rows[h["candidate_key"]].get("first_seen_at_utc")
            try:
                is_daily = bool(first_seen) and stamp(first_seen) > stamp(state["baseline_at_utc"])
            except (ValueError, TypeError):
                is_daily = False
            updated["observed"][key] = {"cohort": "daily" if is_daily else "backlog", "first_observed_at_utc": now}
            discovered.add(key)
    updated["daily_new"][day] = sorted(discovered)
    previous = [len(keys) for d, keys in sorted(state["daily_new"].items()) if d < day][-7:]
    # Initial backlog is inventoried separately. A new daily population greater
    # than 50 or 3x the recent mean (whichever is larger) needs parser review.
    surge_limit = max(50, math.ceil(3 * sum(previous) / len(previous))) if previous else 50
    stops = []
    if len(discovered) > surge_limit:
        stops.append({"reason": "candidate_surge", "count": len(discovered), "threshold": surge_limit})
    scoped = [h for h in future if publishable_keys is None or h["candidate_key"] in publishable_keys]
    changed = [h for h in scoped if h["related_event_uids"] or h["reason"] not in {"unregistered_candidate", "superseded_observation"}]
    if changed:
        stops.append({"reason": "existing_identity_review_required", "fingerprints": [h["fingerprint"] for h in changed]})
    used = sum(len(b["items"]) for b in state["batches"] if b["day_jst"] == day)
    active = [o["identity"] for e in registry["events"] for o in e["observations"] if o["active"]]
    active.extend(published_identities or [])
    eligible, deferred = [], []
    for h in future:
        reason = None
        if publishable_keys is not None and h["candidate_key"] not in publishable_keys:
            reason = "consumer_policy_excluded"
        elif h["reason"] != "unregistered_candidate" or h["related_event_uids"]:
            reason = h["reason"]
        elif "record_kind" in h["identity"]:
            reason = "separate_schedule_day_lane"
        elif any(duplicate_occurrence(h["identity"], other) for other in active):
            reason = "possible_published_duplicate"
        elif updated["observed"][observation_key(h)]["cohort"] != cohort:
            reason = "other_cohort"
        if reason:
            deferred.append({"fingerprint": h["fingerprint"], "reason": reason})
        else:
            eligible.append(h)
    eligible.sort(key=lambda h: (h["identity"]["event_date"], h["identity"]["venue_name"], h["candidate_key"]))
    return {"schema_version": 1, "prepared_at_utc": now, "cohort": cohort, "day_jst": day,
        "limit": min(limit, DAILY_LIMIT - used), "daily_used": used, "stops": stops,
        "resolved_count": len(resolved), "future_held_count": len(future), "eligible": eligible,
        "deferred": deferred, "state": updated}


def safe_url(url: str, *, resolve: bool = False) -> str:
    ids.validate_evidence({"url": url, "reviewed_at_utc": "2026-01-01T00:00:00Z", "reason": "URL validation"})
    parts = urlsplit(url)
    ids.require(parts.scheme == "https" and parts.port in {None, 443}, "official evidence must use public HTTPS")
    if resolve:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        ids.require(addresses and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses), "official URL resolves to a non-public address")
    return url


def fetch_official(url: str):
    import requests

    class PublicSession(requests.Session):
        def __init__(self):
            super().__init__()
            self.trust_env = False

        def get(self, target, **kwargs):
            # Follow only validated same-host HTTPS redirects; no stored browser
            # login, proxy auth, new credentials, or optional paid provider.
            for _ in range(4):
                safe_url(target, resolve=True)
                response = super().get(target, allow_redirects=False, **kwargs)
                if not response.is_redirect:
                    return response
                from urllib.parse import urljoin
                following = urljoin(target, response.headers["Location"])
                ids.require(urlsplit(following).hostname == urlsplit(url).hostname, "cross-host redirect needs manual review")
                target = following
            raise ValueError("too many official redirects")

    with PublicSession() as session:
        return extract_with_requests_bs4(safe_url(url, resolve=True), session=session)


def verify_evidence(row: dict, held: dict, evidence: dict, *, now: str, fetch=fetch_official) -> dict:
    fields = {"fingerprint", "identity", "url", "source_class", "reviewed_at_utc", "context", "date_text", "venue_text", "artist_text", "time_text", "end_date_text"}
    ids.require(isinstance(evidence, dict) and set(evidence) == fields, "incomplete official evidence")
    ids.require(evidence["fingerprint"] == held["fingerprint"] and evidence["identity"] == held["identity"], "evidence observation mismatch")
    ids.require(evidence["source_class"] in OFFICIAL, "official source class required")
    sources = row["supporting_sources"]
    allowed = {s.get("evidence_url") or s.get("url") for s in sources if s.get("source_class") in OFFICIAL}
    ids.require(evidence["url"] in allowed, "evidence URL is not an official supporting source")
    safe_url(evidence["url"])
    ids.require(timedelta(0) <= stamp(now) - stamp(evidence["reviewed_at_utc"]) <= timedelta(hours=6), "official review expired or future dated")
    context = evidence["context"]
    ids.require(isinstance(context, str) and 0 < len(context) <= 2000, "short contiguous occurrence context required")
    for field in ("date_text", "venue_text", "artist_text"):
        ids.require(isinstance(evidence[field], str) and evidence[field].strip() and evidence[field] in context, f"missing {field} in occurrence context")
    ident = held["identity"]
    for field, identity_field in (("venue_text", "venue_name"), ("artist_text", "artist_name")):
        ids.require(builder.normalize_key_part(evidence[field]) == builder.normalize_key_part(ident[identity_field]), f"{field} does not match canonical identity; manual review required")
    def date_matches(value: str, quote: str) -> bool:
        d = date.fromisoformat(value)
        compact = re.sub(r"\s+", "", quote)
        return any(re.search(r"(?<!\d)" + re.escape(token) + r"(?!\d)", compact) for token in (value, f"{d.year}/{d.month}/{d.day}", f"{d.year}.{d.month}.{d.day}", f"{d.year}年{d.month}月{d.day}日", f"{d.year}/{d.month:02}/{d.day:02}", f"{d.year}.{d.month:02}.{d.day:02}"))
    ids.require(date_matches(ident["event_date"], evidence["date_text"]), "full official date required")
    if ident["event_end_date"] != ident["event_date"]:
        ids.require(isinstance(evidence["end_date_text"], str) and evidence["end_date_text"] in context and date_matches(ident["event_end_date"], evidence["end_date_text"]), "official end date required")
    if ident["event_start_time"]:
        marker = r"(?:開演|開始|START|キックオフ)\s*[】:：]?\s*" + re.escape(ident["event_start_time"][:5]) + r"(?!\d)"
        ids.require(isinstance(evidence["time_text"], str) and evidence["time_text"] in context and re.search(marker, evidence["time_text"], re.I), "explicit performance time required; OPEN alone is insufficient")
    page = fetch(evidence["url"])
    ids.require(page.success and page.status_code == 200 and context in page.text, "official context was not retrieved unchanged")
    return {"url": evidence["url"], "reviewed_at_utc": evidence["reviewed_at_utc"],
        "reason": AUTO_REASON + " date, venue, artist" + (", performance time" if ident["event_start_time"] else "") + "; context_sha256=" + ids.digest(context.encode())}


def assert_additive(before: dict, after: dict, before_rows: list[dict], after_rows: list[dict], new_ids: set[str]) -> None:
    ids.validate_registry(after)
    ids.require(after["events"][:len(before["events"])] == before["events"] and after["relations"][:len(before["relations"])] == before["relations"], "existing registry history changed")
    ids.require(len(after["events"]) - len(before["events"]) == len(new_ids), "unexpected identity allocation")
    extra = after["relations"][len(before["relations"]):]
    ids.require(len(extra) == len(new_ids) and all(r["kind"] == "new" and not r["previous_ids"] and not r.get("acknowledged_related_event_uids") for r in extra), "non-new identity transaction")
    old = {r["event_key"]: r for r in before_rows}
    current = {r["event_key"]: r for r in after_rows}
    ids.require(len(current) == len(after_rows) and set(current) - set(old) == new_ids and all(current.get(k) == v for k, v in old.items()), "publication must be strictly additive")


def check_plan_time(plan: dict, now: str) -> None:
    ids.require(timedelta(0) <= stamp(now) - stamp(plan["prepared_at_utc"]) <= timedelta(hours=1), "prepared review expired")
    ids.require(stamp(now).astimezone(JST).date().isoformat() == plan["day_jst"], "review crossed JST quota day; prepare again")


def stage(payload: dict, registry: dict, plan: dict, evidence: list[dict], *, now: str, fetch=fetch_official) -> dict:
    check_plan_time(plan, now)
    ids.require(isinstance(evidence, list), "evidence must be an array")
    by_fp = {}
    for value in evidence:
        ids.require(isinstance(value, dict) and value.get("fingerprint") not in by_fp, "duplicate evidence fingerprint")
        by_fp[value.get("fingerprint")] = value
    eligible = {h["fingerprint"] for h in plan["eligible"]}
    ids.require(set(by_fp) <= eligible, "evidence includes a non-new, related, duplicate, or other-cohort candidate")
    rows = {r["event_key"]: r for r in payload["events"]}
    working, state, items, held, requests = deepcopy(registry), deepcopy(plan["state"]), [], [], []
    accepted_identities = []
    for h in plan["eligible"]:
        fp = h["fingerprint"]
        if fp not in by_fp:
            held.append({"fingerprint": fp, "reason": "official_evidence_pending"})
            continue
        if len(items) >= plan["limit"]:
            held.append({"fingerprint": fp, "reason": "daily_limit_deferred"})
            continue
        if any(duplicate_occurrence(h["identity"], other) for other in accepted_identities):
            held.append({"fingerprint": fp, "reason": "possible_batch_duplicate"})
            continue
        try:
            checked = verify_evidence(rows[h["candidate_key"]], h, by_fp[fp], now=now, fetch=fetch)
        except Exception as exc:
            # Retrieval/ambiguity is individual hold, never source/DB correction.
            held.append({"fingerprint": fp, "reason": "official_evidence_unavailable", "error_type": type(exc).__name__,
                "detail": str(exc)[:200] if isinstance(exc, ValueError) else "official retrieval failed"})
            continue
        request = {"schema_version": 1, "kind": "new", "expected_revision": working["revision"], "previous_ids": [],
            "candidates": [{"event_uid": None, "observation": {k: h[k] for k in ("candidate_key", "identity", "source_records", "fingerprint")}}], "evidence": checked}
        working = ids.apply_review(working, request)
        ids.require(ids.apply_review(working, request) == working, "review replay allocated another ID")
        relation = working["relations"][-1]
        key = observation_key(h)
        items.append({"event_uid": relation["next_ids"][0], "fingerprint": fp, "observation_key": key, "cohort": state["observed"][key]["cohort"], "request_sha256": relation["request_sha256"]})
        requests.append(request)
        accepted_identities.append(h["identity"])
    if items:
        state["batches"].append({"day_jst": plan["day_jst"], "staged_at_utc": now, "ingestion": plan.get("ingestion"), "items": items})
    validate_state(state, working)
    before_rows, _ = ids.resolve_rows(payload["events"], registry)
    after_rows, _ = ids.resolve_rows(payload["events"], working)
    assert_additive(registry, working, before_rows, after_rows, {i["event_uid"] for i in items})
    # Serialization must agree with the digest referenced by the LP.
    registry_bytes = json.dumps(working, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    lp = ids.apply_to_payload(payload, working, ids.digest(registry_bytes))
    lp.pop("identity_held_records")
    validate_payload(lp)
    return {"registry": working, "lp": lp, "state": state, "requests": requests,
        "report": {"status": "stopped" if plan["stops"] else "staged", "stops": plan["stops"], "new_ids": [i["event_uid"] for i in items], "held": held,
            "daily_used_after": plan["daily_used"] + len(items), "promotion_requires_independent_review": True, "mail_send_enabled": False}}


CONSUMER_FILES = ("02_Service/web_lp/scripts/event_source_policy.py",
    "02_Service/web_lp/scripts/refresh_content_freshness.py",
    "02_Service/web_lp/scripts/verify_external_events_asset.py",
    "02_Service/web_lp/scripts/refresh_market_portal_data.py",
    "docs/operations/public-event-source-policy.json")


def consumer_files(consumer: Path) -> dict[str, str]:
    # Include transitive local helpers too: a fresh consumer can add imports
    # without changing the names of the four original entry points.
    paths = {str(p.relative_to(consumer)) for p in (consumer / "02_Service/web_lp/scripts").rglob("*.py")}
    paths.update(CONSUMER_FILES)
    paths.add("02_Service/web_lp/data/events.json")
    return {p: ids.digest((consumer / p).read_bytes()) for p in sorted(paths)}


def consumer_context(payload: dict, consumer: Path) -> tuple[set[str], list[dict]]:
    """Call the consumer's actual projection; do not copy its policy into MSV."""
    scripts = consumer / "02_Service/web_lp/scripts"
    # Run in a separate interpreter to avoid polluting MSV's import namespace.
    code = """import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from refresh_market_portal_data import export_lp_events
from event_source_policy import load_source_policy,project_public_events
from refresh_event_snapshot import validate_snapshot
p=pathlib.Path(sys.argv[2])
policy=load_source_policy(pathlib.Path(sys.argv[4]))
rows,_=project_public_events(export_lp_events(p.parent,sys.argv[3],p),policy)
snapshot=json.loads(pathlib.Path(sys.argv[5]).read_bytes())
validate_snapshot(snapshot,policy)
units=snapshot['events'].get('recordUnits',{})
ordinary=[r for r in snapshot['events']['items'] if units.get(r['event_uid'],'occurrence')=='occurrence']
print(json.dumps({'keys':[r['event_uid'] for r in rows],'published':ordinary}))
"""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "candidate.json"
        path.write_bytes(ids.canonical_bytes(payload))
        result = subprocess.check_output([sys.executable, "-c", code, str(scripts), str(path), payload["as_of_date"], str(consumer / CONSUMER_FILES[-1]), str(consumer / "02_Service/web_lp/data/events.json")], text=True)
    value = json.loads(result)
    return set(value["keys"]), [ids.identity_from_row(r, public=True) for r in value["published"]]


def input_pins(state_path: Path | None, consumer: Path | None = None) -> dict:
    paths = sorted(set(git("ls-files", "data", "scripts", ".github/workflows").splitlines()) | {"scripts/review_new_events.py"})
    pins = {p: ids.digest((ROOT / p).read_bytes()) for p in paths if (ROOT / p).is_file()}
    return {"source_commit": git("rev-parse", "HEAD"), "files": pins,
        "state_path": str(state_path.resolve()) if state_path else None,
        "state_sha256": ids.digest(state_path.read_bytes()) if state_path else None,
        "consumer_path": str(consumer.resolve()) if consumer else None,
        "consumer_commit": subprocess.check_output(["git", "-C", str(consumer), "rev-parse", "HEAD"], text=True).strip() if consumer else None,
        "consumer_files": consumer_files(consumer) if consumer else {}}


def verify_pins(pins: dict) -> None:
    ids.require(input_pins(Path(pins["state_path"]) if pins["state_path"] else None,
        Path(pins["consumer_path"]) if pins["consumer_path"] else None) == pins, "source/state/consumer changed; prepare from the new revision without rebasing staged IDs")


def private_directory(path: Path) -> None:
    ids.require(not path.resolve().is_relative_to(ROOT), "review files must remain outside the checkout")
    path.mkdir(mode=0o700, parents=True, exist_ok=False)


def read_prepared(directory: Path) -> tuple[dict, dict, dict]:
    plan = ids.parse_json((directory / "plan.json").read_bytes())
    verify_pins(plan["pins"])
    payload = ids.parse_json((directory / "candidates.json").read_bytes())
    registry = ids.parse_json((directory / "registry-before.json").read_bytes())
    current, _ = ids.load_registry()
    ids.require(registry == current, "private registry baseline changed")
    rebuilt = builder._build_lp_event_candidates(as_of_date=date.fromisoformat(payload["as_of_date"]))
    rebuilt["generated_at_utc"] = payload["generated_at_utc"]
    ids.require(rebuilt == payload, "private candidate baseline changed")
    original_state = ids.parse_json((directory / "state-before.json").read_bytes())
    expected_state = ids.parse_json(Path(plan["pins"]["state_path"]).read_bytes()) if plan["pins"]["state_path"] else initial_state(
        payload, registry, now=plan["prepared_at_utc"], source_sha=plan["pins"]["source_commit"])
    ids.require(original_state == expected_state, "private state baseline changed")
    consumer = Path(plan["pins"]["consumer_path"])
    scope, published = consumer_context(payload, consumer)
    expected = prepare(payload, registry, original_state, now=plan["prepared_at_utc"], cohort=plan["cohort"],
        limit=plan["requested_limit"], publishable_keys=scope, published_identities=published)
    ids.require(all(expected[k] == plan[k] for k in expected), "private selection/quota changed")
    return plan, payload, registry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--state", type=Path)
    p.add_argument("--initialize", action="store_true", help="Inventory backlog privately; persist the state separately before scheduled promotion.")
    p.add_argument("--ingestion-run-id", type=int, required=True)
    p.add_argument("--consumer-repo", type=Path, required=True)
    p.add_argument("--cohort", choices=["backlog", "daily"], default="daily")
    p.add_argument("--limit", type=int, default=DAILY_LIMIT)
    s = sub.add_parser("stage")
    s.add_argument("--prepared", type=Path, required=True)
    s.add_argument("--evidence", type=Path, required=True)
    a = sub.add_parser("audit")
    a.add_argument("--prepared", type=Path, required=True)
    args = parser.parse_args(argv)
    now = now_z()
    if args.command == "prepare":
        ids.require(bool(args.state) != args.initialize, "supply persisted --state OR explicit private --initialize")
        receipt = read_ingestion(args.ingestion_run_id, now)
        registry, _ = ids.load_registry()
        payload = builder._build_lp_event_candidates()
        state = ids.parse_json(args.state.read_bytes()) if args.state else initial_state(payload, registry, now=now, source_sha=git("rev-parse", "HEAD"))
        scope, published = consumer_context(payload, args.consumer_repo)
        plan = prepare(payload, registry, state, now=now, cohort=args.cohort, limit=args.limit,
            publishable_keys=scope, published_identities=published)
        plan.update(ingestion=receipt, pins=input_pins(args.state, args.consumer_repo), bootstrap=args.initialize, requested_limit=args.limit)
        private_directory(args.output)
        for name, value in {"plan.json": plan, "candidates.json": payload, "registry-before.json": registry, "state-before.json": state}.items():
            write_json(args.output / name, value)
        print(json.dumps({"eligible": len(plan["eligible"]), "limit": plan["limit"],
            "stops": [{"reason": s["reason"], "count": len(s["fingerprints"]) if "fingerprints" in s else s["count"]} for s in plan["stops"]], "bootstrap": args.initialize}))
    elif args.command == "stage":
        plan, payload, registry = read_prepared(args.prepared)
        result = stage(payload, registry, plan, json.loads(args.evidence.read_bytes()), now=now)
        target = args.prepared / "staged"
        private_directory(target)
        for name, value in {"event_identity_registry.json": result["registry"], "lp_events.json": result["lp"], "new_event_review_state.json": result["state"], "report.json": result["report"]}.items():
            write_json(target / name, value)
        write_json(target / "requests.json", {"requests": result["requests"]})
        report = result["report"]
        print(json.dumps({"status": report["status"], "new_count": len(report["new_ids"]),
            "held_counts": dict(Counter(h["reason"] for h in report["held"])), "daily_used_after": report["daily_used_after"], "mail_send_enabled": False}))
    else:
        plan, payload, before = read_prepared(args.prepared)
        root = args.prepared / "staged"
        after, after_sha = ids.load_registry(root / "event_identity_registry.json")
        state = ids.parse_json((root / "new_event_review_state.json").read_bytes())
        lp = ids.parse_json((root / "lp_events.json").read_bytes())
        report = ids.parse_json((root / "report.json").read_bytes())
        validate_state(state, after)
        new_ids = {e["event_uid"] for e in after["events"]} - {e["event_uid"] for e in before["events"]}
        before_rows, _ = ids.resolve_rows(payload["events"], before)
        assert_additive(before, after, before_rows, lp["events"], new_ids)
        expected = ids.apply_to_payload(payload, after, after_sha)
        expected.pop("identity_held_records")
        ids.require(expected == lp and new_ids == set(report["new_ids"]), "staged LP/report differs from independent rebuild")
        validate_payload(lp)
        ids.require(not plan["bootstrap"] and not plan["stops"] and report["status"] == "staged", "promotion stopped: bootstrap baseline or unresolved stop conditions")
        check_plan_time(plan, now)
        ids.require(read_ingestion(plan["ingestion"]["run_id"], now) == plan["ingestion"], "ingestion receipt changed")
        remote = git("ls-remote", "origin", "refs/heads/main").split()[0]
        ids.require(remote == plan["pins"]["source_commit"], "origin/main moved or review did not start from main; re-prepare without rebasing")
        ids.require(len(new_ids) <= plan["limit"], "staged quota exceeded")
        print(json.dumps({"audit": "passed", "new_count": len(new_ids), "mail_send_enabled": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

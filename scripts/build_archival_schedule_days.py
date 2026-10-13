"""Build reviewed preserved day-schedules without restoring DBs or guessing shows.

This explicit offline command has no scheduled workflow. It writes only a new
preview directory and a copied registry; originals and current public rows are
read-only. Day grouping is a presentation unit, never an occurrence merge.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from . import event_identity_registry as ids
from .events.types import JAPAN_PREFECTURES

CANDIDATE = "confident_additional_archival_schedule_candidate"
CANCEL = re.compile(r"中止|延期")
KIND = "schedule_day"


def normalized_title(title: str) -> str:
    # Preserve word boundaries, case, compatibility glyphs and punctuation.
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", title)).strip()


def candidate_title_key(title: str) -> str:
    # Retain keys already reviewed in this private preview. This is never the
    # grouping rule: distinct titles colliding here are refused below.
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", title)).casefold()


def public_url(value: object) -> str:
    ids.validate_evidence({"url": value, "reviewed_at_utc": "2026-01-01T00:00:00Z", "reason": "URL validation only"})
    return str(value)


def observed_timestamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    ids.require(stamp.utcoffset() is not None, "observation timestamp must include a timezone")
    return stamp.astimezone(timezone.utc)


def utc_order(value: str) -> tuple[datetime, str]:
    require_utc(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")), value


def build_candidates(inventory: list[dict], raw: list[dict], baseline: dict) -> tuple[list[dict], dict, dict]:
    current = baseline["events"]["items"]
    ids.require(current and len({r["event_uid"] for r in current}) == len(current), "invalid current baseline")
    cutoff = min(r["start_date"] for r in current)
    buckets = defaultdict(list)
    seen_refs, case_refs = set(), set()
    for case in inventory:
        ids.require(case["case_ref"] not in case_refs, "duplicate case reference")
        case_refs.add(case["case_ref"])
        for ref in case["observation_refs"]:
            ids.require(ref not in seen_refs, "observation belongs to multiple cases")
            seen_refs.add(ref)
        if case["classification"] != CANDIDATE:
            continue
        r = case["proposed_schedule_fact"]
        ids.require(not case["reasons"] and not case["cancellation_evidence"], "unresolved candidate")
        day = r["start_date"]
        ids.require(date.fromisoformat(day).isoformat() == day and day < cutoff, "candidate overlaps current baseline or has invalid date")
        ids.require((r.get("end_date") or day) == day, "aggregate is not a reviewed day schedule")
        ids.require(r["pref_name"] in JAPAN_PREFECTURES and r["title"] and r["venue_id"], "missing day facts")
        ids.require(not CANCEL.search(r["title"]) and r["status"] == "scheduled", "suppressed schedule")
        public_url(r["source_url"])
        original_sources, original_titles = set(), set()
        for ref in case["observation_refs"]:
            index = int(ref.removeprefix("observation-"))
            ids.require(ref == f"observation-{index:04d}" and 0 <= index < len(raw), "invalid observation reference")
            original = raw[index]
            original_sources.add(original["source_uid"])
            for version in original["raw_observations"]:
                v = version["record"]
                observed_timestamp(version["observed_at"])
                require_utc(v["first_seen_at_utc"])
                require_utc(v["updated_at_utc"])
                original_titles.add(normalized_title(v["title"]))
                ids.require(v["venue_id"] == r["venue_id"] and v["start_date"] == day and (v.get("end_date") or day) == day, "original date/venue differs")
                ids.require(v.get("status") == "scheduled" and not CANCEL.search(v["title"]), "original cancellation or postponement")
                ids.require(urlsplit(v["source_url"]).hostname == urlsplit(r["source_url"]).hostname, "original official calendar scope differs")
        ids.require(set(case["source_uids"]) == original_sources and len(case["source_uids"]) == len(original_sources), "source UID set differs from original")
        ids.require(normalized_title(r["title"]) in original_titles, "proposed title differs from original")
        buckets[(r["venue_id"], day, normalized_title(r["title"]))].append(case)
    ids.require(seen_refs == {f"observation-{i:04d}" for i in range(len(raw))}, "original observations missing from inventory")
    rows, metadata, private_groups = [], {}, []
    for (venue_id, day, title), cases in sorted(buckets.items()):
        facts = [c["proposed_schedule_fact"] for c in cases]
        venues = {c["proposed_canonical_venue"] for c in cases}
        prefs = {r["pref_name"] for r in facts}
        ids.require(len(venues) == len(prefs) == 1 and next(iter(venues)), "conflicting day venue")
        key = "schedule_day:" + ids.digest(ids.canonical_bytes([venue_id, day, candidate_title_key(title)]))
        ids.require(key not in metadata, "distinct program titles collide in reviewed candidate key; explicit review required")
        originals = [v for c in cases for ref in c["observation_refs"] for v in raw[int(ref.removeprefix("observation-"))]["raw_observations"]]
        times = sorted({v["record"]["start_time"] for v in originals if v["record"].get("start_time")})
        # Validate recorded times without pretending they are confirmed show times.
        for time in times:
            ids.identity_from_row({"event_date": day, "event_end_date": day, "event_start_time": time, "venue_name": next(iter(venues)), "title": facts[0]["title"]})
        sources = sorted({c_uid for c in cases for c_uid in c["source_uids"]})
        calendar = min(r["source_url"] for r in facts)
        updated = max((v["record"]["updated_at_utc"] for v in originals), key=utc_order)
        row = {"event_key": key, "record_kind": KIND, "event_date": day, "event_end_date": day,
            "event_start_time": "", "event_end_time": "", "venue_name": next(iter(venues)),
            "raw_venue_name": min(r["venue_name"] for r in facts), "artist_name": "", "raw_artist_name": "",
            "title": min(r["title"] for r in facts), "pref_name": next(iter(prefs)), "event_category": "未分類",
            "url": calendar, "evidence_url": calendar, "evidence_snippet": "", "capacity": None,
            "display_source_id": "official_events", "display_source_label": "会場公式（保存日程）",
            "display_source_class": "venue_official", "first_seen_at_utc": min((v["record"]["first_seen_at_utc"] for v in originals), key=utc_order),
            "updated_at_utc": updated, "supporting_sources": [{"source_id": "official_events", "record_id": uid, "url": calendar, "evidence_url": calendar, "updated_at_utc": updated} for uid in sources]}
        ids.observation_from_row(row)
        rows.append(row)
        metadata[key] = {"kind": KIND, "observedTimes": times,
            "hasUnknownTime": any(not v["record"].get("start_time") for v in originals),
            "performanceCount": None, "occurrenceCompleted": "unverified",
            "evidenceBasis": "preserved_official_schedule", "urlGranularity": "calendar",
            "lastObservedAtUtc": max(observed_timestamp(v["observed_at"]) for v in originals).isoformat(),
            "observedTitles": sorted({v["record"]["title"] for v in originals}),
            "venueNotes": sorted({"原本の会場区分: " + match.group(1).strip() for v in originals for match in re.finditer(r"会場タイプ[:：]\s*([^\r\n]+)", v["record"].get("description") or "")}),
            "historicalVenueNames": sorted({v["record"]["venue_name"] for v in originals})}
        private_groups.append({"candidate_key": key, "case_refs": sorted(c["case_ref"] for c in cases),
            "observation_refs": sorted(ref for c in cases for ref in c["observation_refs"]),
            "sources": sources, "original_observations": originals})
    counts = Counter(c["classification"] for c in inventory)
    return rows, metadata, {"classification_counts": dict(counts), "day_display_group_count": len(rows),
        "retained_candidate_case_count": counts[CANDIDATE], "private_groups": private_groups,
        "unit": "same physical venue, day and exactly normalized program title; not a performance count"}


def require_utc(value: object) -> None:
    ids.require(isinstance(value, str), "invalid UTC timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    ids.require(stamp.utcoffset() == timedelta(0), "timestamp must be UTC")


def validate_asset(payload: dict, registry: dict, registry_sha256: str) -> None:
    ids.require(set(payload) == {"schema_version", "dataset", "generated_at_utc", "baseline_sha256", "input_sha256", "identity_registry", "events", "schedule_metadata"}, "invalid day asset schema")
    ids.require(payload["schema_version"] == 1 and payload["dataset"] == "preserved_schedule_days", "invalid day asset type")
    ids.validate_registry(registry)
    ids.require(payload["identity_registry"] == {"schema_version": registry["schema_version"], "revision": registry["revision"], "sha256": registry_sha256}, "day registry metadata differs")
    ids.require(isinstance(registry_sha256, str) and ids.HASH.fullmatch(registry_sha256), "invalid registry digest")
    ids.require(isinstance(payload["baseline_sha256"], str) and ids.HASH.fullmatch(payload["baseline_sha256"]), "invalid baseline digest")
    ids.require(isinstance(payload["input_sha256"], dict) and set(payload["input_sha256"]) == {"inventory", "raw_observations"} and all(isinstance(v, str) and ids.HASH.fullmatch(v) for v in payload["input_sha256"].values()), "invalid input digests")
    require_utc(payload["generated_at_utc"])
    rows, metadata = payload["events"], payload["schedule_metadata"]
    ids.validate_resolved_rows(rows, registry)
    ids.require(len({r["event_key"] for r in rows}) == len(rows) and set(metadata) == {r["event_key"] for r in rows}, "missing/duplicate day metadata")
    for row in rows:
        ids.require(row.get("record_kind") == KIND and row["event_start_time"] == "", "not a day identity")
        m = metadata[row["event_key"]]
        ids.require(isinstance(m, dict) and set(m) == {"kind", "observedTimes", "hasUnknownTime", "performanceCount", "occurrenceCompleted", "evidenceBasis", "urlGranularity", "lastObservedAtUtc", "historicalVenueNames", "observedTitles", "venueNotes"}, "invalid day metadata fields")
        ids.require(m["kind"] == KIND and m["performanceCount"] is None and m["occurrenceCompleted"] == "unverified", "unconfirmed performance claim")
        times = m["observedTimes"]
        ids.require(isinstance(times, list) and all(isinstance(t, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", t) for t in times) and times == sorted(set(times)), "invalid observed times")
        ids.require(type(m["hasUnknownTime"]) is bool and (times or m["hasUnknownTime"]), "unknown time must be explicit")
        ids.require(m["evidenceBasis"] == "preserved_official_schedule" and m["urlGranularity"] == "calendar", "invalid day evidence basis")
        names = m["historicalVenueNames"]
        ids.require(isinstance(names, list) and names and all(isinstance(n, str) and n.strip() for n in names), "missing historical venue names")
        for field in ["observedTitles", "venueNotes"]:
            values = m[field]
            ids.require(isinstance(values, list) and (values or field == "venueNotes") and all(isinstance(v, str) and v.strip() for v in values) and values == sorted(set(values)), "invalid original title/venue note")
        ids.require(row["title"] in m["observedTitles"], "representative title must be an original observation")
        require_utc(m["lastObservedAtUtc"])
        public_url(row["url"])


def validate_preview_paths(root: Path, output_dir: Path, inputs: list[Path]) -> None:
    root, output_dir = root.absolute(), output_dir.absolute()
    ids.require(".." not in root.parts and ".." not in output_dir.parts, "preview paths must not contain parent traversal")
    ids.require(root.is_dir() and not root.is_symlink() and not any((ancestor / ".git").exists() for ancestor in [root, *root.parents]), "isolated non-repository preview root required")
    ids.require(output_dir == root / "private-data", "output must be isolated preview/private-data")
    outputs = [output_dir / name for name in ["preview-identity-registry.json", "lp_schedule_days.json", "private-plan.json", "reviewed-day-request.json"]]
    for path in [root, output_dir, *inputs, *outputs]:
        ids.require(not any(p.is_symlink() for p in [path, *path.parents]), "preview paths must not contain symlinks")
    for path in inputs:
        ids.require(path.is_file(), "input must be a regular file")
    for path in outputs:
        ids.require(not path.exists() or path.is_file(), "output must be a regular file")
        ids.require(all(path.resolve() != source.resolve() and not (path.exists() and path.samefile(source)) for source in inputs), "preview output collides with input")
    ids.require(not output_dir.exists() or output_dir.is_dir(), "private output must be a directory")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--expected-inventory-sha256", required=True)
    p.add_argument("--raw-observations", type=Path, required=True)
    p.add_argument("--expected-raw-sha256", required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--base-registry", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--preview-root", type=Path, required=True)
    p.add_argument("--review-evidence", type=Path, required=True)
    args = p.parse_args()
    validate_preview_paths(args.preview_root, args.output_dir, [args.inventory, args.raw_observations, args.baseline, args.base_registry, args.review_evidence])
    raw_bytes, inv_bytes, baseline_bytes = args.raw_observations.read_bytes(), args.inventory.read_bytes(), args.baseline.read_bytes()
    ids.require(ids.digest(raw_bytes) == args.expected_raw_sha256 and ids.digest(inv_bytes) == args.expected_inventory_sha256, "reviewed input hash changed")
    rows, metadata, plan = build_candidates(json.loads(inv_bytes), json.loads(raw_bytes), json.loads(baseline_bytes))
    original_registry, original_sha = ids.load_registry(args.base_registry)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "preview-identity-registry.json"
    ids.require(target.resolve() != args.base_registry.resolve(), "preview registry must be separate")
    registry, expected = ids.load_registry(target) if target.exists() else (deepcopy(original_registry), None)
    bound, held = ids.resolve_rows(rows, registry)
    plan["formal_unregistered_candidate_count_before_review"] = len(held)
    request = None
    if held:
        ids.require(not target.exists(), "changed preview candidates need a new explicit review")
        evidence = json.loads(args.review_evidence.read_text())
        request = {"schema_version": 2, "expected_revision": registry["revision"], "kind": "new", "previous_ids": [],
            "candidates": [{"event_uid": None, "observation": {k: h[k] for k in ["candidate_key", "identity", "source_records", "fingerprint"]}} for h in held], "evidence": evidence}
        registry = ids.apply_review(registry, request)
        bound, held = ids.resolve_rows(rows, registry)
    ids.require(not held and len(bound) == len(rows), "unresolved day identities")
    ids.require(registry["events"][:len(original_registry["events"])] == original_registry["events"], "existing registry entries changed")
    registry_sha = expected or ids.digest(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n")
    id_by_key = {o["candidate_key"]: e["event_uid"] for e in registry["events"] for o in e["observations"] if o["active"]}
    public_meta = {id_by_key[row["event_key"]]: metadata[row["event_key"]] for row in rows}
    asset = {"schema_version": 1, "dataset": "preserved_schedule_days", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_sha256": ids.digest(baseline_bytes), "input_sha256": {"inventory": ids.digest(inv_bytes), "raw_observations": ids.digest(raw_bytes)},
        "identity_registry": {"schema_version": registry["schema_version"], "revision": registry["revision"], "sha256": registry_sha},
        "events": bound, "schedule_metadata": public_meta}
    validate_asset(asset, registry, registry_sha)
    plan.update(base_registry_sha256=original_sha, preview_registry_sha256=registry_sha,
        formal_resolved_count=len(bound), existing_public_rows_unchanged=True, original_or_production_writes=False)
    asset_path, plan_path = args.output_dir / "lp_schedule_days.json", args.output_dir / "private-plan.json"
    if asset_path.exists() or plan_path.exists():
        ids.require(asset_path.is_file() and plan_path.is_file() and target.is_file(), "reviewed preview outputs differ; use a new explicit preview")
        old_asset, old_plan = ids.parse_json(asset_path.read_bytes()), ids.parse_json(plan_path.read_bytes())
        validate_asset(old_asset, registry, registry_sha)
        asset["generated_at_utc"] = old_asset["generated_at_utc"]
        initial_count = old_plan.get("formal_unregistered_candidate_count_before_review")
        ids.require(type(initial_count) is int and 0 <= initial_count <= len(bound), "invalid initial preview review count")
        plan["formal_unregistered_candidate_count_before_review"] = initial_count
        ids.require(old_asset == asset and old_plan == plan, "reviewed preview outputs differ; use a new explicit preview")
        print(f"preview day schedules={len(bound)}; reviewed bytes retained; no production writes")
        return 0
    if request is not None:
        ids.atomic_write(args.output_dir / "reviewed-day-request.json", json.dumps(request, ensure_ascii=False, indent=2).encode()+b"\n", replace=False)
    if expected is None:
        ids.write_registry(registry, target, expected_sha256=None)
    ids.require(ids.load_registry(target)[1] == registry_sha, "preview registry serialization changed")
    for name, value in [("lp_schedule_days.json", asset), ("private-plan.json", plan)]:
        ids.atomic_write(args.output_dir/name, json.dumps(value, ensure_ascii=False, indent=2).encode()+b"\n", replace=False)
    print(f"preview day schedules={len(bound)}; original candidate cases={plan['retained_candidate_case_count']}; no production writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reviewed, file-backed LP identity; no network or automatic alias guesses.

An observation fingerprint identifies one *unchanged* candidate, not a permanent
event. Permanent IDs are allocated once and changed observations require a
reviewed transaction. Archived observations and IDs are never deleted/reused.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import ipaddress
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data/event_identity_registry.json"
MAX_REGISTRY_BYTES = 16_000_000
IDENTITY_FIELDS = ("event_date", "event_end_date", "event_start_time", "venue_name", "artist_name", "title")
HASH = re.compile(r"[a-f0-9]{64}")
SOURCES = {"official_events", "venue_web_discovery", "starto_concert", "kstyle_music"}
# The approved SideBiz published baseline limits this display field to 128
# characters. Bootstrap may match that exact truncation only within the same
# legacy event key and hash/timestamp-pinned LP. It is never a correction alias.
PUBLISHED_SOURCE_RECORD_ID_LIMIT = 128


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for name, value in pairs:
        require(name not in result, "duplicate JSON key")
        result[name] = value
    return result


def parse_json(data: bytes) -> dict:
    require(len(data) <= MAX_REGISTRY_BYTES, "JSON exceeds byte limit")
    result = json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                        parse_constant=lambda _: require(False, "non-finite JSON number"))
    require(isinstance(result, dict), "JSON root must be an object")
    return result


def identifier(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 1_000 and value == value.strip() and not re.search(r"[\x00-\x1f\x7f]", value)


def identity_from_row(row: dict, *, public: bool = False) -> dict:
    require(isinstance(row, dict), "candidate must be an object")
    mapping = {"event_date": "start_date", "event_end_date": "end_date", "event_start_time": "start_time"} if public else {}
    result = {}
    for field in IDENTITY_FIELDS:
        value = row.get(mapping.get(field, field))
        require(value is None or isinstance(value, str), "invalid identity field type")
        result[field] = (value or "").strip()
    result["event_end_date"] = result["event_end_date"] or result["event_date"]
    require(result["title"] and result["venue_name"], "missing occurrence identity fields")
    for field in ["event_date", "event_end_date"]:
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", result[field]), "invalid occurrence date")
        date.fromisoformat(result[field])
    require(result["event_end_date"] >= result["event_date"], "invalid occurrence interval")
    require(not result["event_start_time"] or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", result["event_start_time"]), "invalid occurrence time")
    return result


def source_records_from_row(row: dict, *, public: bool = False) -> list[dict]:
    members = [{"source_id": row.get("source_id"), "record_id": row.get("source_record_id")}] if public else row.get("supporting_sources")
    require(isinstance(members, list) and members, "missing candidate source records")
    pairs = set()
    for member in members:
        require(isinstance(member, dict) and member.get("source_id") in SOURCES and identifier(member.get("record_id")), "invalid candidate source record")
        pairs.add((member["source_id"], member["record_id"]))
    return [{"source_id": source, "record_id": record} for source, record in sorted(pairs)]


def fingerprint(candidate_key: str, identity: dict, source_records: list[dict]) -> str:
    return digest(canonical_bytes({"candidate_key": candidate_key, "identity": identity, "source_records": source_records}))


def observation_identity_key(observation: dict) -> str:
    return digest(canonical_bytes({"candidate_key": observation["candidate_key"], "identity": observation["identity"]}))


def observation_from_row(row: dict, *, public: bool = False) -> dict:
    key = row.get("event_uid" if public else "event_key")
    require(identifier(key), "missing candidate key")
    identity = identity_from_row(row, public=public)
    sources = source_records_from_row(row, public=public)
    return {"candidate_key": key, "identity": identity, "source_records": sources, "fingerprint": fingerprint(key, identity, sources)}


def validate_observation(observation: dict, *, stored: bool = False) -> None:
    fields = {"candidate_key", "identity", "source_records", "fingerprint"}
    require(isinstance(observation, dict) and set(observation) == (fields | {"active", "evidence"} if stored else fields), "invalid observation schema")
    require(identifier(observation["candidate_key"]), "invalid candidate key")
    require(isinstance(observation["identity"], dict) and set(observation["identity"]) == set(IDENTITY_FIELDS), "invalid identity schema")
    require(identity_from_row(observation["identity"]) == observation["identity"], "noncanonical identity")
    pairs = source_records_from_row({"supporting_sources": observation["source_records"]})
    require(pairs == observation["source_records"], "noncanonical source records")
    require(observation["fingerprint"] == fingerprint(observation["candidate_key"], observation["identity"], observation["source_records"]), "observation fingerprint mismatch")
    if stored:
        require(type(observation["active"]) is bool, "invalid observation activity")


def validate_evidence(evidence: dict) -> None:
    require(isinstance(evidence, dict) and set(evidence) == {"url", "reviewed_at_utc", "reason"}, "review evidence required")
    require(isinstance(evidence["url"], str), "invalid review URL")
    url = urlsplit(evidence["url"])
    require(url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password, "review URL must be public HTTP(S) without credentials")
    host = url.hostname.lower().rstrip(".")
    require(host != "localhost" and not host.endswith((".localhost", ".local")), "review URL must not be local")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        require(address.is_global, "review URL must not be a private or reserved IP")
    require(isinstance(evidence["reviewed_at_utc"], str), "review timestamp must be UTC")
    stamp = datetime.fromisoformat(evidence["reviewed_at_utc"].replace("Z", "+00:00"))
    require(stamp.utcoffset() == timedelta(0), "review timestamp must be UTC")
    require(isinstance(evidence["reason"], str) and 0 < len(evidence["reason"].strip()) <= 2_000, "review reason required")


def validate_registry(registry: dict) -> None:
    require(isinstance(registry, dict) and set(registry) == {"schema_version", "revision", "seed_snapshot_sha256", "seed_lp_sha256", "seed_event_count", "seed_ids_sha256", "seed_observations_sha256", "events", "relations"}, "invalid registry schema")
    require(type(registry["schema_version"]) is int and registry["schema_version"] == 1, "unsupported registry schema")
    require(type(registry["revision"]) is int and registry["revision"] >= 1, "invalid registry revision")
    require(isinstance(registry["seed_snapshot_sha256"], str) and HASH.fullmatch(registry["seed_snapshot_sha256"]), "invalid seed digest")
    require(registry["seed_lp_sha256"] is None or isinstance(registry["seed_lp_sha256"], str) and HASH.fullmatch(registry["seed_lp_sha256"]), "invalid seed LP digest")
    require(type(registry["seed_event_count"]) is int and registry["seed_event_count"] >= 1, "invalid seed count")
    require(isinstance(registry["events"], list) and len(registry["events"]) >= registry["seed_event_count"], "registry lost seed IDs")
    ids, active, observations = set(), {}, {}
    seed_ids = set()
    seed_observations = []
    for event in registry["events"]:
        require(isinstance(event, dict) and set(event) == {"event_uid", "observations"} and identifier(event["event_uid"]) and event["event_uid"] not in ids, "invalid or duplicate fixed ID")
        uid = event["event_uid"]
        ids.add(uid)
        require(isinstance(event["observations"], list) and event["observations"], "missing event observations")
        require(sum(obs.get("active") is True for obs in event["observations"] if isinstance(obs, dict)) <= 1, "multiple active occurrences for fixed ID")
        seen = set()
        for obs in event["observations"]:
            validate_observation(obs, stored=True)
            require(obs["fingerprint"] not in seen, "duplicate observation in event")
            seen.add(obs["fingerprint"])
            evidence = obs["evidence"]
            if evidence == {"published_seed_sha256": registry["seed_snapshot_sha256"]}:
                seed_ids.add(uid)
                seed_observations.append([uid, obs["fingerprint"]])
            else:
                validate_evidence(evidence)
            observations[(uid, obs["fingerprint"])] = obs
            if obs["active"]:
                key = observation_identity_key(obs)
                require(key not in active, "ambiguous active observation IDs")
                active[key] = uid
    require(len(seed_ids) == registry["seed_event_count"], "registry lost seed observations")
    require(registry["seed_ids_sha256"] == digest(canonical_bytes(sorted(seed_ids))), "registry changed seed IDs")
    require(len(seed_observations) == registry["seed_event_count"] and registry["seed_observations_sha256"] == digest(canonical_bytes(sorted(seed_observations))), "registry changed seed observations")
    require(isinstance(registry["relations"], list) and registry["revision"] == len(registry["relations"]) + 1, "registry revision/history mismatch")
    transactions = set()
    reviewed = set()
    expected_active = {uid: fp for uid, fp in seed_observations}
    for relation in registry["relations"]:
        fields = {"kind", "previous_ids", "next_ids", "candidates", "evidence", "request_sha256"}
        require(isinstance(relation, dict) and set(relation) in (fields, fields | {"acknowledged_related_event_uids"}), "invalid relation schema")
        require(isinstance(relation["request_sha256"], str) and HASH.fullmatch(relation["request_sha256"]) and relation["request_sha256"] not in transactions, "invalid or duplicate transaction")
        transactions.add(relation["request_sha256"])
        validate_evidence(relation["evidence"])
        previous, following = relation["previous_ids"], relation["next_ids"]
        require(isinstance(previous, list) and isinstance(following, list) and len(set(previous)) == len(previous) and len(set(following)) == len(following) and set(previous + following) <= ids, "invalid relation IDs")
        kind = relation["kind"]
        acknowledged = relation.get("acknowledged_related_event_uids", [])
        require(isinstance(acknowledged, list) and all(identifier(uid) for uid in acknowledged)
                and acknowledged == sorted(set(acknowledged)) and set(acknowledged) <= set(expected_active)
                and (kind == "new" or not acknowledged), "invalid relation acknowledgement")
        require((kind == "new" and not previous and len(following) >= 1) or (kind == "correction" and len(previous) == len(following) == 1 and previous == following) or (kind == "split" and len(previous) == 1 and len(following) >= 2) or (kind == "merge" and len(previous) >= 2 and len(following) == 1), "invalid relation cardinality")
        require(all(expected_active.get(uid) is not None for uid in previous), "relation reuses a retired or unknown ID")
        require(all(uid not in expected_active or uid in previous for uid in following), "relation reuses an unrelated ID")
        for uid in previous:
            expected_active[uid] = None
        require(isinstance(relation["candidates"], list) and len(relation["candidates"]) == len(following), "invalid relation candidates")
        require({candidate.get("event_uid") for candidate in relation["candidates"] if isinstance(candidate, dict)} == set(following), "relation candidate IDs mismatch")
        for candidate in relation["candidates"]:
            require(set(candidate) == {"event_uid", "fingerprint"} and (candidate["event_uid"], candidate["fingerprint"]) in observations, "relation refers to missing observation")
            reviewed.add((candidate["event_uid"], candidate["fingerprint"], canonical_bytes(relation["evidence"])))
            expected_active[candidate["event_uid"]] = candidate["fingerprint"]
    for (uid, fp), obs in observations.items():
        require(obs["active"] == (expected_active.get(uid) == fp), "observation activity does not match reviewed history")
        if obs["evidence"] != {"published_seed_sha256": registry["seed_snapshot_sha256"]}:
            require((uid, fp, canonical_bytes(obs["evidence"])) in reviewed, "observation has no reviewed transaction")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> tuple[dict, str]:
    require(not path.is_symlink(), "registry must not be a symlink")
    data = path.read_bytes()
    registry = parse_json(data)
    validate_registry(registry)
    return registry, digest(data)


def seed_registry(snapshot_bytes: bytes, *, expected_sha256: str, expected_count: int,
                  lp_baseline_bytes: bytes | None = None, expected_lp_sha256: str | None = None) -> dict:
    require(digest(snapshot_bytes) == expected_sha256, "seed snapshot digest mismatch")
    # The original published envelope also contains unrelated market data;
    # retain only occurrence identity and already-public source record IDs.
    snapshot = json.loads(snapshot_bytes.decode("utf-8"), object_pairs_hook=_object)
    events = snapshot.get("events")
    require(isinstance(events, dict), "seed must be a published events snapshot")
    rows, policy = events.get("items"), events.get("publicationPolicy")
    require(isinstance(rows, list) and type(expected_count) is int and len(rows) == expected_count and expected_count > 0, "seed count mismatch")
    require(isinstance(policy, dict) and policy.get("status") == "enforced" and policy.get("defaultDeny") is True and type(policy.get("publishedCount")) is int and policy["publishedCount"] == len(rows), "seed publication policy required")
    baseline = None
    if lp_baseline_bytes is not None:
        require(isinstance(expected_lp_sha256, str) and digest(lp_baseline_bytes) == expected_lp_sha256, "seed LP digest mismatch")
        baseline = parse_json(lp_baseline_bytes)
        require(type(baseline.get("schema_version")) is int and baseline["schema_version"] == 1 and isinstance(baseline.get("events"), list), "invalid seed LP schema")
        metadata = snapshot.get("metadata")
        require(isinstance(metadata, dict) and baseline.get("as_of_date") == metadata.get("asOfDate"), "seed LP basis mismatch")
        source_time, published_time = baseline.get("generated_at_utc"), metadata.get("eventSourceGeneratedAtUtc")
        require(isinstance(source_time, str) and isinstance(published_time, str), "seed LP generation required")
        source_stamp = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
        published_stamp = datetime.fromisoformat(published_time.replace("Z", "+00:00"))
        require(source_stamp.utcoffset() == published_stamp.utcoffset() == timedelta(0) and source_stamp == published_stamp, "seed LP generation mismatch")
        source_rows = {}
        for candidate in baseline["events"]:
            require(isinstance(candidate, dict) and identifier(candidate.get("event_key")) and candidate["event_key"] not in source_rows, "duplicate or invalid seed LP key")
            source_rows[candidate["event_key"]] = candidate
    else:
        require(expected_lp_sha256 is None, "seed LP bytes required")
    result = {"schema_version": 1, "revision": 1, "seed_snapshot_sha256": expected_sha256, "seed_lp_sha256": expected_lp_sha256, "seed_event_count": len(rows), "seed_ids_sha256": digest(canonical_bytes(sorted(row["event_uid"] for row in rows))), "seed_observations_sha256": "", "events": [], "relations": []}
    for row in rows:
        require(row.get("source_policy_status") in {"approved", "conditional"}, "unpublished seed row")
        obs = observation_from_row(row, public=True)
        if baseline is not None:
            require(row["event_uid"] in source_rows, "published ID missing from seed LP")
            original = observation_from_row(source_rows[row["event_uid"]])
            for source in obs["source_records"]:
                matching = [item for item in original["source_records"] if item["source_id"] == source["source_id"] and (item["record_id"] == source["record_id"] or len(source["record_id"]) == PUBLISHED_SOURCE_RECORD_ID_LIMIT and item["record_id"].startswith(source["record_id"]))]
                require(len(matching) == 1, "published source record missing or ambiguous in seed LP")
            obs = original  # Existing projection can alter display text; identity belongs to the source occurrence.
        obs.update(active=True, evidence={"published_seed_sha256": expected_sha256})
        result["events"].append({"event_uid": row["event_uid"], "observations": [obs]})
    result["seed_observations_sha256"] = digest(canonical_bytes(sorted([event["event_uid"], event["observations"][0]["fingerprint"]] for event in result["events"])))
    validate_registry(result)
    return result


def resolve_rows(rows: list[dict], registry: dict) -> tuple[list[dict], list[dict]]:
    validate_registry(registry)
    known, by_source, historical = {}, {}, set()
    for event in registry["events"]:
        for obs in event["observations"]:
            key = observation_identity_key(obs)
            historical.add(key)
            for source in obs["source_records"]:
                by_source.setdefault((source["source_id"], source["record_id"]), set()).add(event["event_uid"])
            if obs["active"]:
                known[key] = (event["event_uid"], {(source["source_id"], source["record_id"]) for source in obs["source_records"]})
    resolved, held, seen = [], [], set()
    for row in rows:
        obs = observation_from_row(row)
        require(obs["candidate_key"] not in seen, "duplicate input candidate key")
        seen.add(obs["candidate_key"])
        sources = {(source["source_id"], source["record_id"]) for source in obs["source_records"]}
        key = observation_identity_key(obs)
        target = known.get(key)
        if target and sources & target[1]:
            resolved.append(({**row, "event_key": target[0]}, obs))
            continue
        related = sorted({uid for pair in sources for uid in by_source.get(pair, set())})
        reason = "superseded_observation" if key in historical and not target else "changed_or_unbound_observation" if related or target else "unregistered_candidate"
        held.append({**obs, "reason": reason, "related_event_uids": related})
    duplicates = {uid for uid, count in Counter(row["event_key"] for row, _ in resolved).items() if count > 1}
    published = []
    for row, obs in resolved:
        if row["event_key"] in duplicates:
            held.append({**obs, "reason": "multiple_candidates_for_fixed_id", "related_event_uids": [row["event_key"]]})
        else:
            published.append(row)
    held.sort(key=lambda row: row["fingerprint"])
    return published, held


def apply_to_payload(payload: dict, registry: dict, registry_sha256: str) -> dict:
    require(isinstance(registry_sha256, str) and HASH.fullmatch(registry_sha256), "invalid registry digest")
    result = deepcopy(payload)
    result["events"], result["identity_held_records"] = resolve_rows(result["events"], registry)
    counts = Counter(row["display_source_id"] for row in result["events"])
    result["summary"].update(event_count=len(result["events"]), counts_by_display_source=dict(counts), identity_held_record_count=len(result["identity_held_records"]))
    result["identity_registry"] = {"schema_version": 1, "revision": registry["revision"], "sha256": registry_sha256}
    return result


def validate_resolved_rows(rows: list[dict], registry: dict) -> None:
    """Reject edited/unbound final rows before the atomic LP replacement."""
    events = {event["event_uid"]: event for event in registry["events"]}
    seen = set()
    for row in rows:
        uid = row.get("event_key")
        require(uid in events and uid not in seen, "unbound or duplicate final fixed ID")
        seen.add(uid)
        identity = identity_from_row(row)
        sources = {(item["source_id"], item["record_id"]) for item in source_records_from_row(row)}
        require(any(obs["active"] and obs["identity"] == identity and sources & {(item["source_id"], item["record_id"]) for item in obs["source_records"]} for obs in events[uid]["observations"]), "final occurrence is not bound by the registry")


def apply_review(registry: dict, request: dict) -> dict:
    validate_registry(registry)
    fields = {"schema_version", "expected_revision", "kind", "previous_ids", "candidates", "evidence"}
    require(isinstance(request, dict) and set(request) in (fields, fields | {"acknowledged_related_event_uids"}), "invalid review request schema")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and type(request["expected_revision"]) is int, "invalid review request version")
    validate_evidence(request["evidence"])
    request_hash = digest(canonical_bytes(request))
    if any(relation["request_sha256"] == request_hash for relation in registry["relations"]):
        return deepcopy(registry)  # Repeating a committed request never allocates another ID.
    require(request["expected_revision"] == registry["revision"], "review request revision conflict")
    result = deepcopy(registry)
    events = {event["event_uid"]: event for event in result["events"]}
    previous = request["previous_ids"]
    require(isinstance(previous, list) and all(identifier(uid) for uid in previous) and len(previous) == len(set(previous)) and set(previous) <= set(events), "invalid previous IDs")
    require(all(any(obs["active"] for obs in events[uid]["observations"]) for uid in previous), "cannot reuse a retired ID")
    candidates = request["candidates"]
    require(isinstance(candidates, list) and candidates, "review candidates required")
    kind = request["kind"]
    require((kind == "new" and not previous) or (kind == "correction" and len(previous) == len(candidates) == 1) or (kind == "split" and len(previous) == 1 and len(candidates) >= 2) or (kind == "merge" and len(previous) >= 2 and len(candidates) == 1), "invalid review cardinality")
    acknowledged = request.get("acknowledged_related_event_uids", [])
    require(isinstance(acknowledged, list) and all(identifier(uid) for uid in acknowledged)
            and acknowledged == sorted(set(acknowledged)) and set(acknowledged) <= set(events), "invalid acknowledged related IDs")
    require(kind == "new" or not acknowledged, "related-ID acknowledgement is only for confirmed distinct new occurrences")
    if kind == "new":
        related = set()
        by_source = {}
        for event in registry["events"]:
            for obs in event["observations"]:
                for source in obs["source_records"]:
                    by_source.setdefault((source["source_id"], source["record_id"]), set()).add(event["event_uid"])
        for candidate in candidates:
            require(isinstance(candidate, dict) and set(candidate) == {"event_uid", "observation"}, "invalid reviewed candidate")
            validate_observation(candidate["observation"])
            for source in candidate["observation"]["source_records"]:
                related.update(by_source.get((source["source_id"], source["record_id"]), set()))
        require(acknowledged == sorted(related), "new occurrence shares registered sources; confirm correction/split/merge or explicitly acknowledge distinct occurrence IDs")
    for uid in previous:
        for obs in events[uid]["observations"]:
            obs["active"] = False
    following, fingerprints, mapped = [], set(), []
    for candidate in candidates:
        require(isinstance(candidate, dict) and set(candidate) == {"event_uid", "observation"}, "invalid reviewed candidate")
        obs = deepcopy(candidate["observation"])
        validate_observation(obs)
        require(obs["fingerprint"] not in fingerprints, "duplicate reviewed candidate")
        fingerprints.add(obs["fingerprint"])
        uid = candidate["event_uid"]
        if uid is None:
            require(kind != "correction", "correction must retain its ID")
            uid = "evt_" + uuid4().hex
            require(uid not in events, "new ID collision")
            events[uid] = {"event_uid": uid, "observations": []}
            result["events"].append(events[uid])
        else:
            require(identifier(uid) and uid in previous, "ID reuse outside confirmed predecessors")
        require(uid not in following, "one fixed ID cannot identify multiple children")
        following.append(uid)
        existing = next((old for old in events[uid]["observations"] if old["fingerprint"] == obs["fingerprint"]), None)
        if existing:
            existing["active"] = True
        else:
            obs.update(active=True, evidence=deepcopy(request["evidence"]))
            events[uid]["observations"].append(obs)
        mapped.append({"event_uid": uid, "fingerprint": obs["fingerprint"]})
    relation = {"kind": kind, "previous_ids": list(previous), "next_ids": following, "candidates": mapped, "evidence": deepcopy(request["evidence"]), "request_sha256": request_hash}
    if acknowledged:
        relation["acknowledged_related_event_uids"] = list(acknowledged)
    result["relations"].append(relation)
    result["revision"] += 1
    validate_registry(result)
    return result


@contextmanager
def registry_lock(path: Path):
    lock = path.with_name("." + path.name + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        owner = os.fstat(stream.fileno())
        try:
            stream.write(canonical_bytes({"pid": os.getpid(), "started_at_utc": datetime.now(timezone.utc).isoformat()}))
            stream.flush()
            yield
        finally:
            # Keep our inode open until cleanup, even if a manual unlink occurs.
            try:
                current = lock.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (current.st_dev, current.st_ino) == (owner.st_dev, owner.st_ino):
                    lock.unlink()


def atomic_write(path: Path, data: bytes, *, replace: bool = True) -> None:
    require(not path.is_symlink(), "output must not be a symlink")
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False) as stream:
            pending = Path(stream.name)
            if replace and path.exists():
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(pending, path)
            pending = None
        else:
            os.link(pending, path)  # Atomic, exclusive preview creation; never overwrite another file.
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def write_registry(registry: dict, path: Path, *, expected_sha256: str | None) -> bool:
    validate_registry(registry)
    data = json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    require(len(data) <= MAX_REGISTRY_BYTES, "registry exceeds byte limit; existing registry retained")
    path.parent.mkdir(parents=True, exist_ok=True)
    with registry_lock(path):
        if expected_sha256 is None:
            require(not path.exists(), "registry already exists; seed never overwrites it")
        else:
            _, current_hash = load_registry(path)
            require(current_hash == expected_sha256, "registry changed before write")
            if path.read_bytes() == data:
                return False
        atomic_write(path, data)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="Register exactly the approved published baseline once.")
    seed.add_argument("--snapshot", type=Path, required=True)
    seed.add_argument("--expected-sha256", required=True)
    seed.add_argument("--expected-count", type=int, required=True)
    seed.add_argument("--lp-baseline", type=Path, help="Exact LP input that produced the approved published baseline.")
    seed.add_argument("--expected-lp-sha256", help="Required with --lp-baseline; publication timestamp and source IDs must match.")
    commands.add_parser("validate")
    pending = commands.add_parser("pending", help="Inspect copied LP or current read-only source candidates; no registry/publication writes.")
    pending.add_argument("--lp-events", type=Path, help="Copied candidate/internal LP; omit to inspect current source DBs read-only.")
    pending.add_argument("--output", type=Path, required=True, help="New preview file only; an existing path is refused.")
    review = commands.add_parser("apply-review", help="Apply a reviewed new/correction/split/merge request; no publication.")
    review.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "seed":
        registry = seed_registry(args.snapshot.read_bytes(), expected_sha256=args.expected_sha256, expected_count=args.expected_count,
            lp_baseline_bytes=args.lp_baseline.read_bytes() if args.lp_baseline else None, expected_lp_sha256=args.expected_lp_sha256)
        if args.registry.exists():
            existing, _ = load_registry(args.registry)
            require(all(existing[field] == registry[field] for field in ["seed_snapshot_sha256", "seed_lp_sha256", "seed_event_count", "seed_ids_sha256", "seed_observations_sha256"]), "existing registry has a different seed")
            registry = existing
        else:
            write_registry(registry, args.registry, expected_sha256=None)
    elif args.command == "pending":
        registry, sha = load_registry(args.registry)
        if args.lp_events:
            data = args.lp_events.read_bytes()
            source = parse_json(data)
        else:
            from scripts.build_lp_events import _build_lp_event_candidates
            source = _build_lp_event_candidates()
            data = canonical_bytes(source)
        from scripts.validate_external_events import validate_payload
        validate_payload(source)
        if "identity_registry" in source:
            require(source["identity_registry"] == {"schema_version": 1, "revision": registry["revision"], "sha256": sha}, "preview registry changed")
            require(isinstance(source.get("identity_held_records"), list), "published LP omits held details; inspect current sources instead")
            validate_resolved_rows(source["events"], registry)
            rows, held = source["events"], source["identity_held_records"]
        else:
            rows, held = resolve_rows(source["events"], registry)
        preview = {"schema_version": 1, "registry_revision": registry["revision"], "registry_sha256": sha,
                   "input_sha256": digest(data), "resolved_count": len(rows), "held_records": held}
        atomic_write(args.output, json.dumps(preview, ensure_ascii=False, indent=2).encode("utf-8") + b"\n", replace=False)
    elif args.command == "apply-review":
        registry, expected = load_registry(args.registry)
        registry = apply_review(registry, parse_json(args.request.read_bytes()))
        write_registry(registry, args.registry, expected_sha256=expected)
    else:
        registry, _ = load_registry(args.registry)
    print(f"identity registry: revision={registry['revision']} ids={len(registry['events'])}; no publication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

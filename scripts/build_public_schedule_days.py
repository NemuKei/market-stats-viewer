"""Export only hash-approved public day observations; never register IDs or read DBs."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from . import event_identity_registry as ids
from .build_archival_schedule_days import normalized_title, validate_asset
from .events.types import JAPAN_PREFECTURES
from .preserve_published_event_ids import (
    CONSUMER_FILES, parse_input, pinned_consumer, read_input, utc_stamp,
)

PUBLIC_ASSET_FILENAME = "public_schedule_days.json"
PUBLIC_BASELINE_FILENAME = "public_schedule_baseline.json"
DATASET = "public_preserved_schedule_days"
ROOT_FIELDS = {"schema_version", "dataset", "generated_at_utc", "baseline_sha256",
               "provenance", "events", "schedule_metadata", "source_record_digests", "publication_policy"}
ROW_FIELDS = {"event_uid", "source_record_id", "source_policy_rule_id", "source_policy_status",
              "source_policy_reviewed_at", "source_domain", "kind", "kindLabel", "source_id", "source_name",
              "title", "start_date", "end_date", "start_time", "published_at_utc", "updated_at_utc",
              "url", "source_url", "venue_name", "pref_name", "artist_name", "event_category", "source_type"}
REQUIRED_ROW_FIELDS = ROW_FIELDS - {"start_time", "source_url", "artist_name"}
METADATA_FIELDS = {"kind", "observedTimes", "hasUnknownTime", "performanceCount", "occurrenceCompleted",
                   "evidenceBasis", "urlGranularity", "lastObservedAtUtc", "historicalVenueNames",
                   "observedTitles", "venueNotes"}
POLICY_FIELDS = {"status", "policyId", "policySchemaVersion", "reviewedAt", "defaultDeny",
                 "inputCount", "publishedCount", "excludedCount", "excludedByStatus", "allowedFields"}
HASH = re.compile(r"[0-9a-f]{64}")
TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?")
CANCEL = re.compile(r"中止|延期")


def require(value, message):
    if not value:
        raise ValueError(message)


def hash_value(value, label):
    require(isinstance(value, str) and HASH.fullmatch(value), f"invalid {label} SHA-256")


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def approval_set_digest(uids):
    return canonical_digest(sorted(uids))


def validate_publication_selection(selection, *, expected_approval_sha256):
    """Accept only an externally pinned, explicit subset of reviewed day IDs."""
    require(isinstance(selection, dict) and set(selection) == {"schema_version", "approved_ids"}
            and type(selection["schema_version"]) is int and selection["schema_version"] == 1,
            "invalid publication selection fields/version")
    approved_ids = selection["approved_ids"]
    require(isinstance(approved_ids, list) and all(ids.identifier(uid) for uid in approved_ids)
            and approved_ids == sorted(set(approved_ids)), "publication selection IDs must be sorted and unique")
    hash_value(expected_approval_sha256, "expected approval")
    require(approval_set_digest(approved_ids) == expected_approval_sha256,
            "reviewed publication selection differs")
    return set(approved_ids)


def source_record_digest(source_id, record_id):
    return canonical_digest([source_id, record_id])


def _url(value):
    require(isinstance(value, str), "invalid public URL")
    parsed = urlsplit(value)
    require(parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
            and not parsed.password, "invalid public URL")
    return parsed.hostname.lower().removeprefix("www.").rstrip(".")


def validate_public_baseline(payload):
    """The frozen baseline is an existing public v1 snapshot, not a private LP."""
    require(isinstance(payload, dict) and set(payload) == {"schemaVersion", "generation", "metadata", "coverage", "events"}
            and type(payload["schemaVersion"]) is int and payload["schemaVersion"] == 1, "public v1 baseline required")
    require(payload["generation"] == ids.digest(ids.canonical_bytes({k: v for k, v in payload.items() if k != "generation"})),
            "baseline generation differs")
    meta, coverage, events = payload["metadata"], payload["coverage"], payload["events"]
    require(isinstance(meta, dict) and set(meta) == {"generatedAtUtc", "eventSourceGeneratedAtUtc", "asOfDate",
        "eventHistoryWindowDays", "eventHistoryStartDate", "sourceRepository", "sourceOwner", "displayOwner", "sourceCommit", "sourceAssetSha256"},
        "private or missing baseline metadata")
    require(isinstance(coverage, dict) and set(coverage) == {"scope", "availableFrom", "availableThrough", "publicCount", "completeArchive"}
            and coverage["scope"] == "all_verified_retained" and coverage["completeArchive"] is False
            and meta["eventHistoryWindowDays"] is None and meta["sourceRepository"] == meta["sourceOwner"] == "market-stats-viewer"
            and meta["displayOwner"] == "SideBiz_HotelRM", "invalid baseline provenance/coverage")
    hash_value(meta["sourceAssetSha256"], "baseline source")
    require(isinstance(meta["sourceCommit"], str) and re.fullmatch(r"[0-9a-f]{40}", meta["sourceCommit"]), "invalid baseline commit")
    date.fromisoformat(meta["asOfDate"])
    utc_stamp(meta["generatedAtUtc"])
    utc_stamp(meta["eventSourceGeneratedAtUtc"])
    require(isinstance(events, dict) and set(events) == {"items", "publicationPolicy", "summary"}, "private baseline events")
    rows = events["items"]
    require(isinstance(rows, list) and rows, "empty baseline")
    for row in rows:
        require(isinstance(row, dict) and REQUIRED_ROW_FIELDS <= set(row) <= ROW_FIELDS
                and all(isinstance(v, str) and (v.strip() or k in {"start_time", "source_url", "artist_name"})
                        for k, v in row.items()), "invalid public baseline row fields")
        require(row["kind"] in {"official", "news"} and row["source_id"] in ids.SOURCES
                and row["source_policy_status"] in {"approved", "conditional"}
                and row["pref_name"] in JAPAN_PREFECTURES, "invalid baseline public predicate")
        start = date.fromisoformat(row["start_date"])
        require(start.isoformat() == row["start_date"] and date.fromisoformat(row["end_date"]) >= start, "invalid baseline date")
        if row.get("start_time"):
            require(TIME.fullmatch(row["start_time"]), "invalid baseline time")
        for field in ("published_at_utc", "updated_at_utc"):
            utc_stamp(row[field])
        date.fromisoformat(row["source_policy_reviewed_at"])
        require(_url(row.get("source_url") or row["url"]) == row["source_domain"], "invalid baseline domain")
        _url(row["url"])
    require(len({r["event_uid"] for r in rows}) == len(rows), "duplicate baseline public ID")
    require(type(coverage["publicCount"]) is int and coverage["publicCount"] == len(rows)
            and meta["eventHistoryStartDate"] == coverage["availableFrom"] == min(r["start_date"] for r in rows)
            and coverage["availableThrough"] == max(r["end_date"] for r in rows), "baseline range/count differs")
    _validate_policy(events["publicationPolicy"], len(rows))
    expected_summary = {"byKind": dict(sorted(Counter(r["kind"] for r in rows).items())),
        "categories": dict(sorted(Counter(r["event_category"] for r in rows).items())),
        "topPrefectures": [list(item) for item in Counter(r["pref_name"] for r in rows).most_common(12)]}
    require(events["summary"] == expected_summary, "baseline summary differs")
    return {"baseline_count": len(rows)}


def _validate_policy(policy, count):
    require(isinstance(policy, dict) and set(policy) == POLICY_FIELDS, "invalid publication policy fields")
    allowed = policy["allowedFields"]
    require(policy["status"] == "enforced" and policy["defaultDeny"] is True
            and isinstance(policy["policyId"], str) and policy["policyId"].strip()
            and type(policy["policySchemaVersion"]) is int and policy["policySchemaVersion"] == 1
            and isinstance(allowed, list) and all(isinstance(v, str) for v in allowed)
            and len(set(allowed)) == len(allowed) and set(allowed) == ROW_FIELDS, "invalid public policy predicate")
    date.fromisoformat(policy["reviewedAt"])
    require(all(type(policy[k]) is int and policy[k] >= 0 for k in ("inputCount", "publishedCount", "excludedCount"))
            and policy["publishedCount"] == count and policy["inputCount"] == count + policy["excludedCount"],
            "publication policy counts differ")
    excluded = policy["excludedByStatus"]
    require(isinstance(excluded, dict) and set(excluded) == {"blocked", "unknown", "invalid"}
            and all(type(v) is int and v >= 0 for v in excluded.values())
            and sum(excluded.values()) == policy["excludedCount"], "publication exclusion counts differ")


def validate_public_asset(payload, *, expected_approval_sha256=None):
    """Validate the standalone public contract without loading a private ledger."""
    require(isinstance(payload, dict) and set(payload) == ROOT_FIELDS, "invalid public schedule fields")
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1
            and payload["dataset"] == DATASET, "invalid public schedule dataset/version")
    utc_stamp(payload["generated_at_utc"])
    hash_value(payload["baseline_sha256"], "baseline")
    provenance = payload["provenance"]
    require(isinstance(provenance, dict) and set(provenance) == {
        "schedule_asset_sha256", "identity_registry", "approval_set_sha256"}, "invalid schedule provenance")
    for field in ("schedule_asset_sha256", "approval_set_sha256"):
        hash_value(provenance[field], field)
    registry = provenance["identity_registry"]
    require(isinstance(registry, dict) and set(registry) == {"schema_version", "revision", "sha256"}
            and type(registry["schema_version"]) is int and registry["schema_version"] == 2
            and type(registry["revision"]) is int and registry["revision"] >= 1, "invalid day registry provenance")
    hash_value(registry["sha256"], "registry")
    rows = payload["events"]
    require(isinstance(rows, list), "public days must be a list")
    require(rows or expected_approval_sha256 is not None, "empty public days require an external approval pin")
    uids = []
    for row in rows:
        require(isinstance(row, dict) and REQUIRED_ROW_FIELDS <= set(row) <= ROW_FIELDS,
                "private or missing public row fields")
        require(all(isinstance(v, str) and v.strip() for k, v in row.items()
                    if k not in {"start_time", "artist_name", "source_url"})
                and all(isinstance(row.get(k, ""), str) for k in ("start_time", "artist_name", "source_url")), "invalid public row text")
        require(row.get("start_time", "") == "" and row.get("artist_name", "") == ""
                and row["kind"] == "official" and row["source_id"] == "official_events"
                and row["source_type"] == "venue_official"
                and row["source_policy_status"] in {"approved", "conditional"}, "unapproved day row predicate")
        require(not CANCEL.search(row["title"]), "cancelled/postponed day cannot publish")
        require(date.fromisoformat(row["start_date"]).isoformat() == row["start_date"]
                and row["end_date"] == row["start_date"], "day must have one canonical date")
        require(row["pref_name"] in JAPAN_PREFECTURES, "invalid domestic prefecture")
        date.fromisoformat(row["source_policy_reviewed_at"])
        for field in ("published_at_utc", "updated_at_utc"):
            utc_stamp(row[field])
        require(_url(row.get("source_url") or row["url"]) == row["source_domain"], "day source domain differs")
        _url(row["url"])
        uids.append(row["event_uid"])
    require(len(set(uids)) == len(uids), "duplicate public day ID")
    computed = approval_set_digest(uids)
    require(computed == provenance["approval_set_sha256"], "day approval set differs")
    if expected_approval_sha256 is not None:
        hash_value(expected_approval_sha256, "expected approval")
        require(computed == expected_approval_sha256, "reviewed day approval set differs")
    metadata, digests = payload["schedule_metadata"], payload["source_record_digests"]
    require(isinstance(metadata, dict) and isinstance(digests, dict)
            and set(metadata) == set(digests) == set(uids), "day metadata/digest IDs differ")
    for row in rows:
        uid = row["event_uid"]
        m = metadata[uid]
        require(isinstance(m, dict) and set(m) == METADATA_FIELDS, "invalid day metadata fields")
        require(m["kind"] == "schedule_day" and m["performanceCount"] is None
                and m["occurrenceCompleted"] == "unverified" and m["evidenceBasis"] == "preserved_official_schedule"
                and m["urlGranularity"] == "calendar" and type(m["hasUnknownTime"]) is bool,
                "false performance predicate")
        times = m["observedTimes"]
        require(isinstance(times, list) and all(isinstance(t, str) and TIME.fullmatch(t) for t in times)
                and times == sorted(set(times)) and (times or m["hasUnknownTime"]), "invalid observed times")
        utc_stamp(m["lastObservedAtUtc"])
        for field in ("historicalVenueNames", "observedTitles", "venueNotes"):
            values = m[field]
            require(isinstance(values, list) and (values or field == "venueNotes")
                    and all(isinstance(v, str) and v.strip() for v in values)
                    and values == sorted(set(values)), "invalid original display metadata")
        require(not any(CANCEL.search(t) for t in m["observedTitles"]), "suppressed original title")
        require(row["title"] in m["observedTitles"]
                or any(normalized_title(t)[:180] == row["title"] for t in m["observedTitles"]),
                "public representative title is not an original observation")
        values = digests[uid]
        require(isinstance(values, list) and values and all(isinstance(v, str) and HASH.fullmatch(v) for v in values)
                and values == sorted(set(values)), "invalid source record digests")
    _validate_policy(payload["publication_policy"], len(rows))
    require(payload["publication_policy"]["excludedByStatus"]["invalid"] == 0, "invalid private days must not be omitted")
    return {"day_count": len(rows), "approval_set_sha256": computed}


def build_public_asset(source, registry, snapshot, *, source_sha256, registry_sha256,
                       expected_approval_sha256, projector, publication_selection=None):
    """Use the existing consumer projection, not a second source-policy implementation."""
    hash_value(source_sha256, "private source")
    hash_value(registry_sha256, "private registry")
    validate_asset(source, registry, registry_sha256)
    require(type(source["schema_version"]) is int and registry["schema_version"] == 2,
            "typed private day source required")
    by_id = {r["event_key"]: r for r in source["events"]}
    entries = {e["event_uid"]: e for e in registry["events"]}
    for uid, row in by_id.items():
        active = [o for o in entries[uid]["observations"] if o["active"]]
        source_records = ids.source_records_from_row(row)
        require(len(source_records) == len(row["supporting_sources"]), "duplicate private source records")
        require(len(active) == 1 and active[0]["identity"] == ids.identity_from_row(row)
                and active[0]["source_records"] == source_records, "private day/source binding differs")
    projected, publication = projector(source["events"], snapshot)
    require(isinstance(snapshot, dict) and type(snapshot.get("schemaVersion")) is int
            and snapshot["schemaVersion"] == 2, "approved typed snapshot required")
    meta, events = snapshot["metadata"], snapshot["events"]
    require(meta["scheduleSourceAssetSha256"] == source_sha256
            and meta["scheduleSourceGeneratedAtUtc"] == source["generated_at_utc"], "snapshot private source differs")
    units = events["recordUnits"]
    items = events["items"]
    require(len({r["event_uid"] for r in items}) == len(items) and set(units) == {r["event_uid"] for r in items}
            and set(units.values()) <= {"occurrence", "schedule_day"}, "invalid approved snapshot IDs/units")
    approved = [r for r in items if units[r["event_uid"]] == "schedule_day"]
    require(approved == projected, "approved public projection changed")
    approved_ids = {r["event_uid"] for r in approved}
    require(approved_ids <= set(by_id) and set(events["scheduleDays"]) == approved_ids
            and events["scheduleDays"] == {uid: source["schedule_metadata"][uid] for uid in approved_ids},
            "approved original day metadata changed")
    require(approved or publication_selection is not None, "public days must be nonempty without an explicit selection")
    result = {"schema_version": 1, "dataset": DATASET, "generated_at_utc": source["generated_at_utc"],
              "baseline_sha256": source["baseline_sha256"],
              "provenance": {"schedule_asset_sha256": source_sha256, "identity_registry": deepcopy(source["identity_registry"]),
                             "approval_set_sha256": approval_set_digest(approved_ids)},
              "events": deepcopy(approved), "schedule_metadata": deepcopy(events["scheduleDays"]),
              "source_record_digests": {uid: sorted(source_record_digest(s["source_id"], s["record_id"])
                                                   for s in ids.source_records_from_row(by_id[uid])) for uid in sorted(approved_ids)},
              "publication_policy": deepcopy(publication)}
    # Validate every reviewed row and the original aggregates before selection can omit anything.
    validate_public_asset(result, expected_approval_sha256=approval_set_digest(approved_ids))
    if publication_selection is not None:
        selected_ids = validate_publication_selection(publication_selection,
            expected_approval_sha256=expected_approval_sha256)
        require(selected_ids <= approved_ids, "publication selection includes an unapproved day ID")
        stopped_count = len(approved_ids - selected_ids)
        result["events"] = [row for row in result["events"] if row["event_uid"] in selected_ids]
        for field in ("schedule_metadata", "source_record_digests"):
            result[field] = {uid: value for uid, value in result[field].items() if uid in selected_ids}
        result["publication_policy"]["publishedCount"] -= stopped_count
        result["publication_policy"]["excludedCount"] += stopped_count
        result["publication_policy"]["excludedByStatus"]["blocked"] += stopped_count
    result["provenance"]["approval_set_sha256"] = expected_approval_sha256
    validate_public_asset(result, expected_approval_sha256=expected_approval_sha256)
    return result


def validate_public_package(data_dir, *, expected_public_sha256=None, expected_baseline_sha256=None,
                            expected_approval_sha256=None):
    captures = [read_input(data_dir / name, name) for name in (PUBLIC_ASSET_FILENAME, PUBLIC_BASELINE_FILENAME)]
    for raw, expected in zip(captures, (expected_public_sha256, expected_baseline_sha256)):
        if expected is not None:
            hash_value(expected, "expected public package")
            require(ids.digest(raw) == expected, "reviewed public package bytes differ")
    public, baseline = [parse_input(raw) for raw in captures]
    result = validate_public_asset(public, expected_approval_sha256=expected_approval_sha256)
    require(ids.digest(captures[1]) == public["baseline_sha256"], "public package baseline digest differs")
    result.update(validate_public_baseline(baseline))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("private-asset", "registry", "approved-snapshot", "consumer-scripts", "consumer-hashes", "source-policy", "baseline", "output", "baseline-output"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("asset", "registry", "snapshot", "consumer-hashes", "policy", "approval"):
        p.add_argument("--expected-" + name + "-sha256", required=True)
    p.add_argument("--publication-selection", type=Path)
    args = p.parse_args(argv)
    paths = [args.private_asset, args.registry, args.approved_snapshot, args.consumer_hashes, args.source_policy, args.baseline]
    if args.publication_selection is not None:
        paths.append(args.publication_selection)
    outputs = [args.output, args.baseline_output]
    require(args.output.name == PUBLIC_ASSET_FILENAME and args.baseline_output.name == PUBLIC_BASELINE_FILENAME
            and args.output.parent.resolve() == args.baseline_output.parent.resolve(), "fixed public package filenames required")
    for path in paths + outputs:
        require(".." not in path.parts and not any(p.is_symlink() for p in [path, *path.parents]), "unsafe producer path")
    require(all(output.resolve() != path.resolve() and not (output.exists() and output.samefile(path))
                for path in paths for output in outputs), "public output cannot overwrite an input")
    captures = [read_input(path, str(path), limit=ids.MAX_REGISTRY_BYTES if path == args.registry else 64 * 1024 * 1024) for path in paths]
    for raw, expected in zip(captures[:5],
                             [args.expected_asset_sha256, args.expected_registry_sha256, args.expected_snapshot_sha256,
                              args.expected_consumer_hashes_sha256, args.expected_policy_sha256]):
        hash_value(expected, "expected input")
        require(ids.digest(raw) == expected, "reviewed producer input changed")
    source, registry, snapshot, hashes, _, baseline = [parse_input(raw) for raw in captures[:6]]
    selection = parse_input(captures[6]) if args.publication_selection is not None else None
    if args.publication_selection is not None:
        validate_publication_selection(selection, expected_approval_sha256=args.expected_approval_sha256)
    require(ids.digest(captures[5]) == source["baseline_sha256"], "reviewed public baseline changed")
    validate_public_baseline(baseline)
    require(set(hashes) == set(CONSUMER_FILES), "exact consumer script hashes required")
    scripts = {name: read_input(args.consumer_scripts / name, name) for name in CONSUMER_FILES}
    for name, raw in scripts.items():
        hash_value(hashes[name], "consumer")
        require(ids.digest(raw) == hashes[name], "reviewed consumer script changed")
    with tempfile.TemporaryDirectory() as folder, pinned_consumer(args.consumer_scripts, scripts) as (portal, policy_module):
        policy_path = Path(folder) / "policy.json"
        policy_path.write_bytes(captures[4])
        policy = policy_module.load_source_policy(policy_path)
        policy_module.verify_public_event_payload(baseline, policy)
        def projector(rows, approved):
            policy_module.verify_public_event_payload(approved, policy)
            return policy_module.project_public_events(portal.export_lp_event_rows(rows, history_start_date=None), policy)
        result = build_public_asset(source, registry, snapshot, source_sha256=args.expected_asset_sha256,
            registry_sha256=args.expected_registry_sha256, expected_approval_sha256=args.expected_approval_sha256,
            projector=projector, publication_selection=selection)
    data = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    for output, content in zip(outputs, [data, captures[5]]):
        if output.exists():
            require(read_input(output, "previous public asset") == content, "public asset changes require a new reviewed output")
    for output, content in zip(outputs, [data, captures[5]]):
        if not output.exists():
            ids.atomic_write(output, content, replace=False)
    print(json.dumps(validate_public_asset(result, expected_approval_sha256=args.expected_approval_sha256)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

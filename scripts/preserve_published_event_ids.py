"""Preserve an explicitly reviewed set of already-published IDs, offline.

This migration never allocates IDs or interprets changed occurrences. The
consumer's hash-pinned exporter and policy implementation must reproduce every
public event field from the exact source LP. Default mode validates only;
--apply backs up the original registry once and atomically supplements it.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from types import ModuleType
from typing import Any

from scripts import event_identity_registry as ids


MAX_INPUT_BYTES = 64_000_000
CONSUMER_FILES = (
    "event_source_policy.py",
    "refresh_content_freshness.py",
    "verify_external_events_asset.py",
    "refresh_market_portal_data.py",
)
REQUEST_FIELDS = {
    "schema_version", "kind", "origin_registry_sha256", "origin_registry_revision",
    "snapshot_sha256", "lp_sha256", "consumer_scripts_sha256", "policy_sha256",
    "added_ids", "added_count", "evidence",
}


def read_input(path: Path, label: str, *, limit: int = MAX_INPUT_BYTES) -> bytes:
    ids.require(not path.is_symlink() and path.is_file(), f"{label} must be a regular nonsymlink file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    ids.require(len(data) <= limit, f"{label} exceeds byte limit")
    return data


def parse_input(data: bytes) -> dict:
    """Public envelopes can exceed the registry's separate 16 MB limit."""
    ids.require(len(data) <= MAX_INPUT_BYTES, "input JSON exceeds byte limit")
    def finite_float(value: str) -> float:
        number = float(value)
        ids.require(math.isfinite(number), "non-finite JSON number")
        return number

    result = json.loads(data.decode("utf-8"), object_pairs_hook=ids._object, parse_float=finite_float,
                        parse_constant=lambda _: ids.require(False, "non-finite JSON number"))
    ids.require(isinstance(result, dict), "input JSON root must be an object")
    return result


def read_registry(path: Path) -> tuple[dict, str, bytes]:
    # Gate before opening: load_registry's general read_bytes is unbounded and
    # can block on a FIFO. Every initial/CAS read in this migration uses this
    # regular-file check and the registry's distinct size limit instead.
    data = read_input(path, "registry", limit=ids.MAX_REGISTRY_BYTES)
    registry = ids.parse_json(data)
    ids.validate_registry(registry)
    return registry, ids.digest(data), data


def validate_request(request: dict) -> None:
    ids.require(set(request) == REQUEST_FIELDS, "invalid preservation request schema")
    ids.require(type(request["schema_version"]) is int and request["schema_version"] == 1
                and request["kind"] == "preserve_published", "invalid preservation request version/kind")
    for field in ("origin_registry_sha256", "snapshot_sha256", "lp_sha256", "policy_sha256"):
        ids.require(isinstance(request[field], str) and ids.HASH.fullmatch(request[field]), f"invalid {field}")
    ids.require(type(request["origin_registry_revision"]) is int and request["origin_registry_revision"] >= 1,
                "invalid origin registry revision")
    scripts = request["consumer_scripts_sha256"]
    ids.require(isinstance(scripts, dict) and set(scripts) == set(CONSUMER_FILES)
                and all(isinstance(value, str) and ids.HASH.fullmatch(value) for value in scripts.values()),
                "exact four consumer script hashes required")
    additions = request["added_ids"]
    ids.require(isinstance(additions, list) and all(ids.identifier(uid) for uid in additions)
                and additions == sorted(set(additions)), "added IDs must be unique and sorted")
    ids.require(type(request["added_count"]) is int and request["added_count"] > 0
                and len(additions) == request["added_count"], "added ID count mismatch")
    ids.validate_evidence(request["evidence"])


def index_rows(rows: Any, key: str, label: str) -> dict[str, dict]:
    ids.require(isinstance(rows, list), f"{label} rows must be a list")
    result = {}
    for row in rows:
        ids.require(isinstance(row, dict) and ids.identifier(row.get(key)) and row[key] not in result,
                    f"duplicate or invalid {label} ID/key")
        result[row[key]] = row
    return result


def utc_stamp(value: Any) -> datetime:
    ids.require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value),
        "generation timestamp must be explicit UTC")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    ids.require(stamp.utcoffset() == timedelta(0), "generation timestamp must be UTC")
    return stamp


@contextmanager
def pinned_consumer(scripts_dir: Path, script_bytes: dict[str, bytes]):
    """Execute the verified bytes, bypassing pycache and cached imports.

    The four modules have only standard-library and mutual imports. Their real
    __file__ paths are retained for existing consumer constants. Original module
    bindings are restored even when import or projection fails.
    """
    names = [Path(filename).stem for filename in CONSUMER_FILES]
    absent = object()
    previous = {name: sys.modules.get(name, absent) for name in names}
    try:
        modules = {}
        for filename, name in zip(CONSUMER_FILES, names):
            module = ModuleType(name)
            module.__file__ = str(scripts_dir / filename)
            module.__package__ = ""
            modules[name] = module
            sys.modules[name] = module
        for filename, name in zip(CONSUMER_FILES, names):
            exec(compile(script_bytes[filename], str(scripts_dir / filename), "exec"), modules[name].__dict__)
        yield modules["refresh_market_portal_data"], modules["event_source_policy"]
    finally:
        for name, module in previous.items():
            if module is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def project_snapshot(lp_bytes: bytes, policy_bytes: bytes, script_bytes: dict[str, bytes],
                     scripts_dir: Path, as_of_date: str) -> tuple[list[dict], dict]:
    # Existing consumer functions read paths. Give them private immutable input
    # copies so a concurrent edit cannot replace bytes after their hash check.
    with tempfile.TemporaryDirectory(prefix="preserve-published-inputs-") as directory:
        root = Path(directory)
        lp_path, policy_path = root / "lp_events.json", root / "source-policy.json"
        for path, data in ((lp_path, lp_bytes), (policy_path, policy_bytes)):
            with path.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
        with pinned_consumer(scripts_dir, script_bytes) as (portal, policy_module):
            policy = policy_module.load_source_policy(policy_path)
            raw = portal.export_lp_events(root, as_of_date, lp_events_path=lp_path)
            ids.require(isinstance(raw, list), "consumer exporter did not return event rows")
            return policy_module.project_public_events(raw, policy)


def validate_generation(snapshot: dict, lp: dict, projected: list[dict], policy: dict) -> tuple[dict, dict]:
    metadata, events = snapshot.get("metadata"), snapshot.get("events")
    ids.require(isinstance(metadata, dict) and isinstance(events, dict), "published snapshot envelope required")
    ids.require(type(lp.get("schema_version")) is int and lp["schema_version"] == 1, "invalid source LP schema")
    basis = lp.get("as_of_date")
    ids.require(isinstance(basis, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", basis), "invalid source LP basis")
    date.fromisoformat(basis)
    ids.require(basis == metadata.get("asOfDate"), "published/source LP basis mismatch")
    ids.require(utc_stamp(lp.get("generated_at_utc")) == utc_stamp(metadata.get("eventSourceGeneratedAtUtc")),
                "published/source LP generation mismatch")
    public = index_rows(events.get("items"), "event_uid", "published")
    source = index_rows(lp.get("events"), "event_key", "source LP")
    projection = index_rows(projected, "event_uid", "consumer projection")
    publication = events.get("publicationPolicy")
    ids.require(isinstance(publication, dict) and publication.get("status") == "enforced"
                and publication.get("defaultDeny") is True and type(publication.get("publishedCount")) is int
                and publication["publishedCount"] == len(public), "enforced publication policy/count required")
    ids.require(ids.canonical_bytes(publication) == ids.canonical_bytes(policy), "consumer publication policy mismatch")
    ids.require(ids.canonical_bytes(public) == ids.canonical_bytes(projection),
                "consumer projection differs from published IDs/fields")
    ids.require(set(public) <= set(source), "published ID missing from same-generation LP")
    for row in public.values():
        ids.require(row.get("source_policy_status") in {"approved", "conditional"}, "unpublished supplementation row")
    return public, source


def construct_migration(origin: dict, public: dict, source: dict, request: dict) -> dict:
    origin_ids = {event["event_uid"] for event in origin["events"]}
    ids.require(sorted(set(public) - origin_ids) == request["added_ids"], "exact added published ID set mismatch")
    by_source = set()
    for event in origin["events"]:
        for observation in event["observations"]:
            by_source.update((item["source_id"], item["record_id"]) for item in observation["source_records"])
    result = deepcopy(origin)
    candidates = []
    for uid in request["added_ids"]:
        observation = ids.observation_from_row(source[uid])
        published_sources = ids.source_records_from_row(public[uid], public=True)
        for item in published_sources:
            matches = [original for original in observation["source_records"]
                       if original["source_id"] == item["source_id"]
                       and (original["record_id"] == item["record_id"]
                            or len(item["record_id"]) == ids.PUBLISHED_SOURCE_RECORD_ID_LIMIT
                            and original["record_id"].startswith(item["record_id"]))]
            ids.require(len(matches) == 1, "published source record missing or ambiguous in source LP")
        sources = {(item["source_id"], item["record_id"]) for item in observation["source_records"]}
        ids.require(not sources & by_source, "unreviewed registered/additional source collision")
        by_source.update(sources)
        observation.update(active=True, evidence=deepcopy(request["evidence"]))
        result["events"].append({"event_uid": uid, "observations": [observation]})
        candidates.append({"event_uid": uid, "fingerprint": observation["fingerprint"]})
    result["relations"].append({"kind": "new", "previous_ids": [], "next_ids": list(request["added_ids"]),
                                "candidates": candidates, "evidence": deepcopy(request["evidence"]),
                                "request_sha256": ids.digest(ids.canonical_bytes(request))})
    result["revision"] += 1
    ids.validate_registry(result)
    bound, _ = ids.resolve_rows(list(source.values()), result)
    ids.require(set(public) <= {row["event_key"] for row in bound}, "published occurrence is not bound by preservation registry")
    return result


def assert_preserved(current: dict, expected: dict) -> None:
    """Replay accepts later reviews, but never missing/rewritten history."""
    ids.validate_registry(current)
    for field in expected:
        if field not in {"events", "relations", "revision"}:
            ids.require(current[field] == expected[field], "preservation seed metadata changed")
    ids.require(current["relations"][:len(expected["relations"])] == expected["relations"],
                "preservation origin/journal history changed")
    events = {event["event_uid"]: event for event in current["events"]}
    for event in expected["events"]:
        ids.require(event["event_uid"] in events, "preservation lost an original/published ID")
        observations = {observation["fingerprint"]: observation for observation in events[event["event_uid"]]["observations"]}
        for observation in event["observations"]:
            actual = observations.get(observation["fingerprint"])
            ids.require(actual is not None and
                        {key: value for key, value in actual.items() if key != "active"} ==
                        {key: value for key, value in observation.items() if key != "active"},
                        "preservation original observation/evidence changed")


def validate_paths(registry_path: Path, backup_path: Path, sources: list[Path], scripts_dir: Path) -> None:
    ids.require(not registry_path.is_symlink(), "registry must not be a symlink")
    ids.require(not scripts_dir.is_symlink() and scripts_dir.is_dir(), "consumer scripts must be a nonsymlink directory")
    ids.require(not backup_path.is_symlink() and backup_path.parent.is_dir()
                and not backup_path.parent.is_symlink(), "backup requires a nonsymlink path/directory")
    ids.require(backup_path.resolve() not in {path.resolve() for path in sources + [registry_path]},
                "backup would overwrite a source/registry path")
    if backup_path.exists():
        ids.require(backup_path.is_file(), "backup must be a regular file")
        for path in sources + [registry_path]:
            ids.require(not path.exists() or not backup_path.samefile(path), "backup aliases a source/registry file")


def preserve_published(*, registry_path: Path, request_path: Path, expected_request_sha256: str,
                       snapshot_path: Path, lp_path: Path, scripts_dir: Path, policy_path: Path,
                       backup_path: Path, apply: bool = False) -> dict:
    scripts_dir = scripts_dir.absolute()
    script_paths = [scripts_dir / filename for filename in CONSUMER_FILES]
    source_paths = [request_path, snapshot_path, lp_path, policy_path, *script_paths]
    validate_paths(registry_path, backup_path, source_paths, scripts_dir)
    captured = {path: read_input(path, "migration input") for path in source_paths}
    ids.require(isinstance(expected_request_sha256, str) and ids.HASH.fullmatch(expected_request_sha256)
                and ids.digest(captured[request_path]) == expected_request_sha256, "reviewed request hash mismatch")
    request = parse_input(captured[request_path])
    validate_request(request)
    for path, expected in ((snapshot_path, request["snapshot_sha256"]), (lp_path, request["lp_sha256"]),
                           (policy_path, request["policy_sha256"])):
        ids.require(ids.digest(captured[path]) == expected, "snapshot/LP/policy input hash mismatch")
    scripts = {filename: captured[scripts_dir / filename] for filename in CONSUMER_FILES}
    for filename, data in scripts.items():
        ids.require(ids.digest(data) == request["consumer_scripts_sha256"][filename], "consumer script hash mismatch")
    snapshot, lp = parse_input(captured[snapshot_path]), parse_input(captured[lp_path])
    parse_input(captured[policy_path])
    # Reject duplicate keys before any consumer dict conversion can hide them.
    index_rows(snapshot.get("events", {}).get("items"), "event_uid", "published")
    index_rows(lp.get("events"), "event_key", "source LP")
    projected, policy = project_snapshot(captured[lp_path], captured[policy_path], scripts, scripts_dir, lp.get("as_of_date"))
    public, source = validate_generation(snapshot, lp, projected, policy)
    with ids.registry_lock(registry_path):
        current, current_sha, current_bytes = read_registry(registry_path)
        if backup_path.exists():
            origin_bytes = read_input(backup_path, "origin backup", limit=ids.MAX_REGISTRY_BYTES)
        else:
            origin_bytes = current_bytes
        ids.require(ids.digest(origin_bytes) == request["origin_registry_sha256"], "origin registry hash mismatch")
        origin = ids.parse_json(origin_bytes)
        ids.validate_registry(origin)
        ids.require(origin["revision"] == request["origin_registry_revision"], "origin registry revision mismatch")
        expected = construct_migration(origin, public, source, request)
        request_hash = ids.digest(ids.canonical_bytes(request))
        replay = any(relation["request_sha256"] == request_hash for relation in current["relations"])
        if replay:
            ids.require(backup_path.exists(), "replay requires original registry backup")
            assert_preserved(current, expected)
        else:
            ids.require(current_bytes == origin_bytes and current["revision"] == origin["revision"],
                        "initial registry state/revision conflict")
        for path, data in captured.items():
            ids.require(read_input(path, "migration input") == data, "migration input changed before write")
        _, final_sha, _ = read_registry(registry_path)
        ids.require(final_sha == current_sha, "registry changed before write")
        if replay or not apply:
            return {"changed": False, "would_change": not replay, "replay": replay,
                    "revision": current["revision"], "ids": len(current["events"]),
                    "added_count": request["added_count"], "publication_changed": False}
        data = json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        ids.require(len(data) <= ids.MAX_REGISTRY_BYTES, "registry exceeds byte limit; existing registry retained")
        if not backup_path.exists():
            ids.atomic_write(backup_path, origin_bytes, replace=False)
        ids.require(read_input(backup_path, "origin backup", limit=ids.MAX_REGISTRY_BYTES) == origin_bytes,
                    "origin backup changed before write")
        _, final_sha, _ = read_registry(registry_path)
        ids.require(final_sha == current_sha, "registry changed before atomic replacement")
        ids.atomic_write(registry_path, data)
        return {"changed": True, "would_change": False, "replay": False,
                "revision": expected["revision"], "ids": len(expected["events"]),
                "added_count": request["added_count"], "publication_changed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--expected-request-sha256", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--lp-baseline", type=Path, required=True)
    parser.add_argument("--consumer-scripts", type=Path, required=True)
    parser.add_argument("--source-policy", type=Path, required=True)
    parser.add_argument("--origin-backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Back up and atomically supplement the registry; default is validation only.")
    args = parser.parse_args(argv)
    result = preserve_published(registry_path=args.registry, request_path=args.request,
        expected_request_sha256=args.expected_request_sha256, snapshot_path=args.snapshot,
        lp_path=args.lp_baseline, scripts_dir=args.consumer_scripts, policy_path=args.source_policy,
        backup_path=args.origin_backup, apply=args.apply)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit, single-field corrections to already-published legacy rows.

No new public fields or links are accepted. The baseline remains immutable;
reviewers pin its exact row, the current official observation and the registry
correction transaction. This is not an automatic alias/identity repair.
"""

from copy import deepcopy
from functools import wraps

from .event_identity_registry import (
    canonical_bytes,
    digest,
    identity_from_row,
    observation_from_row,
    validate_evidence,
    validate_observation,
)

MODE = "legacy_artist_correction"
FIELDS = {
    "mode",
    "event_uid",
    "observation",
    "source_signature",
    "previous_row_sha256",
    "correction_request_sha256",
    "evidence",
}


def source_map_errors(function):
    """Preserve the public source-map exception contract at this boundary."""

    @wraps(function)
    def checked(*args, **kwargs):
        from .reviewed_source_map import SourceMapError

        try:
            return function(*args, **kwargs)
        except ValueError as exc:
            if isinstance(exc, SourceMapError):
                raise
            raise SourceMapError(str(exc)) from exc

    return checked


@source_map_errors
def split_records(doc):
    regular, corrections = [], []
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema_version", "records"}
        or type(doc["schema_version"]) is not int
        or doc["schema_version"] != 1
        or not isinstance(doc["records"], list)
    ):
        raise ValueError("invalid reviewed source map")
    uids, keys = set(), set()
    for rec in doc["records"]:
        if not isinstance(rec, dict):
            raise ValueError("invalid source review record")
        uid = rec.get("event_uid")
        key = (
            rec.get("candidate_key")
            if rec.get("mode") == "artist_source_link"
            else rec.get("observation", {}).get("candidate_key")
        )
        if not isinstance(uid, str) or not isinstance(key, str):
            raise ValueError("invalid reviewed selection")
        if uid in uids or key in keys:
            raise ValueError("duplicate reviewed selection")
        uids.add(uid)
        keys.add(key)
        if rec.get("mode") != MODE:
            regular.append(rec)
            continue
        if set(rec) != FIELDS:
            raise ValueError("invalid legacy artist correction")
        validate_observation(rec["observation"])
        validate_evidence(rec["evidence"])
        for field in (
            "source_signature",
            "previous_row_sha256",
            "correction_request_sha256",
        ):
            value = rec[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("invalid correction digest")
        corrections.append(rec)
    return {"schema_version": 1, "records": regular}, corrections


@source_map_errors
def validate_correction(rec, baseline, registry, official_sources, candidate=None):
    """Return an exact baseline copy changing only artist_name, or fail closed."""
    from .reviewed_source_map import source_signature

    uid = rec["event_uid"]
    if baseline["schema_version"] != 5 or uid not in baseline["published_rows"]:
        raise ValueError("artist correction requires an existing v5 published ID")
    old = baseline["published_rows"][uid]
    if digest(canonical_bytes(old)) != rec["previous_row_sha256"]:
        raise ValueError("previous public row changed since correction review")
    old_identity = identity_from_row(old)
    obs = rec["observation"]
    new_identity = obs["identity"]
    if (
        not old_identity.get("artist_name")
        or not new_identity.get("artist_name")
        or old_identity["artist_name"] == new_identity["artist_name"]
        or {k: v for k, v in old_identity.items() if k != "artist_name"}
        != {k: v for k, v in new_identity.items() if k != "artist_name"}
    ):
        raise ValueError("only artist_name may change on the same occurrence")
    event = next(
        (event for event in registry["events"] if event["event_uid"] == uid), None
    )
    if event is None or not any(
        o["active"] and o["fingerprint"] == obs["fingerprint"]
        for o in event["observations"]
    ):
        raise ValueError("correction is not the active fixed-ID observation")
    if not any(
        not o["active"] and o["identity"] == old_identity for o in event["observations"]
    ):
        raise ValueError("prior fixed-ID observation history required")
    relations = [
        r
        for r in registry["relations"]
        if r["request_sha256"] == rec["correction_request_sha256"]
    ]
    if len(relations) != 1:
        raise ValueError("exact reviewed correction transaction required")
    relation = relations[0]
    if (
        relation["kind"] != "correction"
        or relation["previous_ids"] != [uid]
        or relation["next_ids"] != [uid]
        or relation["candidates"]
        != [{"event_uid": uid, "fingerprint": obs["fingerprint"]}]
        or relation["evidence"] != rec["evidence"]
    ):
        raise ValueError("correction transaction does not match publication review")
    relation_index = registry["relations"].index(relation)

    def affected(r):
        return uid in r["previous_ids"] or uid in r["next_ids"]

    if any(affected(r) for r in registry["relations"][relation_index + 1 :]):
        raise ValueError(
            "publication correction is no longer the latest ID transaction"
        )
    predecessors = [r for r in registry["relations"][:relation_index] if affected(r)]
    if predecessors:
        prior = [
            c["fingerprint"]
            for c in predecessors[-1]["candidates"]
            if c["event_uid"] == uid
        ]
        if len(prior) != 1:
            raise ValueError("correction predecessor is not a continuing ID")
        predecessor = next(
            (o for o in event["observations"] if o["fingerprint"] == prior[0]), None
        )
    else:
        seeds = [
            o
            for o in event["observations"]
            if "published_seed_sha256" in o.get("evidence", {})
        ]
        predecessor = seeds[0] if len(seeds) == 1 else None
    if (
        predecessor is None
        or predecessor["active"]
        or predecessor["identity"] != old_identity
    ):
        raise ValueError(
            "correction must directly follow the pinned old public identity"
        )
    old_sources = {(s["source_id"], s["record_id"]) for s in old["supporting_sources"]}
    if {
        (s["source_id"], s["record_id"]) for s in predecessor["source_records"]
    } != old_sources:
        raise ValueError("correction predecessor provenance differs from baseline")
    new_sources = {(s["source_id"], s["record_id"]) for s in obs["source_records"]}
    if (
        old_sources != new_sources
        or old.get("display_source_id") != "official_events"
        or old.get("display_source_class") != "venue_official"
    ):
        raise ValueError("legacy artist correction cannot change provenance")
    official_ids = [rid for sid, rid in new_sources if sid == "official_events"]
    if len(official_ids) != 1 or official_ids[0] not in official_sources:
        raise ValueError("one current official source required")
    acquisition, detail = official_sources[official_ids[0]]
    if rec["evidence"]["url"] not in {acquisition, detail} or old.get("url") != (
        detail or acquisition
    ):
        raise ValueError("correction evidence must bind the same official detail")
    result = deepcopy(old)
    result["artist_name"] = new_identity["artist_name"]
    if candidate is not None:
        raw = deepcopy(candidate)
        raw["event_key"] = obs["candidate_key"]  # guard receives the resolved fixed ID
        if (
            observation_from_row(raw) != obs
            or source_signature(raw, official_sources) != rec["source_signature"]
        ):
            raise ValueError(
                "current official candidate changed after correction review"
            )
        if (
            raw.get("display_source_id") != "official_events"
            or raw.get("display_source_class") != "venue_official"
            or raw.get("url") != old["url"]
        ):
            raise ValueError("current official display provenance changed")
    return result

"""Apply explicitly reviewed, fixed-ID source selections at LP generation.

This module checks provenance and drift, not reviewer identity or link rights.
The map must be reviewed under the repository's existing change process.
Consumer policy remains the final separate gate. Default generation has no map.
"""

from copy import deepcopy
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from .event_identity_registry import (
    observation_from_row,
    validate_observation,
    parse_json,
    canonical_bytes,
    digest,
)
from .public_lp_projection import (
    embedded_urls, host, project_event, public_row_sha256,
    publication_is_reviewed, validate_publication,
)


class SourceMapError(ValueError):
    pass


def apply_reviewed_source_map(rows, registry, map_bytes, events_db, signals_db=None):
    doc = parse_json(map_bytes)
    if (
        set(doc) != {"schema_version", "records"}
        or type(doc["schema_version"]) is not int
        or doc["schema_version"] != 1
        or not isinstance(doc["records"], list)
    ):
        raise SourceMapError("invalid reviewed source map")
    by_key = {}
    uids = set()
    artist_reviews = {}
    preserved_reviews = {}
    active = {event["event_uid"]: event["observations"] for event in registry["events"]}
    for rec in doc["records"]:
        if isinstance(rec, dict) and "publication" in rec:
            try:
                validate_publication(rec["publication"])
            except ValueError as exc:
                raise SourceMapError(str(exc)) from exc
            rec = {key: value for key, value in rec.items() if key != "publication"}
        if isinstance(rec, dict) and rec.get("mode") == "preserve_source":
            if (
                set(rec) != {"mode", "event_uid", "observation", "source_signature", "fact_review", "public_urls"}
                or not isinstance(rec["event_uid"], str)
                or not rec["event_uid"]
                or rec["fact_review"] != "reviewed"
                or not isinstance(rec["source_signature"], str)
                or not re.fullmatch("[0-9a-f]{64}", rec["source_signature"])
                or not isinstance(rec["public_urls"], list)
                or any(not isinstance(u, str) or not host(u) for u in rec["public_urls"])
                or len(rec["public_urls"]) != len(set(rec["public_urls"]))
            ):
                raise SourceMapError("invalid preserved source review")
            try:
                validate_observation(rec["observation"])
            except (ValueError, TypeError, KeyError) as exc:
                raise SourceMapError("invalid reviewed observation") from exc
            obs = rec["observation"]
            uid = rec["event_uid"]
            if uid in uids or obs["candidate_key"] in by_key:
                raise SourceMapError("duplicate reviewed selection")
            if not any(
                item["active"] and item["fingerprint"] == obs["fingerprint"]
                for item in active.get(uid, [])
            ):
                raise SourceMapError("preserved source review is not bound to active fixed ID")
            uids.add(uid)
            by_key[obs["candidate_key"]] = rec
            preserved_reviews[obs["candidate_key"]] = rec
            continue
        if isinstance(rec, dict) and rec.get("mode") == "artist_source_link":
            fields = {
                "mode",
                "event_uid",
                "candidate_key",
                "fingerprint",
                "source_id",
                "record_id",
                "evidence_url_sha256",
                "fact_review",
            }
            if (
                set(rec) != fields
                or rec["source_id"] != "starto_concert"
                or rec["fact_review"] != "reviewed"
                or any(not isinstance(rec[k], str) or not rec[k] for k in fields)
                or not re.fullmatch("[0-9a-f]{64}", rec["record_id"])
                or not re.fullmatch("[0-9a-f]{64}", rec["fingerprint"])
                or not re.fullmatch("[0-9a-f]{64}", rec["evidence_url_sha256"])
                or rec["event_uid"] in uids
                or rec["candidate_key"] in by_key
            ):
                raise SourceMapError("invalid artist source selection")
            uids.add(rec["event_uid"])
            by_key[rec["candidate_key"]] = rec
            artist_reviews[rec["candidate_key"]] = rec
            if not any(
                item["active"]
                and item["fingerprint"] == rec["fingerprint"]
                and {"source_id": rec["source_id"], "record_id": rec["record_id"]}
                in item["source_records"]
                for item in active.get(rec["event_uid"], [])
            ):
                raise SourceMapError("artist selection is not bound to active fixed ID")
            continue
        if not isinstance(rec, dict) or set(rec) != {
            "event_uid",
            "observation",
            "source",
            "source_class",
            "fact_review",
            "public_urls",
        }:
            raise SourceMapError("invalid reviewed selection")
        uid = rec["event_uid"]
        obs = rec["observation"]
        source = rec["source"]
        try:
            validate_observation(obs)
        except (ValueError, TypeError, KeyError) as exc:
            raise SourceMapError("invalid reviewed observation") from exc
        if not isinstance(uid, str) or uid in uids or obs["candidate_key"] in by_key:
            raise SourceMapError("duplicate reviewed selection")
        uids.add(uid)
        by_key[obs["candidate_key"]] = rec
        if not any(
            item["active"] and item["fingerprint"] == obs["fingerprint"]
            for item in active.get(uid, [])
        ):
            raise SourceMapError("reviewed selection is not bound to active fixed ID")
        if (
            not isinstance(source, dict)
            or set(source) != {"source_id", "record_id", "source_url", "detail_url"}
            or source["source_id"] != "official_events"
            or {"source_id": source["source_id"], "record_id": source["record_id"]}
            not in obs["source_records"]
            or rec["source_class"] != "venue_official"
            or rec["fact_review"] != "reviewed"
            or not isinstance(rec["public_urls"], list)
            or any(not isinstance(u, str) or not host(u) for u in rec["public_urls"])
            or len(rec["public_urls"]) != len(set(rec["public_urls"]))
            or source["source_url"] not in rec["public_urls"]
            or source["detail_url"] not in rec["public_urls"]
            or not isinstance(source["source_url"], str)
            or not host(source["source_url"])
            or not isinstance(source["detail_url"], str)
        ):
            raise SourceMapError("invalid reviewed source or reference")
    result = deepcopy(rows)
    found = set()
    official_sources = read_official_sources(events_db) if preserved_reviews else {}
    con = sqlite3.connect(Path(events_db).resolve().as_uri() + "?mode=ro", uri=True)
    signals = (
        sqlite3.connect(Path(signals_db).resolve().as_uri() + "?mode=ro", uri=True)
        if artist_reviews and signals_db
        else None
    )
    try:
        if artist_reviews and signals is None:
            raise SourceMapError("artist source snapshot required")
        for row in result:
            key = row.get("event_key")
            rec = by_key.get(key)
            if rec is None:
                continue
            if key in preserved_reviews:
                if (
                    key in found
                    or observation_from_row(row) != rec["observation"]
                    or source_signature(row, official_sources) != rec["source_signature"]
                    or not host(row.get("evidence_url"))
                    or not host(row.get("url"))
                    or set(embedded_urls(project_event(row))) != set(rec["public_urls"])
                ):
                    raise SourceMapError("preserved source or public links changed since review")
                if row.get("display_source_id") == "official_events" and not any(
                    item.get("source_id") == "official_events"
                    and (urls := official_sources.get(item.get("record_id")))
                    and (urls[0], urls[1] or urls[0]) == (row["evidence_url"], row["url"])
                    for item in row["supporting_sources"]
                ):
                    raise SourceMapError("preserved source does not retain acquisition URL; use explicit source selection")
                found.add(key)
                # This review pins the existing facts/source/link tuple. It does
                # not rewrite provenance or grant consumer publication rights.
                continue
            if key in artist_reviews:
                obs = observation_from_row(row)
                if (
                    key in found
                    or obs["fingerprint"] != rec["fingerprint"]
                    or {"source_id": rec["source_id"], "record_id": rec["record_id"]}
                    not in obs["source_records"]
                ):
                    raise SourceMapError("artist candidate changed since review")
                found.add(key)
                signal = signals.execute(
                    "select source_id,url,first_seen_at_utc,updated_at_utc,title,labels_json from signals where signal_uid=?",
                    (rec["record_id"],),
                ).fetchone()
                if (
                    not signal
                    or signal[0] != "starto_concert"
                    or host(signal[1]) != "starto.jp"
                    or digest(signal[1].encode("utf-8")) != rec["evidence_url_sha256"]
                ):
                    raise SourceMapError("artist source changed since review")
                try:
                    labels = json.loads(signal[5])
                    info = labels.get("event_info") or ""
                    date_time = re.match(
                        r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*/", info
                    )

                    def compact(text):
                        return re.sub(
                            r"\s+", "", unicodedata.normalize("NFKC", text or "")
                        )

                    if (
                        not date_time
                        or date_time.group(1) != row.get("event_date")
                        or date_time.group(2) != row.get("event_start_time")
                        or labels.get("event_start_date") != row.get("event_date")
                        or labels.get("event_end_date") != row.get("event_end_date")
                        or labels.get("pref_name") != row.get("pref_name")
                        or compact(labels.get("venue_name"))
                        != compact(row.get("venue_name"))
                        or compact(labels.get("artist_name"))
                        != compact(row.get("artist_name"))
                        or signal[4] != row.get("title")
                    ):
                        raise SourceMapError(
                            "selected artist observation does not substantiate candidate facts"
                        )
                except SourceMapError:
                    raise
                except (TypeError, ValueError, AttributeError) as exc:
                    raise SourceMapError("invalid selected artist observation") from exc
                from .build_lp_events import SOURCE_PRIORITY

                row.update(
                    {
                        "display_source_id": "starto_concert",
                        "display_source_class": "artist_official",
                        "display_source_label": "STARTO ENTERTAINMENT",
                        "source_domain": "starto.jp",
                        "source_priority": SOURCE_PRIORITY["starto_concert"],
                        "first_seen_at_utc": signal[2],
                        "updated_at_utc": signal[3],
                        "url": "",
                        "evidence_url": "",
                        "evidence_snippet": "",
                        "supporting_sources": [
                            {
                                "source_id": "starto_concert",
                                "record_id": rec["record_id"],
                            }
                        ],
                    }
                )
                # The explicit map choice selects the recorded source link;
                # other supporting/detail URLs remain absent from this row.
                row["url"] = signal[1]
                row["evidence_url"] = signal[1]
                if any(url != signal[1] for url in embedded_urls(row)):
                    raise SourceMapError("artist event exposes an unselected URL")
                continue
            if key in found or observation_from_row(row) != rec["observation"]:
                raise SourceMapError("candidate changed since source review")
            found.add(key)
            source = rec["source"]
            if (
                row.get("display_source_id") != source["source_id"]
                or row.get("display_source_class") != rec["source_class"]
            ):
                raise SourceMapError("source mapping differs from reviewed candidate")
            dbrow = con.execute(
                "select source_url,url from events where event_uid=?",
                (source["record_id"],),
            ).fetchone()
            if dbrow is None or (dbrow[0] or "", dbrow[1] or "") != (
                source["source_url"],
                source["detail_url"],
            ):
                raise SourceMapError("stored source changed since review")
            # Both links require independent explicit decisions. Supporting
            # sources are public too; reject URLs not in that same decision.
            for url in embedded_urls(row["supporting_sources"]):
                if url not in rec["public_urls"]:
                    raise SourceMapError("unreviewed supporting source URL")
            row["url"] = source["detail_url"]
            row["evidence_url"] = source["source_url"]
            for member in row["supporting_sources"]:
                if (
                    member.get("source_id") == source["source_id"]
                    and member.get("record_id") == source["record_id"]
                ):
                    member["evidence_url"] = source["source_url"]
            # The legacy snippet may originate from a different display URL.
            row["evidence_snippet"] = ""
    finally:
        con.close()
        if signals:
            signals.close()
    return result


def source_signature(row, official_sources, *, legacy_row=False):
    """Capture source identity and public URLs without volatile timestamps."""
    members = row.get("supporting_sources")
    if not isinstance(members, list) or any(
        not isinstance(item, dict) for item in members
    ):
        raise SourceMapError("invalid supporting sources")
    stored = {}
    for item in members:
        if item.get("source_id") == "official_events":
            rid = item.get("record_id")
            if rid not in official_sources:
                raise SourceMapError("official source missing from snapshot")
            stored[rid] = list(official_sources[rid])
    return digest(
        canonical_bytes(
            {
                "stored_official_sources": stored,
                "public_row_sha256": public_row_sha256(row, include_event_key=False,
                    mode="legacy" if legacy_row else "reviewed"),
                "display_source_id": row.get("display_source_id"),
                "display_source_class": row.get("display_source_class"),
                "url": row.get("url"),
                "evidence_url": row.get("evidence_url"),
                "sources": sorted(
                    (
                        {
                            "source_id": item.get("source_id"),
                            "record_id": item.get("record_id"),
                            "embedded_urls": sorted(embedded_urls(item)),
                        }
                        for item in project_event(row)["supporting_sources"]
                    ),
                    key=canonical_bytes,
                ),
            }
        )
    )


def guard_new_ids(
    rows, map_bytes, baseline_bytes, applied_candidate_keys, official_sources,
    *, reviewed_event_uids=None, registry=None, retained_changes=None,
    failed_source_uids=frozenset(),
) -> set[str]:
    """Hold new IDs; v5 can retain verified old rows without accepting drift."""
    baseline = publication_baseline(baseline_bytes)
    selection = parse_json(map_bytes)
    if (
        set(baseline) - {"published_rows", "published_rows_sha256"} != {"schema_version", "asset_sha256", "event_sources"}
        or type(baseline["schema_version"]) is not int
        or baseline["schema_version"] not in {4, 5}
        or not isinstance(baseline["asset_sha256"], str)
        or len(baseline["asset_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in baseline["asset_sha256"])
        or not isinstance(baseline["event_sources"], dict)
        or any(
            not isinstance(uid, str)
            or not uid
            or not isinstance(sh, str)
            or len(sh) != 64
            or any(c not in "0123456789abcdef" for c in sh)
            for uid, sh in baseline["event_sources"].items()
        )
    ):
        raise SourceMapError("invalid verified publication baseline")
    reviewed = {
        rec["event_uid"]: rec
        for rec in selection["records"]
        if (
            rec.get("candidate_key")
            if rec.get("mode") == "artist_source_link"
            else rec["observation"]["candidate_key"]
        )
        in applied_candidate_keys
    }
    held = set()
    for index, row in enumerate(rows):
        uid = row["event_key"]
        publication_changed = False
        if uid in reviewed and uid not in failed_source_uids:
            try:
                if publication_is_reviewed(reviewed[uid], row):
                    if reviewed_event_uids is not None:
                        reviewed_event_uids.add(uid)
                    continue
            except ValueError as exc:
                if baseline["schema_version"] == 4:
                    raise SourceMapError(str(exc)) from exc
                publication_changed = True
        if uid not in baseline["event_sources"]:
            held.add(uid)
            continue
        try:
            changed = source_signature(row, official_sources, legacy_row=True) != baseline["event_sources"][uid]
        except ValueError:
            changed = True
        if changed or publication_changed or uid in failed_source_uids:
            if baseline["schema_version"] == 4 or registry is None or retained_changes is None:
                raise SourceMapError("existing ID source or public link changed")
            from .event_identity_registry import identity_from_row, validate_resolved_rows
            old = baseline["published_rows"][uid]
            if identity_from_row(old) != identity_from_row(row):
                raise SourceMapError("cannot retain an existing ID with changed identity")
            try:
                validate_resolved_rows([old], registry)
            except ValueError as exc:
                raise SourceMapError("previous publication no longer binds to active identity") from exc
            retained_changes.append(deepcopy(row))
            rows[index] = deepcopy(old)
    return held


def publication_baseline(raw):
    """v5 adds exact previous public rows; checksums are not authentication."""
    baseline = parse_json(raw)
    if not isinstance(baseline, dict):
        raise SourceMapError("invalid verified publication baseline")
    version = baseline.get("schema_version")
    if version not in {4, 5} or type(version) is not int:
        raise SourceMapError("invalid verified publication baseline")
    if version == 4:
        if set(baseline) != {"schema_version", "asset_sha256", "event_sources"}:
            raise SourceMapError("invalid verified publication baseline")
    else:
        if (set(baseline) != {"schema_version", "asset_sha256", "event_sources", "published_rows", "published_rows_sha256"}
                or not isinstance(baseline["event_sources"], dict)
                or not isinstance(baseline["published_rows"], dict)
                or set(baseline["published_rows"]) != set(baseline["event_sources"])
                or digest(canonical_bytes(baseline["published_rows"])) != baseline["published_rows_sha256"]):
            raise SourceMapError("invalid retained publication rows")
        from .public_lp_projection import legacy_event
        for uid, row in baseline["published_rows"].items():
            if not isinstance(row, dict) or row.get("event_key") != uid:
                raise SourceMapError("invalid retained publication identity")
            legacy_event(row)
    return baseline


def reviewed_rows_for_publication(rows, registry, map_bytes, baseline_bytes, events_db, signals_db):
    """Validate the complete map first; isolate stale row choices only on v5."""
    baseline = publication_baseline(baseline_bytes)
    if baseline["schema_version"] == 4:
        return apply_reviewed_source_map(rows, registry, map_bytes, events_db, signals_db), set()
    # Empty rows still exercise all schema, duplicate and active-ID checks.
    apply_reviewed_source_map([], registry, map_bytes, events_db, signals_db)
    doc = parse_json(map_bytes)
    records = {(r["candidate_key"] if r.get("mode") == "artist_source_link" else r["observation"]["candidate_key"]): r
               for r in doc["records"]}
    result, failed = [], set()
    for row in rows:
        rec = records.get(row["event_key"])
        if rec is None:
            result.append(deepcopy(row))
            continue
        try:
            result.extend(apply_reviewed_source_map([row], registry,
                canonical_bytes({"schema_version": 1, "records": [rec]}), events_db, signals_db))
        except ValueError:
            # Preserve the raw candidate for the guard. It cannot use the
            # failed choice as a publication approval, even if URLs coincide.
            result.append(deepcopy(row))
            failed.add(rec["event_uid"])
    return result, failed


def baseline_from_asset(asset_bytes, expected_sha256, official_sources, *, retain_published_rows=False):
    """Capture approved prior source fields; hash does not authenticate origin."""
    if digest(asset_bytes) != expected_sha256:
        raise SourceMapError("baseline asset hash mismatch")
    asset = parse_json(asset_bytes)
    if asset.get("history_scope") != "all_verified_retained" or not isinstance(
        asset.get("events"), list
    ):
        raise SourceMapError("baseline requires verified all-dates event asset")
    ids = [row.get("event_key") for row in asset["events"] if isinstance(row, dict)]
    if (
        len(ids) != len(asset["events"])
        or not ids
        or any(not isinstance(uid, str) or not uid for uid in ids)
        or len(ids) != len(set(ids))
    ):
        raise SourceMapError("invalid baseline event IDs")
    result = {
        "schema_version": 5 if retain_published_rows else 4,
        "asset_sha256": expected_sha256,
        "event_sources": {
            row["event_key"]: source_signature(row, official_sources, legacy_row=True)
            for row in asset["events"]
        },
    }
    if retain_published_rows:
        result["published_rows"] = {row["event_key"]: deepcopy(row) for row in asset["events"]}
        result["published_rows_sha256"] = digest(canonical_bytes(result["published_rows"]))
    return result


def read_official_sources(events_db):
    con = sqlite3.connect(Path(events_db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return {
            uid: (url or "", detail or "")
            for uid, url, detail in con.execute(
                "select event_uid,source_url,url from events"
            )
        }
    finally:
        con.close()


def extend_publication_baseline(previous_bytes, asset_bytes, expected_sha256, official_sources, approved_new_ids):
    """Add an exact reviewed ID set without blessing drift in existing sources."""
    previous = publication_baseline(previous_bytes)
    if previous["schema_version"] != 5 or digest(asset_bytes) != expected_sha256:
        raise SourceMapError("verified v5 baseline and approved asset hash required")
    asset = parse_json(asset_bytes)
    if asset.get("history_scope") != "all_verified_retained" or not isinstance(asset.get("events"), list):
        raise SourceMapError("approved all-dates asset required")
    rows = {row["event_key"]: row for row in asset["events"]}
    if (len(rows) != len(asset["events"]) or not approved_new_ids
            or len(set(approved_new_ids)) != len(approved_new_ids)
            or set(previous["published_rows"]) - set(rows)
            or set(rows) - set(previous["published_rows"]) != set(approved_new_ids)):
        raise SourceMapError("baseline extension must match the exact reviewed new ID set")
    from .public_lp_projection import legacy_event
    result = deepcopy(previous)
    for uid, row in rows.items():
        legacy_event(row)
        if uid in previous["published_rows"]:
            if public_row_sha256(row, mode="legacy") != public_row_sha256(previous["published_rows"][uid], mode="legacy"):
                raise SourceMapError("baseline extension changed an existing public row")
            # Keep the old source signature even if the current DB has changed.
        else:
            result["event_sources"][uid] = source_signature(row, official_sources, legacy_row=True)
        result["published_rows"][uid] = deepcopy(row)
    result["asset_sha256"] = expected_sha256
    result["published_rows_sha256"] = digest(canonical_bytes(result["published_rows"]))
    return result


def main():
    """Create a private candidate baseline from verified same-generation assets."""
    import argparse
    import json
    from .event_identity_registry import atomic_write

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--asset-sha256", required=True)
    parser.add_argument("--events-db", type=Path, required=True)
    parser.add_argument("--events-db-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retain-published-rows", action="store_true", help="v5: retain verified old public rows while changed candidates await review.")
    parser.add_argument("--previous-baseline", type=Path, help="Extend an existing v5 baseline for an exact reviewed new ID set.")
    parser.add_argument("--approved-id", action="append", default=[])
    args = parser.parse_args()
    if bool(args.previous_baseline) != bool(args.approved_id):
        parser.error("previous baseline and exact reviewed new IDs must be provided together")
    if args.output.resolve() in {args.asset.resolve(), args.events_db.resolve(), *([args.previous_baseline.resolve()] if args.previous_baseline else [])}:
        raise SourceMapError("output aliases input")
    wal = Path(str(args.events_db) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise SourceMapError("use an immutable consistent DB snapshot")
    db_sha = digest(args.events_db.read_bytes())
    if db_sha != args.events_db_sha256:
        raise SourceMapError("events DB hash mismatch")
    if args.previous_baseline:
        previous = args.previous_baseline.read_bytes()
        result = extend_publication_baseline(previous, args.asset.read_bytes(), args.asset_sha256,
            read_official_sources(args.events_db), args.approved_id)
        if args.previous_baseline.read_bytes() != previous:
            raise SourceMapError("previous baseline changed during extension")
    else:
        result = baseline_from_asset(
            args.asset.read_bytes(), args.asset_sha256, read_official_sources(args.events_db),
            retain_published_rows=args.retain_published_rows,
        )
    if digest(args.events_db.read_bytes()) != db_sha or (
        wal.exists() and wal.stat().st_size
    ):
        raise SourceMapError("events DB changed during baseline generation")
    atomic_write(
        args.output,
        (
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode(),
        replace=False,
    )


if __name__ == "__main__":
    main()

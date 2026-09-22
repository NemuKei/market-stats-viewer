from copy import deepcopy
from datetime import date

import pytest

from scripts.event_corrections import digest, prepare_correction
from scripts.ticketjam_discovery import build_discovery_bundle
from scripts.signals.sources.base import compute_signal_uid

BASE = "a" * 40


def record(source, key, time="19:00"):
    return dict(
        source_id=source,
        record_id=key,
        event_date="2030-12-01",
        event_end_date="2030-12-01",
        event_start_time=time,
        event_status="scheduled",
        venue_name="試験アリーナ",
        artist_name="試験出演者",
        title="試験公演",
        pref_name="沖縄県",
        source_class="venue_official",
        url="https://official.example/event",
        evidence_url="https://official.example/event",
        evidence_snippet="Official test fixture",
        content_extractor="requests_bs4",
    )


def case():
    old = record("official_events", "old")
    evening = record("official_events", "evening", "21:00")
    records = [old, evening]
    payload = build_discovery_bundle(records, as_of_date=date(2030, 9, 21))[0]
    target = next(r for r in payload["events"] if r["event_start_time"] == "19:00")
    values = {
        k: target.get(k)
        for k in (
            "event_date",
            "event_end_date",
            "event_start_time",
            "venue_name",
            "artist_name",
            "title",
        )
    }
    event = dict(
        event_id="corrected",
        event_start_date="2030-12-01",
        event_start_time="18:30",
        **{
            k: old[k]
            for k in (
                "venue_name",
                "artist_name",
                "title",
                "pref_name",
                "url",
                "evidence_url",
                "evidence_snippet",
                "source_class",
                "content_extractor",
            )
        },
    )
    proposal = dict(
        current_values=values,
        event_key=target["event_key"],
        candidate_fingerprint=digest(target),
    )
    snapshot = dict(
        base_commit=BASE, records=records, records_fingerprint=digest(records)
    )
    published = dict(payload=payload, lp_fingerprint=digest(payload))
    receipt = dict(origin_kind="published_event")
    proof = prepare_correction(
        proposal, event, receipt, snapshot, published, None, BASE
    )
    row = dict(
        old,
        source_id="venue_web_discovery",
        record_id=compute_signal_uid(
            "venue_web_discovery", event["url"], extra_key=event["event_id"]
        ),
        event_start_time="18:30",
        discovery_event_key="",
        date_time_correction=proof,
    )
    return records, row, (proposal, event, receipt, snapshot, published, None, BASE)


@pytest.mark.parametrize(
    "mutation",
    ["changed_old", "new_old_uid", "changed_replacement", "bad_hash", "overlap"],
)
def test_changed_inputs_stop_correction_instead_of_publishing_two_dates(mutation):
    records, row, _ = case()
    if mutation == "changed_old":
        records[0]["evidence_snippet"] = "Official notice changed"
    elif mutation == "new_old_uid":
        records.append(dict(records[0], record_id="newly_discovered_stale_row"))
    elif mutation == "changed_replacement":
        row["event_start_time"] = "17:00"
    elif mutation == "bad_hash":
        row["date_time_correction"]["input_records_fingerprint"] = "unknown"
    else:
        row["date_time_correction"]["retired_records"] *= 2
    before = deepcopy(records + [row])
    with pytest.raises(ValueError):
        build_discovery_bundle(records + [row], as_of_date=date(2030, 9, 21))
    assert records + [row] == before


def test_fetch_timestamp_changes_do_not_resurrect_old_rows():
    records, row, _ = case()
    records[0]["updated_at_utc"] = "2030-09-22T00:00:00Z"
    after = build_discovery_bundle(records + [row], as_of_date=date(2030, 9, 21))[0]
    assert {r["event_start_time"] for r in after["events"]} == {"18:30", "21:00"}
    # An aged-out original is already absent and need not halt every later daily run.
    after = build_discovery_bundle(records[1:] + [row], as_of_date=date(2030, 9, 21))[0]
    assert len(after["events"]) == 2


@pytest.mark.parametrize(
    "mutation",
    ["base", "records_hash", "lp_snapshot", "shared_unknown_time", "invalid_proof"],
)
def test_preview_requires_current_unambiguous_source_snapshot(mutation):
    _, _, args = case()
    p, e, r, s, lp, state, base = deepcopy(args)
    if mutation == "base":
        s["base_commit"] = "b" * 40
    elif mutation == "records_hash":
        s["records"][0]["title"] = "Changed after snapshot"
    elif mutation == "lp_snapshot":
        lp["payload"]["events"][0]["title"] = "Other published version"
    elif mutation == "invalid_proof":
        s["records"][0]["date_time_correction"] = {"schema_version": 1}
        s["records_fingerprint"] = digest(s["records"])
    else:
        s["records"].append(record("starto_concert", "shared", None))
        s["records_fingerprint"] = digest(s["records"])
        payload = build_discovery_bundle(s["records"], as_of_date=date(2030, 9, 21))[0]
        lp = dict(payload=payload, lp_fingerprint=digest(payload))
    with pytest.raises(ValueError):
        prepare_correction(p, e, r, s, lp, state, base)


def test_second_correction_requires_new_migration_review():
    records, row, args = case()
    records.append(row)
    payload = build_discovery_bundle(records, as_of_date=date(2030, 9, 21))[0]
    target = next(r for r in payload["events"] if r["event_start_time"] == "18:30")
    proposal, event, receipt, _, _, state, base = deepcopy(args)
    proposal.update(
        current_values=target,
        event_key=target["event_key"],
        candidate_fingerprint=digest(target),
    )
    event.update(event_id="corrected-again", event_start_time="18:00")
    snapshot = dict(
        base_commit=base, records=records, records_fingerprint=digest(records)
    )
    published = dict(payload=payload, lp_fingerprint=digest(payload))
    with pytest.raises(ValueError, match="chained correction"):
        prepare_correction(proposal, event, receipt, snapshot, published, state, base)

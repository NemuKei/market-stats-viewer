import pytest

from scripts.validate_external_events import validate_payload


def payload():
    return {
        "schema_version": 1,
        "as_of_date": "2026-09-08",
        "ticketjam_policy": "discovery",
        "summary": {
            "event_count": 1,
            "counts_by_display_source": {"official_events": 1},
        },
        "events": [
            {
                "event_key": "one",
                "display_source_id": "official_events",
                "event_date": "2026-09-20",
                "venue_name": "Hall",
                "pref_name": "東京都",
                "artist_name": "Artist",
                "title": "Concert",
                "url": "https://venue.example/event",
                "event_start_time": "18:00",
            }
        ],
    }


def test_secondary_display_is_rejected_even_if_policy_label_is_discovery():
    p = payload()
    p["events"][0]["display_source_id"] = "ticketjam_events"
    with pytest.raises(ValueError, match="source"):
        validate_payload(p)


def test_counts_keys_and_expected_date_are_checked():
    assert validate_payload(payload(), expected_date="2026-09-08")["event_count"] == 1
    p = payload()
    p["events"].append(p["events"][0])
    with pytest.raises(ValueError):
        validate_payload(p)
    with pytest.raises(ValueError, match="date"):
        validate_payload(payload(), expected_date="2026-09-09")


def test_package_validator_detects_changed_asset_bytes(tmp_path):
    import json
    import sqlite3
    from scripts.build_external_events_manifest import _build_manifest
    from scripts.validate_external_events import validate_package

    for name in ["events.sqlite", "event_signals.sqlite"]:
        connection = sqlite3.connect(tmp_path / name)
        connection.execute("create table sample (id integer)")
        connection.close()
    path = tmp_path / "lp_events.json"
    path.write_text(json.dumps(payload()))
    manifest = _build_manifest(tmp_path, "external-events-latest")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert validate_package(tmp_path)["event_count"] == 1
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="manifest mismatch"):
        validate_package(tmp_path)


def test_missing_prefecture_cannot_silently_disappear_from_public_search():
    p = payload()
    del p["events"][0]["pref_name"]
    with pytest.raises(ValueError, match="prefecture"):
        validate_payload(p)

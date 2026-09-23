import pytest

from scripts.validate_external_events import validate_payload


def payload():
    return {
        "schema_version": 1,
        "as_of_date": "2026-09-08",
        "source_priority": ["official_events", "venue_web_discovery", "starto_concert", "kstyle_music"],
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


def test_secondary_display_is_rejected():
    p = payload()
    p["events"][0]["display_source_id"] = "ticketjam_events"
    with pytest.raises(ValueError, match="source"):
        validate_payload(p)


def test_ticketjam_in_source_priority_is_rejected():
    p = payload()
    p["source_priority"].append("ticketjam_events")
    with pytest.raises(ValueError, match="ticketjam must not be a publication source"):
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


def test_lp_events_only_cli_rejects_summary_row_mismatch(tmp_path, capsys):
    import json
    from scripts.validate_external_events import main

    path = tmp_path / "lp_events.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    assert main(["--lp-events", str(path)]) == 0
    assert '"valid": true' in capsys.readouterr().out

    # Shape left by `git pull --rebase -X ours`: summary from one build, rows from both.
    mixed = payload()
    extra = dict(mixed["events"][0], event_key="two", display_source_id="venue_web_discovery", display_source_class="venue_official")
    mixed["events"].append(extra)
    path.write_text(json.dumps(mixed), encoding="utf-8")
    with pytest.raises(ValueError, match="summary does not match rows"):
        main(["--lp-events", str(path)])

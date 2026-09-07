import json
from pathlib import Path

import requests

from scripts.signals.sources.venue_web_discovery import VenueWebDiscoverySource
from scripts.signals.types import SignalSourceRecord


def test_venue_web_discovery_loads_only_accepted_confirmed_events(tmp_path: Path):
    config_path = tmp_path / "venue_web_discovery_config.json"
    config_path.write_text(
        json.dumps(
            {
                "future_only": False,
                "accepted_source_classes": ["artist_official"],
                "rejected_source_classes": ["general_news"],
                "confirmed_events": [
                    {
                        "event_id": "accepted",
                        "title": "Stray Kids World Tour <RUN IT JAPAN>",
                        "artist_name": "Stray Kids",
                        "venue_name": "京セラドーム大阪",
                        "event_start_date": "2026-09-19",
                        "source_class": "artist_official",
                        "content_extractor": "crawl4ai",
                        "confidence": "high",
                        "url": "https://www.straykidsjapan.com/runitjapan/",
                        "evidence_url": "https://www.straykidsjapan.com/runitjapan/",
                        "evidence_snippet": "Official special site lists OSAKA 京セラドーム大阪 on 2026.09.19-20.",
                        "announced_at_utc": "2026-06-23T00:00:00Z",
                    },
                    {
                        "event_id": "disabled-without-status",
                        "enabled": False,
                        "title": "Disabled event without authoritative status",
                        "artist_name": "Disabled Artist",
                        "venue_name": "京セラドーム大阪",
                        "event_start_date": "2026-09-20",
                        "source_class": "artist_official",
                        "url": "https://example.com/disabled",
                        "evidence_url": "https://example.com/disabled",
                        "evidence_snippet": "This row is disabled but not postponed or cancelled.",
                    },
                    {
                        "event_id": "officially-postponed",
                        "enabled": False,
                        "event_status": "postponed",
                        "title": "Postponed official event",
                        "artist_name": "Postponed Artist",
                        "venue_name": "京セラドーム大阪",
                        "event_start_date": "2026-09-21",
                        "source_class": "artist_official",
                        "url": "https://example.com/postponed",
                        "evidence_url": "https://example.com/postponed",
                        "evidence_snippet": "The artist official page says this event is postponed.",
                    },
                    {
                        "event_id": "officially-cancelled",
                        "enabled": False,
                        "event_status": "cancelled",
                        "title": "Cancelled official event",
                        "artist_name": "Cancelled Artist",
                        "venue_name": "京セラドーム大阪",
                        "event_start_date": "2026-09-21",
                        "source_class": "artist_official",
                        "url": "https://example.com/cancelled",
                        "evidence_url": "https://example.com/cancelled",
                        "evidence_snippet": "The artist official page says this event is cancelled.",
                    },
                    {
                        "event_id": "rejected-news",
                        "title": "News-only event",
                        "artist_name": "Example",
                        "venue_name": "京セラドーム大阪",
                        "event_start_date": "2026-09-22",
                        "source_class": "general_news",
                        "url": "https://example.com/news",
                        "evidence_url": "https://example.com/news",
                        "evidence_snippet": "news only",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source = SignalSourceRecord(
        source_id="venue_web_discovery",
        source_name="Venue Web Discovery",
        source_url=str(config_path),
        source_type="codex_web_discovery",
        config_json=json.dumps({"config_path": str(config_path)}, ensure_ascii=False),
        is_enabled=True,
    )

    records = VenueWebDiscoverySource(requests.Session()).fetch_signals(source)

    assert len(records) == 3
    by_title = {record.title: record for record in records}

    accepted_labels = json.loads(
        by_title["Stray Kids World Tour <RUN IT JAPAN>"].labels_json or "{}"
    )
    assert accepted_labels["source_class"] == "artist_official"
    assert accepted_labels["content_extractor"] == "crawl4ai"
    assert accepted_labels["event_start_date"] == "2026-09-19"
    assert accepted_labels["artist_name"] == "Stray Kids"
    assert "event_status" not in accepted_labels

    postponed_labels = json.loads(
        by_title["Postponed official event"].labels_json or "{}"
    )
    assert postponed_labels["event_status"] == "postponed"
    assert postponed_labels["source_class"] == "artist_official"
    cancelled_labels = json.loads(
        by_title["Cancelled official event"].labels_json or "{}"
    )
    assert cancelled_labels["event_status"] == "cancelled"
    assert cancelled_labels["source_class"] == "artist_official"
    assert "Disabled event without authoritative status" not in by_title
    assert "News-only event" not in by_title


def test_browser_observed_official_calendar_retains_its_evidence_method():
    plugin = VenueWebDiscoverySource(requests.Session())
    event = {'event_id': 'calendar', 'title': 'Calendar concert', 'artist_name': 'Artist',
             'venue_name': 'Hall', 'event_start_date': '2026-11-06', 'event_start_time': '18:00',
             'source_class': 'promoter_official', 'content_extractor': 'browser',
             'url': 'https://official.example/ticket/', 'evidence_url': 'https://official.example/calendar.svg',
             'evidence_snippet': 'Official visual timetable shows November 6 at 18:00.'}
    result = plugin._event_to_signal(source_id='venue_web_discovery', event=event,
        accepted_source_classes={'promoter_official'}, rejected_source_classes=set(),
        future_only=False, today_iso='2026-09-08')
    assert json.loads(result.labels_json)['content_extractor'] == 'browser'


def test_confirmed_venue_supplies_missing_prefecture_for_public_search():
    plugin = VenueWebDiscoverySource(requests.Session())
    event = {'event_id': 'osaka', 'title': 'Concert', 'artist_name': 'Artist',
             'venue_name': 'Zepp Namba(Osaka)', 'event_start_date': '2026-09-13',
             'source_class': 'venue_official', 'url': 'https://www.zepp.co.jp/hall/namba/schedule/',
             'evidence_snippet': 'Official schedule confirms the event.'}
    result = plugin._event_to_signal(source_id='venue_web_discovery', event=event,
        accepted_source_classes={'venue_official'}, rejected_source_classes=set(),
        future_only=False, today_iso='2026-09-08')
    assert json.loads(result.labels_json)['pref_name'] == '大阪府'


def test_conflicting_explicit_prefecture_is_not_silently_replaced():
    import pytest
    plugin = VenueWebDiscoverySource(requests.Session())
    event = {'event_id': 'conflict', 'title': 'Concert', 'artist_name': 'Artist',
             'venue_name': 'Zepp Namba(Osaka)', 'pref_name': '東京都', 'event_start_date': '2026-09-13',
             'source_class': 'venue_official', 'url': 'https://www.zepp.co.jp/hall/namba/schedule/',
             'evidence_snippet': 'Official schedule confirms the event.'}
    with pytest.raises(ValueError, match='prefecture conflicts'):
        plugin._event_to_signal(source_id='venue_web_discovery', event=event,
            accepted_source_classes={'venue_official'}, rejected_source_classes=set(),
            future_only=False, today_iso='2026-09-08')

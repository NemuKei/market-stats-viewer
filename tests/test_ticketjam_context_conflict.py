import json

import requests

from scripts.signals.sources.ticketjam import TicketjamEventsSource


def fetch(context):
    source = TicketjamEventsSource(requests.Session())
    response = requests.Response()
    response.status_code = 200
    body = "<h1>広島 vs 清水 10/24(土) 14:00 エディオンピースウイング広島</h1>"
    body += (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "SportsEvent",
                "name": "広島 vs 清水",
                "startDate": "2026-10-24T14:00:00+09:00",
                "performer": {"name": "サンフレッチェ広島"},
                "location": {
                    "name": "エディオンピースウイング広島",
                    "address": {"addressRegion": "広島県"},
                },
            }
        )
        + "</script>"
    )
    response._content = body.encode()
    source._get_with_retry = lambda *args, **kwargs: response
    return source._fetch_event_signal(
        "ticketjam_events",
        "https://ticketjam.jp/tickets/sanfrecce/event/1269543",
        15,
        0,
        min_event_date="2026-09-07",
        future_only=True,
        allowed_event_types={"SportsEvent"},
        candidate_context=context,
    )


def test_venue_context_cannot_override_conflicting_event_headline():
    assert (
        fetch(
            {
                "venue_name": "大阪府立体育会館（エディオンアリーナ大阪）",
                "pref_name": "大阪府",
                "event_start_date": "2026-10-24",
            }
        )
        is None
    )


def test_consistent_context_retains_event():
    result = fetch(
        {
            "venue_name": "エディオンピースウイング広島",
            "pref_name": "広島県",
            "event_start_date": "2026-10-24",
            "event_start_time": "14:00",
        }
    )
    assert result is not None
    assert (
        json.loads(result.labels_json)["venue_name"] == "エディオンピースウイング広島"
    )


def test_conflicting_date_or_time_is_rejected():
    assert fetch({"event_start_date": "2026-10-25"}) is None
    assert fetch({"event_start_time": "19:00"}) is None


def test_known_venue_aliases_are_not_false_conflicts():
    source = TicketjamEventsSource(requests.Session())
    assert source._context_venues_agree(
        "エディオンアリーナ大阪", "大阪府立体育会館（エディオンアリーナ大阪）"
    )

from types import SimpleNamespace

import pytest

from scripts.events.sources.html import (
    _MufgStadiumSchedule,
    _NissanStadiumCalendar,
    _TokyoDomeCalendar,
)
from scripts.events.types import VenueRecord


class StaticSession:
    def __init__(self, html: str):
        self.response = SimpleNamespace(
            status_code=200,
            text=html,
            apparent_encoding="utf-8",
            encoding="utf-8",
            raise_for_status=lambda: None,
        )

    def get(self, url, timeout=30):
        return self.response


@pytest.mark.parametrize("label,expected", [("19時30分", "19:30"), ("19時", "19:00")])
def test_nissan_preserves_the_minutes_in_japanese_start_time(label, expected):
    venue = VenueRecord(
        "nissan_stadium",
        "日産スタジアム",
        "14",
        "神奈川県",
        72000,
        "https://www.nissan-stadium.jp/",
        "html",
        "https://www.nissan-stadium.jp/calendar/",
        None,
        True,
    )
    session = StaticSession(f"""<table>
        <tr><th>行事名</th><td>横浜F・マリノス vs 水戸ホーリーホック</td></tr>
        <tr><th>期日</th><td>2026年9月19日</td></tr>
        <tr><th>開場</th><td>17時</td></tr>
        <tr><th>開始</th><td>{label}</td></tr>
        </table>""")
    event = _NissanStadiumCalendar()._parse_detail(
        venue,
        session,
        "https://www.nissan-stadium.jp/calendar/detail.php?id=test",
        venue.source_url,
        set(),
    )
    assert event.start_time == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("OPEN15:30 / START17:30", "17:30"),
        ("18:00キックオフ", "18:00"),
        ("開場15:30 お問い合わせ 11:00～18:00", None),
    ],
)
def test_ajinomoto_only_uses_explicit_start_or_kickoff_time(text, expected):
    session = StaticSession(f"<h2>公演</h2><article>{text}</article>")
    title, start_time = _MufgStadiumSchedule._extract_detail_fields(
        session, "https://www.ajinomotostadium.com/schedule/2026/0919_16242.php"
    )
    assert title == "公演"
    assert start_time == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("開場10:30／開始 13:00", "13:00"),
        ("開場 16:30／開演 18:30", "18:30"),
        ("開場 16:30", None),
    ],
)
def test_tokyo_dome_does_not_publish_opening_time_as_start(text, expected):
    assert _TokyoDomeCalendar._extract_time(text) == expected


def test_tokyo_dome_keeps_each_events_time_inside_its_own_block():
    venue = VenueRecord(
        "tokyo_dome",
        "東京ドーム",
        "13",
        "東京都",
        55000,
        "https://www.tokyo-dome.co.jp/",
        "html",
        "https://www.tokyo-dome.co.jp/dome/event/schedule.html",
        None,
        True,
    )
    session = StaticSession("""<p class="c-ttl-set-calender">2026年09月</p>
        <table><tr class="c-mod-calender__item">
        <td><span class="c-mod-calender__day">08</span></td>
        <td class="c-mod-calender__detail">
          <div class="c-mod-calender__detail-in">
            <a href="/dome/visit/">TOKYO DOME TOUR</a>
          </div>
          <div class="c-mod-calender__detail-in">
            <a href="/dome/baseball/giants/">巨人ー中日</a>
            <p>開場 16:00／開始 18:00</p>
          </div>
        </td></tr></table>""")
    events = _TokyoDomeCalendar().parse(venue, session, {})
    assert {event.title: event.start_time for event in events} == {
        "TOKYO DOME TOUR": None,
        "巨人ー中日": "18:00",
    }

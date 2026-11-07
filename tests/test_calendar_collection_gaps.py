"""Regressions from Issue #42; reduced markup from official calendar structures."""

from bs4 import BeautifulSoup

from scripts.events.sources.html import _MakuhariMesseSchedule, _MufgStadiumSchedule
from scripts.events.sources.html import _VantelinDomeSchedule
import pytest
from scripts.events.types import VenueRecord


def venue(uid, url):
    return VenueRecord(
        uid, "味の素スタジアム", "13", "東京都", 49000, url, "html", url, None, True
    )


class Response:
    status_code = 200
    apparent_encoding = "utf-8"
    encoding = "utf-8"

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class Session:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return Response(self.pages[len(self.urls) - 1])


def card(category, title="公演", key="music"):
    return f"""<li class="eventInr"><a href="/event/detail/{key}">
        <div class="rightCont"><div class="category">{category}</div>
        <div class="date">2026.11.21(土)</div><div class="eventTit">{title}</div>
        <div class="target">対象 一般</div></div></a></li>"""


def pager(n):
    return f'<div class="pager"><a href="javascript:pager({n})">{n}</a></div>'


def test_makuhari_follows_page_after_filtered_out_categories():
    session = Session([card("展示会・見本市") + pager(2), card("音楽イベント")])
    rows = _MakuhariMesseSchedule().parse(
        venue("makuhari", "https://www.m-messe.co.jp/event/"),
        session,
        {"months_ahead": 0, "allowed_categories": ["音楽イベント"]},
    )
    assert len(session.urls) == 2
    assert session.urls[1].endswith("&page=2")
    assert [row.title for row in rows] == ["公演"]


def test_makuhari_duplicate_page_does_not_hide_later_programme():
    session = Session(
        [
            card("音楽イベント") + pager(2),
            card("音楽イベント") + pager(3),
            card("音楽イベント", "別公演", "other"),
        ]
    )
    rows = _MakuhariMesseSchedule().parse(
        venue("makuhari", "https://www.m-messe.co.jp/event/"),
        session,
        {"months_ahead": 0, "allowed_categories": ["音楽イベント"]},
    )
    assert len(session.urls) == 3
    assert [r.title for r in rows] == ["公演", "別公演"]


def test_makuhari_pagination_is_bounded_and_does_not_infer_pages_from_digits():
    session = Session([card("展示会") + pager(12)])
    assert (
        _MakuhariMesseSchedule().parse(
            venue("m", "https://www.m-messe.co.jp/event/"),
            session,
            {"months_ahead": 0, "allowed_categories": ["音楽イベント"]},
        )
        == []
    )
    assert len(session.urls) == 1


def test_ajinomoto_requires_main_facility_without_fetching_sibling_details():
    html = "".join(
        f'''<div class="columnBlock03"><h3>{label}</h3>
        <ul class="icon"><li class="{css}">{label}</li></ul>
        <div class="linkWaku"><a href="/schedule/2026/1121_{i}.php">詳細はこちら</a></div></div>'''
        for i, (css, label) in enumerate(
            [
                ("icon01", "味の素スタジアム"),
                ("icon02", "アミノバイタルフィールド"),
                ("icon03", "AGFフィールド"),
                ("iconA", "サッカー"),
            ]
        )
    )
    session = Session(
        ["<h2>FC東京×鹿島アントラーズ</h2><p>開始時間: 15:00 キックオフ</p>"]
    )
    rows = _MufgStadiumSchedule()._parse_month_page(
        venue("mufg_stadium", "https://www.ajinomotostadium.com/schedule"),
        session,
        BeautifulSoup(html, "html.parser"),
        "https://www.ajinomotostadium.com/schedule/2026/11/",
        set(),
    )
    assert len(session.urls) == len(rows) == 1
    assert rows[0].start_time == "15:00"
    assert rows[0].source_url.endswith("/schedule/2026/11/")
    assert rows[0].url.endswith("1121_0.php")
    assert rows[0].event_uid == "mufg_stadium:/schedule/2026/1121_0.php"


def nagoya_table(tab, title, start="17:00", day="12/6"):
    return f"""<div class="events" id="tabs-{tab}"><table><tr>
        <td>{day}</td><td>15:00</td><td>{start}</td><td>19:00</td>
        <td colspan="2"><p class="eventname"><a href="https://artist.example/{title}">{title}</a></p></td>
        </tr></table></div>"""


def test_nagoya_uses_source_year_for_archives_current_and_next_year_not_today():
    labels = '<div class="tabYear"/>2025年</div><div class="tabYear"/>2026年</div><div class="tabYear"/>2027年</div>'
    html = (
        labels
        + nagoya_table(11, "前年公演")
        + nagoya_table(23, "今年公演")
        + nagoya_table(35, "来年公演")
    )
    rows = _VantelinDomeSchedule().parse(
        venue("vantelin_dome_nagoya", "https://www.nagoya-dome.co.jp/enjoy/index.php"),
        Session([html]),
        {},
    )
    assert [(r.title, r.start_date, r.start_time) for r in rows] == [
        ("前年公演", "2025-12-06", "17:00"),
        ("今年公演", "2026-12-06", "17:00"),
        ("来年公演", "2027-12-06", "17:00"),
    ]
    assert "#d=2025-12-06#t=17:00" in rows[0].event_uid


def test_nagoya_unknown_calendar_year_fails_and_missing_start_never_uses_doors_or_end():
    source = _VantelinDomeSchedule()
    v = venue("vantelin_dome_nagoya", "https://www.nagoya-dome.co.jp/enjoy/index.php")
    with pytest.raises(ValueError, match="calendar years"):
        source.parse(v, Session([nagoya_table(11, "年不明")]), {})
    rows = source.parse(
        v,
        Session(
            [
                '<div class="tabYear">2026年</div>'
                + nagoya_table(11, "開始未定", start="")
            ]
        ),
        {},
    )
    assert rows[0].start_time is None
    assert (
        source.parse(
            v,
            Session(
                [
                    '<div class="tabYear">2026年</div>'
                    + nagoya_table(11, "月矛盾", day="11/6")
                ]
            ),
            {},
        )
        == []
    )

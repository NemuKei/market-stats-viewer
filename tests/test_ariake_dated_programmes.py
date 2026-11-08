"""Ariake dated sessions: reduced markup from the official venue calendar."""

from bs4 import BeautifulSoup
import pytest

from scripts.events.sources.html import _AriakeArenaSchedule
from scripts.events.types import VenueRecord


def parse(days, times, *, year=2026, month=12, issues=None, counter=None):
    html = f"""<ul class="event_detail_list"><li id="detail-338">
    <div class="event_day">{"".join("<span>" + d + "</span>" for d in days)}</div>
    <div class="event_name">出演者</div><table class="detail_table"><tr>
    <th>公演時間</th><td>{times}</td></tr></table>
    <a class="other_link" href="https://artist.example/tour">公式</a></li></ul>"""
    venue = VenueRecord(
        "ariake_arena",
        "有明アリーナ",
        "13",
        "東京都",
        15000,
        "https://ariake-arena.tokyo/",
        "html",
        "https://ariake-arena.tokyo/event/",
        None,
        True,
    )
    return _AriakeArenaSchedule()._parse_page(
        venue,
        BeautifulSoup(html, "html.parser"),
        venue.source_url,
        year,
        month,
        set(),
        note_issue=counter or ((lambda: issues.append("ambiguous_dated_programme")) if issues is not None else None),
    )


def test_date_specific_start_does_not_copy_first_day_or_opening_time():
    rows = parse(
        ["12.5 SAT", "12.6 SUN"],
        "12.5 Sat 開場15:30 / 開演17:00<br>12.6 Sun 開場15:00 / 開演16:30",
    )
    assert [(r.start_date, r.end_date, r.start_time) for r in rows] == [
        ("2026-12-05", None, "17:00"),
        ("2026-12-06", None, "16:30"),
    ]
    # Reuse the old raw source key for the first session, replacing the old
    # aggregate on upsert. Other days have stable keys independent of clock.
    assert [r.event_uid for r in rows] == [
        "ariake_arena:detail-338",
        "ariake_arena:detail-338#d=2026-12-06",
    ]
    changed = parse(
        ["12.5 SAT", "12.6 SUN"], "12.5 Sat 開演17:00<br>12.6 Sun 開演16:00"
    )
    assert changed[1].event_uid == rows[1].event_uid
    assert changed[1].data_hash != rows[1].data_hash
    assert rows[1].source_url == "https://ariake-arena.tokyo/event/"
    assert rows[1].url == "https://artist.example/tour"


@pytest.mark.parametrize("prefix", ["", "1/30 "])
def test_slash_between_clocks_is_not_a_calendar_date(prefix):
    rows = parse(["1.30 SAT"], prefix + "開演13:00/18:30", year=2027, month=1)
    assert [(r.start_date, r.start_time) for r in rows] == [
        ("2027-01-30", "13:00"), ("2027-01-30", "18:30")
    ]


@pytest.mark.parametrize("times", ["①開演13:00 ②開演18:30", "開演13:00/18:30"])
def test_second_session_clock_change_updates_the_same_raw_record(tmp_path, times):
    from scripts.update_events_data import init_db, upsert_events

    before = parse(["12.5 SAT"], times)
    after = parse(["12.5 SAT"], times.replace("18:30", "19:00"))
    with init_db(tmp_path / "events.sqlite") as conn:
        upsert_events(conn, before, {}, {})
        upsert_events(conn, after, {}, {})
        rows = conn.execute("select start_time from events order by start_time").fetchall()
    assert [r[0] for r in rows] == ["13:00", "19:00"]
    assert before[1].event_uid == after[1].event_uid


def test_explicit_second_session_never_reuses_missing_first_session_key():
    before = parse(["12.5 SAT"], "①開演13:00 ②開演18:30")
    remaining = parse(["12.5 SAT"], "②開演18:30")
    assert remaining[0].event_uid == before[1].event_uid
    assert remaining[0].event_uid != before[0].event_uid


def test_equal_clocks_under_different_session_numbers_require_review():
    issues = []
    assert parse(["12.5 SAT"], "①開演13:00 ②開演13:00", issues=issues) == []
    assert issues == ["ambiguous_dated_programme"]


@pytest.mark.parametrize("times", ["①開演未定 ②開演18:30", "①開演未定 ②開演未定"])
def test_unknown_clock_in_multiple_sessions_is_held_before_lp_can_collapse_it(times):
    issues = []
    assert parse(["12.5 SAT"], times, issues=issues) == []
    assert issues == ["ambiguous_dated_programme"]


def test_range_uses_explicit_dated_sessions_and_keeps_matinees():
    rows = parse(
        ["1.28 THU -", "1.31 SUN"],
        """1.28 Thu 開演18:30<br>
        1.29 Fri 開演18:30<br>1.30 Sat ①開場12:00 / 開演13:00<br>
        ②開場17:30 / 開演18:30<br>1.31 Sun ①開演13:00 ②開演18:30""",
        year=2027,
        month=1,
    )
    assert [(r.start_date, r.start_time) for r in rows] == [
        ("2027-01-28", "18:30"),
        ("2027-01-29", "18:30"),
        ("2027-01-30", "13:00"),
        ("2027-01-30", "18:30"),
        ("2027-01-31", "13:00"),
        ("2027-01-31", "18:30"),
    ]
    assert len({r.event_uid for r in rows}) == 6
    assert all(r.end_date is None for r in rows)


def test_nonconsecutive_days_and_year_boundary_are_explicit():
    rows = parse(
        ["12.30 WED", "1.1 FRI", "1.3 SUN"],
        "12.30 Wed 開演18:00<br>1.1 Fri 開演15:00<br>1.3 Sun 開演16:00",
        year=2027,
        month=1,
    )
    assert [r.start_date for r in rows] == ["2026-12-30", "2027-01-01", "2027-01-03"]
    assert "2026-12-31" not in [r.start_date for r in rows]
    assert "2027-01-02" not in [r.start_date for r in rows]


def test_unknown_times_never_use_doors_or_copy_unlabelled_common_clock():
    assert parse(["12.5 SAT"], "開場15:00")[0].start_time is None
    assert all(
        r.start_time is None for r in parse(["12.5 SAT", "12.6 SUN"], "開演17:00")
    )
    assert [
        r.start_time for r in parse(["12.5 SAT", "12.6 SUN"], "両日 開演17:00")
    ] == ["17:00"] * 2
    assert [r.start_time for r in parse(["12.5 SAT"], "試合開始：１９：０５")] == [
        "19:05"
    ]


@pytest.mark.parametrize(
    "days,times",
    [
        (["12.5 SAT", "12.6 SUN"], "12.5 Sat 開演17:00<br>12.7 Mon 開演16:00"),
        (["12.5 SAT", "12.6 SUN"], "12.5 Sat 開演17:00"),
        (["12.5 SAT"], "12.5 Sat 開演25:00"),
        (["12.5 SAT"], "12.5 Sat 開演17:99"),
        (["1.28 THU -", "1.31 SUN"], "開演18:30"),
    ],
)
def test_ambiguous_or_invalid_programme_is_reported_and_not_invented(days, times):
    issues = []
    assert parse(days, times, issues=issues) == []
    assert len(issues) == 1


def test_duplicate_date_sections_do_not_silently_choose_one():
    issues = []
    assert (
        parse(["12.5 SAT"], "12.5 Sat 開演17:00<br>12.5 Sat 開演18:00", issues=issues)
        == []
    )
    assert issues


def test_ambiguous_programme_uses_the_real_count_only_session_callback():
    from scripts.update_events_data import ThrottledSession
    session = ThrottledSession(None, None)
    assert parse(['12.5 SAT'], '12.6 Sun 開演17:00', counter=session.note_parser_issue) == []
    assert session.parser_issue_count == 1
    assert session.fetch_status(failed=False, raw_count=0)['status'] == 'partial_or_failed_collection'


def test_default_collection_keeps_legacy_contract_until_split_migration():
    html = '''<li><a href="https://ariake-arena.tokyo/event/">
    <span class="year">2026</span><span class="month_number">12</span></a></li>
    <ul class="event_detail_list"><li id="detail-338"><div class="event_day">
    <span>12.5 SAT</span><span>12.6 SUN</span></div><div class="event_name">出演者</div>
    <table class="detail_table"><tr><th>公演時間</th><td>12.5 開演17:00<br>12.6 開演16:30</td></tr></table>
    <a class="other_link" href="https://artist.example/tour">公式</a></li></ul>'''
    class Response:
        encoding = 'utf8'
        apparent_encoding = 'utf8'
        def __init__(self, ok):
            self.status_code = 200 if ok else 404
            self.text = html if ok else ''
    class Session:
        def get(self, url, **kwargs):
            return Response(url == 'https://ariake-arena.tokyo/event/')
    venue = VenueRecord('ariake_arena', '有明アリーナ', '13', '東京都', 15000,
                        'https://ariake-arena.tokyo/', 'html',
                        'https://ariake-arena.tokyo/event/', None, True)
    default = _AriakeArenaSchedule().parse(venue, Session(), {})
    assert [(r.start_date,r.end_date,r.start_time) for r in default] == [('2026-12-05','2026-12-06','17:00')]
    assert len(_AriakeArenaSchedule().parse(venue, Session(), {'dated_sessions': True})) == 2
    with pytest.raises(ValueError,match='must be boolean'):
        _AriakeArenaSchedule().parse(venue, Session(), {'dated_sessions': 'true'})

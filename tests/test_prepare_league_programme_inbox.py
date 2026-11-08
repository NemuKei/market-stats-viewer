"""Reduced primary-league structures; preparation never authorizes publication."""

from datetime import date
import pytest

from scripts.prepare_league_programme_inbox import SOURCES, collect, parse_page
from scripts.signals.entity_aliases import load_venue_lookup_maps
from scripts.apply_venue_discovery_inbox import apply_inbox

STAMP = "2026-11-07T12:00:00Z"


def parse(
    html, source, *, url=None, start=date(2026, 11, 7), through=date(2027, 2, 28)
):
    return parse_page(
        html,
        source,
        url or SOURCES[source][1],
        start=start,
        through=through,
        venue_names={
            "味の素スタジアム",
            "有明アリーナ",
            "Asueアリーナ大阪",
            "国立競技場",
        },
        venue_maps=load_venue_lookup_maps(),
        verified_at=STAMP,
    )


def football(venue="味の素スタジアム", day="25", display=None):
    return f"""<h2>2026/11/{display or day} (水)</h2><div class="m-schedule" id="202611{day}03">
    <a class="m-schedule__link" href="/match/j1/2026/11{day}03/">
    <div class="m-schedule__team-home"><span class="m-schedule__team-name" data-media="pc">FC東京</span></div>
    <div class="m-schedule__team-away"><span class="m-schedule__team-name" data-media="pc">広島</span></div>
    <p class="m-schedule__time-text">19:00</p>
    <p class="m-schedule__info-stadium" data-media="pc">{venue}</p></a></div>"""


def basket(
    day="2027.01.19",
    time="",
    arena="有明アリーナ(メイン)",
    href="https://www.bleague.jp/game_detail/?ScheduleKey=507524",
):
    return f'''<h1>{arena} | アリーナ検索</h1><div class="matchSchedule">
    <div class="matchSchedule-date">{day}</div><a class="matchSchedule-main" href="{href}">
    <div class="matchSchedule-home"><div class="matchSchedule-name">東京U</div></div>
    <div class="matchSchedule-away"><div class="matchSchedule-name">香川</div></div>
    <p class="matchSchedule-info-venue">有明M<br>{time}</p></a></div>'''


def rugby(venue="MUFGスタジアム（国立競技場） (東京都)", day="01.22", time="未定"):
    return f"""<div class="c-schedule"><h3 class="ttl">リーグワン 2026-27 第6節 (2027D10601)</h3>
    <p class="place"><a>{venue}</a></p><div class="datetime"><p class="date">{day} 金</p><p class="time">{time}</p></div>
    <ul class="game"><li class="home"><p class="name only-pc">浦安D-Rocks</p></li>
    <li class="away"><p class="name only-pc">神戸スティーラーズ</p></li></ul>
    <a class="btn-match-detail" href="/match/31165">詳細</a></div>"""


def sv(
    dom=16,
    selected=16,
    *,
    month=1,
    venue="Asueアリーナ大阪",
    clock="GAME START 13:05",
    game=1,
):
    return f"""<select id="select-year"><option selected value="2026">2026-27</option></select>
    <select id="select-ym"><option selected value="2027:{month}">2027年{month}月</option></select>
    <div class="div_day active" id="div_day_{selected}"></div><div class="div_day" id="div_day_17"></div>
    <dl id="match-list"><dt><b>第11節 GAME{game}</b><p><a>{venue}</a></p></dt><dd>
    <ul><li><b>サントリー</b></li><li class="away"><b>大阪B</b></li></ul>
    <div class="time">{clock}</div><a href="/match/detail/{38095 + dom}/">試合詳細</a></dd></dl>"""


def test_jleague_uses_each_actual_facility_not_clubs_default_home_stadium():
    rows, notes = parse(
        football() + football("AGFフィールド", day="26"), "jleague-ftokyo"
    )
    assert len(rows) == 1 and notes == {"unregistered_or_unselected_facility": 1}
    assert (
        rows[0]["event_start_date"] == "2026-11-25"
        and rows[0]["event_start_time"] == "19:00"
    )
    assert rows[0]["url"].endswith("/match/j1/2026/112503/")
    assert rows[0]["evidence_url"] == SOURCES["jleague-ftokyo"][1]
    with pytest.raises(ValueError, match="disagree"):
        parse(football(display="26"), "jleague-ftokyo")


def test_basketball_known_arena_binding_unknown_time_and_separate_link():
    rows, _ = parse(basket(), "bleague-ariake")
    assert "event_start_time" not in rows[0]
    assert rows[0]["source_class"] == "promoter_official"
    assert rows[0]["raw_venue_name"] == "有明アリーナ(メイン)"
    assert rows[0]["url"] != rows[0]["evidence_url"]
    rows, _ = parse(basket(time="19:05"), "bleague-ariake")
    assert rows[0]["event_start_time"] == "19:05"
    with pytest.raises(ValueError, match="arena identity"):
        parse(basket(arena="有明アリーナ(サブ)"), "bleague-ariake")
    with pytest.raises(ValueError, match="start time"):
        parse(basket(time="開場19:05"), "bleague-ariake")


def test_same_day_same_card_sessions_do_not_become_an_unimportable_inbox_draft():
    html = basket(time="13:00", href="https://www.bleague.jp/game_detail/?ScheduleKey=1")
    html += basket(time="19:00", href="https://www.bleague.jp/game_detail/?ScheduleKey=2")
    with pytest.raises(ValueError, match="existing inbox identity"):
        parse(html, "bleague-ariake")


def test_leagueone_uses_explicit_year_and_exact_national_stadium_alias():
    rows, _ = parse(rugby(), "leagueone")
    assert rows[0]["event_start_date"] == "2027-01-22"
    assert rows[0]["venue_name"] == "国立競技場"
    assert "event_start_time" not in rows[0]
    rows, notes = parse(rugby(day="02.27/28"), "leagueone")
    assert not rows and notes == {"date_not_confirmed": 1}
    rows, notes = parse(rugby(venue="有明アリーナ(サブ)"), "leagueone")
    assert not rows and notes == {"unregistered_or_unselected_facility": 1}


def test_sv_game2_and_explicit_source_date_survive_existing_inbox():
    first, _ = parse(
        sv(), "svleague-men", url=SOURCES["svleague-men"][1] + "?s=2026&y=2027&m=1&d=16"
    )
    second, _ = parse(
        sv(17, 17, game=2),
        "svleague-men",
        url=SOURCES["svleague-men"][1] + "?s=2026&y=2027&m=1&d=17",
    )
    rows = first + second
    assert [r["event_start_date"] for r in rows] == ["2027-01-16", "2027-01-17"]
    result = apply_inbox(
        dict(schema_version=1, run_at_utc=STAMP, candidates=rows),
        dict(
            watch_venues=[dict(venue_name="Asueアリーナ大阪", aliases=[])],
            accepted_source_classes=["promoter_official"],
            confirmed_events=[],
        ),
        venue_maps=({}, {}),
        artist_maps=({}, {}),
    )
    assert len(result.applied) == 2 and not result.rejected
    assert len({r["event_id"] for r in result.config["confirmed_events"]}) == 2


@pytest.mark.parametrize("html", [sv(selected=17), sv(month=2), sv(clock="25:05")])
def test_sv_rejects_ignored_date_switch_or_invalid_time(html):
    with pytest.raises(ValueError):
        parse(
            html,
            "svleague-men",
            url=SOURCES["svleague-men"][1] + "?s=2026&y=2027&m=1&d=16",
        )


def test_unknown_time_on_unselected_facility_does_not_stop_other_valid_updates():
    rows, notes = parse(
        rugby(venue="他の会場", time="未定 調整中") + rugby(time="14:00"), "leagueone"
    )
    assert len(rows) == 1 and rows[0]["event_start_time"] == "14:00"
    assert notes == {"unregistered_or_unselected_facility": 1}


@pytest.mark.parametrize(
    "html,source",
    [
        (football().replace("広島", "広島 中止"), "jleague-ftokyo"),
        (basket().replace("香川", "香川 延期"), "bleague-ariake"),
        (rugby().replace("神戸スティーラーズ", "神戸スティーラーズ 中止"), "leagueone"),
    ],
)
def test_cancelled_or_postponed_programmes_require_status_review(html, source):
    rows, notes = parse(html, source)
    assert not rows and notes == {"status_requires_review": 1}


def test_cross_domain_details_and_oversized_or_redirected_collection_fail():
    with pytest.raises(ValueError, match="primary-league"):
        parse(
            basket(href="https://other.example/game_detail/?ScheduleKey=1"),
            "bleague-ariake",
        )
    with pytest.raises(ValueError, match="calendar month"):
        collect(
            "svleague-men", date(2027, 1, 1), date(2027, 2, 1), {"Asueアリーナ大阪"}
        )

    class Response:
        url = "https://other.example/calendar/"

        def raise_for_status(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    with pytest.raises(ValueError, match="redirected"):
        collect(
            "jleague-ftokyo",
            date(2026, 11, 1),
            date(2026, 11, 30),
            {"味の素スタジアム"},
            session=Session(),
        )


def test_sv_collection_follows_source_day_navigation_and_keeps_game2():
    from urllib.parse import urlparse, parse_qs
    class Response:
        encoding='utf8'
        apparent_encoding='utf8'
        def __init__(self,url):
            self.url=url
            day=int(parse_qs(urlparse(url).query).get('d',['16'])[0])
            self.text=sv(day,day,game=day-15)
        def raise_for_status(self):pass
    class Session:
        def __init__(self):self.urls=[]
        def get(self,url,**kwargs):
            self.urls.append(url)
            return Response(url)
    session=Session()
    payload,_,pages=collect('svleague-men',date(2027,1,16),date(2027,1,17),{'Asueアリーナ大阪'},session=session)
    assert pages==2 and len(session.urls)==4
    assert [r['event_start_date'] for r in payload['candidates']]==['2027-01-16','2027-01-17']
    assert all(r['source_class']=='promoter_official' for r in payload['candidates'])
    assert payload['candidates'][0]['evidence_url'].endswith('&d=16')

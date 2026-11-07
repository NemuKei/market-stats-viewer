from datetime import date

import pytest

from scripts.prepare_venue_programme_inbox import explicit_times, parse_programmes
from scripts.apply_venue_discovery_inbox import apply_inbox

STAMP = "2026-11-07T12:00:00Z"


def game(day, venue="Asueアリーナ大阪"):
    return f"""<li class="gameData homegame"><div class="txtGameStart">
    <time datetime="2026-11-{day} 13:05">13:05</time> 試合開始</div>
    <div class="vsBox"><figure><figcaption>大阪マーヴェラス</figcaption></figure>
    <figure><figcaption>東レ滋賀</figcaption></figure></div>
    <dl class="txtKaijyo"><dd>{venue}<br/>（大阪）</dd></dl></li>"""


def parse(
    html, source="osaka-marvelous", start=date(2026, 11, 7), through=date(2026, 11, 30)
):
    return parse_programmes(
        html, source, start=start, through=through, verified_at=STAMP
    )


def test_team_programme_keeps_game2_and_filters_other_facilities():
    rows, skipped = parse(game("28") + game("29") + game("21", "おおきにアリーナ舞洲"))
    assert [r["event_start_date"] for r in rows] == ["2026-11-28", "2026-11-29"]
    assert [r["event_start_time"] for r in rows] == ["13:05", "13:05"]
    assert {r["source_class"] for r in rows} == {"promoter_official"}
    assert skipped == {"other_facility": 1}
    # Existing inbox / collector path can take both dates independently.
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


def test_away_game_is_not_classified_as_this_clubs_promoter_programme():
    rows, skipped = parse(game("29").replace("homegame", "awaygame"))
    assert rows == []
    assert skipped == {"not_home_programme": 1}


def arena_card(
    day="11.10 火",
    title="千葉ジェッツ vs 大阪エヴェッサ",
    times="開場 16:30 / 試合開始：19:05",
    href="/event/2900/",
):
    return f'''<div class="p-eventbox"><a class="p-eventbox__link" href="{href}"></a>
    <p class="p-eventbox__date">{day}</p><p class="p-eventbox__artist">千葉ジェッツ</p>
    <h2 class="p-eventbox__title">{title}</h2><p>{times}</p></div>'''


def arena_html(card, year=2026, month=11):
    return f"""<div data-target="cards1"><span class="c-tab__year">{year}</span>
        <span class="c-tab__month">{month}</span></div><div class="p-cards" id="cards1">{card}</div>"""


def test_arena_uses_labelled_year_and_actual_start_not_priority_entry_time():
    rows, _ = parse(arena_html(arena_card()), "lala-arena")
    assert rows[0]["event_start_time"] == "19:05"
    assert rows[0]["evidence_url"] == "https://lalaarenatokyo-bay.com/event/"
    assert rows[0]["url"] == "https://lalaarenatokyo-bay.com/event/2900/"
    html = arena_html(arena_card("1.2 土"), year=2027, month=1)
    rows, _ = parse(
        html, "lala-arena", start=date(2027, 1, 1), through=date(2027, 1, 31)
    )
    assert rows[0]["event_start_date"] == "2027-01-02"


def test_times_and_reserved_programmes_are_not_invented():
    assert explicit_times("開場15:00 / 開演17:00") == ["17:00"]
    assert explicit_times("開演12:30/18:00") == ["12:30", "18:00"]
    assert explicit_times("開演12:30 / 開演18:00") == ["12:30", "18:00"]
    assert explicit_times("優先入場10:00 一般10:30 開演未定") == []
    rows, skipped = parse(arena_html(arena_card(title="Reserved")), "lala-arena")
    assert not rows and skipped == {"unannounced_programme": 1}
    rows, _ = parse(arena_html(arena_card(times="開場15:00 / 開演未定")), "lala-arena")
    assert "event_start_time" not in rows[0]


def test_two_actual_shows_are_kept_for_existing_conflicting_time_review():
    rows, _ = parse(arena_html(arena_card(times="開演13:00/18:00")), "lala-arena")
    assert [r["event_start_time"] for r in rows] == ["13:00", "18:00"]


@pytest.mark.parametrize(
    "html,source",
    [
        ("<html>HTML changed</html>", "osaka-marvelous"),
        (arena_html(arena_card(day="12.10 火")), "lala-arena"),
        (arena_html(arena_card(href="https://other.example/")), "lala-arena"),
        (game("29").replace("datetime=", "missing="), "osaka-marvelous"),
    ],
)
def test_ambiguous_structure_date_or_cross_domain_link_fails_for_manual_review(
    html, source
):
    with pytest.raises(ValueError):
        parse(html, source)

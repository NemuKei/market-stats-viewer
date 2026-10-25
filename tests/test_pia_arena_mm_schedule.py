import pytest
from bs4 import BeautifulSoup

from scripts.events.sources.html import _PiaArenaMmSchedule
from scripts.events.types import VenueRecord
from scripts.update_events_data import init_db, upsert_events


class DetailSession:
    def get(self, url, timeout=30):
        assert url in {
            "https://pia-arena-mm.jp/event/6602.html",
            "https://pia-arena-mm.jp/event/6605.html",
        }
        start = "18:00" if "6602" in url else "17:00"
        return type("Response", (), {
            "status_code": 200,
            "apparent_encoding": "utf-8",
            "text": f"<dl><dt>公演時間</dt><dd>開場/16:00 開演/{start}</dd></dl>",
        })()


def parse_card(heading, subtitle, day, source_key):
    venue = VenueRecord(
        venue_id="pia_arena_mm", venue_name="ぴあアリーナMM",
        pref_code="14", pref_name="神奈川県", capacity=10000,
        official_url="https://pia-arena-mm.jp/", source_type="html",
        source_url="https://pia-arena-mm.jp/event@p1=2027&p2=03.html",
        config_json=None, is_enabled=True,
    )
    heading_html = f"<h3>{heading}</h3>" if heading is not None else ""
    soup = BeautifulSoup(f"""
        <a class="event-list" href="event/{source_key}.html">
          <div class="event-list__date"><p>03.{day}</p></div>
          <div class="event-list__detail"><div class="title">
            {heading_html}<p>{subtitle}</p>
          </div></div>
        </a>
    """, "html.parser")
    return _PiaArenaMmSchedule()._parse_page(
        venue, DetailSession(), soup, venue.source_url, 2027, set(),
    )[0]


@pytest.mark.parametrize("day,source_key,subtitle,start", [
    ("06", "6602", 'ReoNa ANIME & GAME スーパーベストコンサート “ハロー、アンハッピー ー青ー 〜逃げて逢おうね〜” at ぴあアリーナMM', "18:00"),
    ("07", "6605", 'ReoNa ANIME & GAME スーパーベストコンサート “ハロー、アンハッピー ー赤ー 〜やっぱり人が好き〜” at ぴあアリーナMM', "17:00"),
])
def test_explicit_artist_survives_new_program_title_in_database(tmp_path, day, source_key, subtitle, start):
    event = parse_card("ReoNa", subtitle, day, source_key)
    assert event.performers == "ReoNa"
    assert event.event_uid == f"pia_arena_mm:event/{source_key}.html"
    assert event.start_date == f"2027-03-{day}"
    assert event.start_time == start
    assert event.title == f"ReoNa {subtitle}"

    conn = init_db(tmp_path / "events.sqlite")
    try:
        upsert_events(conn, [event], {}, {})
        artist, confidence = conn.execute(
            "SELECT artist_name_resolved, artist_confidence FROM events"
        ).fetchone()
        assert (artist, confidence) == ("ReoNa", "source")
    finally:
        conn.close()


@pytest.mark.parametrize("heading", [None, "", "合同イベント"])
def test_absent_or_unrecognized_heading_keeps_existing_inference_path(heading):
    event = parse_card(heading, "ReoNa ANIME & GAME スーパーベストコンサート", "06", "6602")
    assert event.performers is None

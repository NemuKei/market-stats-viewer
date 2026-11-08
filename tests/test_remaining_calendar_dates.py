"""Regressions for source-labelled years and separately labelled door/start times."""
from datetime import date
import sqlite3
from types import SimpleNamespace

import pytest

from scripts.prepare_venue_programme_inbox import parse_programmes
from scripts import update_events_data as collector
from scripts.signals.sources.venue_web_discovery import VenueWebDiscoverySource
from scripts.audit_event_calendar_coverage import audit_runtime


def avex_card(day='2026.11.29[Sun]', clocks='開場：15:00 開演：17:00', venue='京セラドーム大阪'):
    return f'''<ul class="tourData__lists"><li class="js-tourDataPlace">{venue}</li>
    <li><span class="tourData__date">{day}</span></li>
    <li class="tourData__list--time">{clocks}</li></ul>'''


def parse(html):
    return parse_programmes('<title>BIGBANG Official TOUR</title>'+html, 'bigbang-kyocera',
        start=date(2026,11,27), through=date(2026,11,29), verified_at='2026-11-08T07:27:10Z')


def test_artist_draft_reads_start_in_its_own_dated_card_not_the_door_time():
    rows, _ = parse(avex_card('2026.11.27[Fri]', '開場：16:00 開演：18:00')+avex_card())
    assert [(r['event_start_date'],r['event_start_time']) for r in rows] == [('2026-11-27','18:00'),('2026-11-29','17:00')]
    assert all(r['source_class']=='artist_official' for r in rows)
    with pytest.raises(ValueError, match='start'):
        parse(avex_card(clocks='開場：15:00'))
    with pytest.raises(ValueError, match='date'):
        parse(avex_card(day='11.29[Sun]'))


def test_artist_draft_keeps_two_real_same_day_performances_and_other_venues_out():
    rows, skipped = parse(avex_card(clocks='開場：12:00 開演：13:00')+avex_card()+avex_card(venue='別の会場'))
    assert [r['event_start_time'] for r in rows] == ['13:00','17:00']
    assert skipped['other_facility'] == 1
    with pytest.raises(ValueError, match='duplicate'):
        parse(avex_card()+avex_card())


def test_year_conflict_review_detects_retained_wrong_year_without_guessing_or_mutation():
    con=sqlite3.connect(':memory:')
    con.execute('create table events (event_uid,venue_id,title,url,source_url,start_date,start_time)')
    con.execute("insert into events values ('old','nagoya','Tour 2025','https://artist/tour','https://venue/calendar','2026-12-06','17:00')")
    old=con.execute('select * from events').fetchall()
    def event(day):
        return SimpleNamespace(event_uid=day,title='Tour 2025',url='https://artist/tour',source_url='https://venue/calendar',start_date=day,start_time='17:00')
    assert collector.calendar_year_conflict_count(con,'nagoya',[event('2025-12-06')]) == 1
    assert collector.calendar_year_conflict_count(con,'nagoya',[event('2024-12-06')]) == 1
    assert collector.calendar_year_conflict_count(con,'nagoya',[event('2025-12-06'),event('2026-12-06')]) == 0
    assert collector.calendar_year_conflict_count(con,'nagoya',[event('2025-12-07')]) == 0
    assert collector.calendar_year_conflict_count(con,'nagoya',[]) == 0
    assert con.execute('select * from events').fetchall() == old


def test_explicit_utc_offset_observation_time_is_stable_instead_of_collection_now():
    source=VenueWebDiscoverySource(None)
    row={'verified_at_utc':'2026-11-08T05:42:18.057600+00:00'}
    assert source._published_at(row)=='2026-11-08T05:42:18Z'
    assert source._published_at(row)=='2026-11-08T05:42:18Z'
    assert source._published_at(dict(row,published_at_utc='2026-11-08T05:58:46Z'))=='2026-11-08T05:58:46Z'


def test_year_conflict_counts_reach_coverage_summary_without_source_contents():
    report = audit_runtime(dict(venues=[dict(venue_id='nagoya',venue_name='テスト会場',
        official_enabled=True,web_watch_configured=False)],scope='fixture',summary={},
        identity_conflicts=[],orphan_web_watch_ids=[],orphan_ticketjam_ids=[]), [], [],
        {'events':[]}, {'held_records':[]}, {'events':[]}, start=date(2026,11,8),end=date(2026,11,8),
        fetch_report={'venues':[{'venue_id':'nagoya','calendar_year_conflict_count':14,'status':'fetched_completeness_unverified'}]})
    venue = report['venues'][0]
    assert venue['calendar_year_conflict_count'] == 14
    assert 'retained_calendar_year_conflicts_require_review' in venue['flags']
    assert report['coverage_verified'] is False


def test_review_only_venue_collection_cannot_write_directly_to_public_db(tmp_path):
    reviewed = SimpleNamespace(config_json='{"publication_review":true}')
    with pytest.raises(ValueError, match='outside'):
        collector.validate_collection_target(collector.EVENTS_DB_PATH,[reviewed],skip_artist_inference=True)
    assert collector.validate_collection_target(tmp_path/'private.sqlite',[reviewed],skip_artist_inference=True) == tmp_path/'private.sqlite'
    malformed = SimpleNamespace(config_json='{"publication_review":"true"}')
    with pytest.raises(ValueError, match='boolean'):
        collector.validate_collection_target(tmp_path/'private.sqlite',[malformed],skip_artist_inference=True)

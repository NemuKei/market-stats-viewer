"""A registered candidate awaiting source review must not block unrelated updates.

All events are fictional. Cross-repository publication is checked separately by
the isolated CLI rehearsal; these producer tests require only this repository.
"""
from copy import deepcopy
from datetime import date
import json

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts import reviewed_source_map as reviewed
from scripts.build_all_dates_lp_events import build_all_dates_payload
from scripts.validate_external_events import validate_payload
from scripts.public_lp_projection import project_event
from test_event_identity_registry import record, payload, registry_for, request



@pytest.mark.parametrize(('source_id', 'source_class', 'url', 'consumer_published'), [
    ('official_events', 'venue_official', 'https://www.tokyo-dome.co.jp/dome/event/fictional-new', True),
    ('venue_web_discovery', 'venue_official', 'https://ariake-arena.tokyo/event/fictional-new', True),
    ('starto_concert', '', 'https://starto.jp/s/p/live/fictional-new', False),
    ('kstyle_music', '', 'https://kstyle.com/article/fictional-new', False),
])
def test_all_collectors_hold_review_and_publish_independently(
        tmp_path, monkeypatch, source_id, source_class, url, consumer_published):
    old_raw = record('old')
    new_raw = record('new', source_id=source_id, source_class=source_class,
                     url=url, evidence_url=url)
    original = payload([old_raw, new_raw])
    old = next(x for x in original['events'] if x['title'] == old_raw['title'])
    new = next(x for x in original['events'] if x['title'] == new_raw['title'])
    registry = registry_for([old])
    registry = ids.apply_review(registry, request(registry, 'new', [], [(None, new)]))
    registry_path = tmp_path / 'registry.json'
    ids.write_registry(registry, registry_path, expected_sha256=None)
    registry_before = registry_path.read_bytes()
    uid = next(e['event_uid'] for e in registry['events'] if any(
        o['fingerprint'] == ids.observation_from_row(new)['fingerprint'] and o['active']
        for o in e['observations']))
    official = {'source-old': (old_raw['evidence_url'], old_raw['url'])}
    if source_id == 'official_events':
        official['source-new'] = (url, url)
    source_map = tmp_path / 'map.json'
    source_map.write_text(json.dumps({'schema_version': 1, 'records': []}))
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'schema_version': 4, 'asset_sha256': 'a' * 64,
                                    'event_sources': {old['event_key']: reviewed.source_signature(old, official, legacy_row=True)}}))
    # Keep the real publication filter, grouping, ID resolver, map and writer.
    # Only the input loader is replaced with fictional collector records.
    monkeypatch.setattr(builder, 'load_lp_records', lambda **kwargs: deepcopy([old_raw, new_raw]))
    monkeypatch.setattr(reviewed, 'read_official_sources', lambda path: official)
    kw = dict(identity_registry_path=registry_path, reviewed_source_map_path=source_map,
              reviewed_source_baseline_path=baseline, as_of_date=date(2026, 10, 6))
    without_map = builder.build_lp_events(identity_registry_path=registry_path, as_of_date=date(2026, 10, 6))
    assert len(without_map['events']) == (2 if consumer_published else 1)
    result = builder.build_lp_events(**kw)
    validate_payload(result)
    assert result['events'] == [old]
    assert result['summary']['identity_held_record_count'] == 1
    held = result['identity_held_records']
    assert len(held) == 1 and held[0]['reason'] == 'source_review_required'
    assert held[0]['related_event_uids'] == [uid]
    assert held[0]['source_records'] == ids.observation_from_row(new)['source_records']
    output = tmp_path / 'lp.json'
    builder.write_lp_events(result, output, identity_registry_path=registry_path)
    public = json.loads(output.read_text())
    assert public['events'] == [old]
    assert 'identity_held_records' not in public
    assert 'source_review_candidates' not in public
    all_dates = build_all_dates_payload(result, **{k: v for k, v in kw.items() if k != 'as_of_date'})
    assert all_dates['events'] == [old]
    assert all_dates['summary']['identity_held_record_count'] == 1

    preview = tmp_path / 'pending.json'
    ids.main(['--registry', str(registry_path), 'pending', '--output', str(preview),
              '--reviewed-source-map', str(source_map), '--reviewed-source-baseline', str(baseline)])
    pending = json.loads(preview.read_text())
    assert pending['held_records'] == held
    draft = pending['source_review_candidates'][0]['review_request']
    assert draft['event_uid'] == uid and draft['fact_review'] == 'pending'
    source_map.write_text(json.dumps({'schema_version': 1, 'records': [draft]}))
    with pytest.raises(reviewed.SourceMapError, match='invalid preserved source review'):
        builder.build_lp_events(**kw)

    # Simulate a separate Git review of this exact unchanged tuple. This is not
    # automatic approval or a new consumer source/domain permission.
    draft['fact_review'] = 'reviewed'
    source_map.write_text(json.dumps({'schema_version': 1, 'records': [draft]}))
    facts_only = builder.build_lp_events(**kw)
    assert facts_only['events'] == [old]
    draft['publication']['status'] = 'reviewed'  # Separate hypothetical public decision.
    source_map.write_text(json.dumps({'schema_version': 1, 'records': [draft]}))
    approved = builder.build_lp_events(**kw)
    assert approved['events'] == ([project_event(r) if r['event_key'] == uid else r for r in without_map['events']] if consumer_published else [old])
    assert len(approved['identity_held_records']) == (0 if consumer_published else 1)
    builder.write_lp_events(approved, output, identity_registry_path=registry_path)
    public = json.loads(output.read_text())
    assert public['events'] == approved['events']
    assert next(row for row in public['events'] if row['event_key'] == old['event_key']) == old
    assert registry_path.read_bytes() == registry_before
    all_approved = build_all_dates_payload(approved, **{k: v for k, v in kw.items() if k != 'as_of_date'})
    assert all_approved['events'] == approved['events']
    if consumer_published:
        assert next(r for r in approved['events'] if r['event_key'] == uid)['display_source_class'] == source_class

    # A supporting-source URL is public data too. It cannot be added under an
    # unchanged identity fingerprint, nor omitted from the explicit review.
    changed = deepcopy(original['events'])
    next(r for r in changed if r['event_key'] == new['event_key'])['supporting_sources'][0]['evidence_url'] = 'https://unreviewed.example/support'
    with pytest.raises(reviewed.SourceMapError, match='preserved source or public links changed'):
        reviewed.apply_reviewed_source_map(changed, registry, source_map.read_bytes(), builder.DEFAULT_EVENTS_DB_PATH)
    missing_link = deepcopy(draft)
    missing_link['public_urls'] = []
    with pytest.raises(reviewed.SourceMapError, match='preserved source or public links changed'):
        reviewed.apply_reviewed_source_map(original['events'], registry,
            json.dumps({'schema_version': 1, 'records': [missing_link]}).encode(), builder.DEFAULT_EVENTS_DB_PATH)
    wrong_id = deepcopy(draft)
    wrong_id['event_uid'] = old['event_key']
    with pytest.raises(reviewed.SourceMapError, match='not bound to active fixed ID'):
        reviewed.apply_reviewed_source_map(original['events'], registry,
            json.dumps({'schema_version': 1, 'records': [wrong_id]}).encode(), builder.DEFAULT_EVENTS_DB_PATH)
    if source_id == 'official_events':
        official['source-new'] = ('https://www.tokyo-dome.co.jp/dome/event/', url)
        mismatched_acquisition = deepcopy(draft)
        mismatched_acquisition['source_signature'] = reviewed.source_signature(new, official)
        with pytest.raises(reviewed.SourceMapError, match='does not retain acquisition URL'):
            reviewed.apply_reviewed_source_map(original['events'], registry,
                json.dumps({'schema_version': 1, 'records': [mismatched_acquisition]}).encode(), builder.DEFAULT_EVENTS_DB_PATH)
        official['source-new'] = (url, url)

    # A reviewed source/link tuple cannot drift; volatile update time can advance.
    new_raw['updated_at_utc'] = '2026-11-06T00:00:00Z'
    assert len(builder.build_lp_events(**kw)['events']) == (2 if consumer_published else 1)
    new_raw['url'] = 'https://changed.example/new'
    with pytest.raises(reviewed.SourceMapError, match='preserved source or public links changed'):
        builder.build_lp_events(**kw)
    new_raw['url'] = url
    # Existing published drift still stops rather than silently dropping its row.
    old_raw['url'] = 'https://changed.example/old'
    with pytest.raises(reviewed.SourceMapError, match='existing ID source or public link changed'):
        builder.build_lp_events(**kw)
    assert json.loads(output.read_text()) == public


def test_all_source_candidates_held_preserves_previous_snapshot(tmp_path, monkeypatch):
    candidate = payload([record('new')])
    row = candidate['events'][0]
    registry = registry_for([row])
    registry_path = tmp_path / 'registry.json'
    ids.write_registry(registry, registry_path, expected_sha256=None)
    source_map = tmp_path / 'map.json'
    source_map.write_text(json.dumps({'schema_version': 1, 'records': []}))
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'schema_version': 4, 'asset_sha256': 'a' * 64, 'event_sources': {}}))
    monkeypatch.setattr(builder, '_build_lp_event_candidates', lambda **kwargs: deepcopy(candidate))
    result = builder.build_lp_events(identity_registry_path=registry_path,
        reviewed_source_map_path=source_map, reviewed_source_baseline_path=baseline)
    assert result['events'] == [] and result['summary']['identity_held_record_count'] == 1
    output = tmp_path / 'lp.json'
    output.write_bytes(b'previous approved snapshot')
    with pytest.raises(ValueError, match='all candidates held'):
        builder.write_lp_events(result, output, identity_registry_path=registry_path)
    assert output.read_bytes() == b'previous approved snapshot'

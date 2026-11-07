"""Fictional data: retain approved bytes, never infer approval of changed data."""
from copy import deepcopy
from datetime import date
import json

import pytest

from scripts import build_lp_events as builder
from scripts import event_identity_registry as ids
from scripts import reviewed_source_map as review
from scripts.build_all_dates_lp_events import build_all_dates_payload
from scripts.public_lp_projection import embedded_urls, project_event, publication_preview
from test_event_identity_registry import record, payload, registry_for, request


def setup(tmp_path, monkeypatch, *, mapped_old=False):
    old_raw, new_raw = record('old'), record('new', source_id='venue_web_discovery')
    rows = payload([old_raw, new_raw])['events']
    old = next(r for r in rows if r['title'] == old_raw['title'])
    new = next(r for r in rows if r['title'] == new_raw['title'])
    registry = registry_for([old])
    registry = ids.apply_review(registry, request(registry, 'new', [], [(None, new)]))
    resolved, _ = ids.resolve_rows([new], registry)
    new = resolved[0]
    reg = tmp_path / 'registry.json'
    ids.write_registry(registry, reg, expected_sha256=None)
    official = {'source-old': (old_raw['evidence_url'], old_raw['url'])}
    asset = payload([old_raw])
    asset['history_scope'] = 'all_verified_retained'
    asset_bytes = ids.canonical_bytes(asset)
    baseline = review.baseline_from_asset(asset_bytes, ids.digest(asset_bytes), official,
                                         retain_published_rows=True)
    base = tmp_path / 'baseline.json'
    base.write_text(json.dumps(baseline))

    def selection(row):
        raw = next(r for r in rows if r['title'] == row['title'])
        return {'mode': 'preserve_source', 'event_uid': row['event_key'],
                'observation': ids.observation_from_row(raw),
                'source_signature': review.source_signature(row, official),
                'public_urls': sorted(set(embedded_urls(project_event(row)))),
                'fact_review': 'reviewed',
                'publication': {**publication_preview(row), 'status': 'reviewed'}}
    mapping = tmp_path / 'map.json'
    mapping.write_text(json.dumps({'schema_version': 1, 'records': [selection(new)] + ([selection(old)] if mapped_old else [])}))
    monkeypatch.setattr(builder, 'load_lp_records', lambda **kw: deepcopy([old_raw, new_raw]))
    monkeypatch.setattr(review, 'read_official_sources', lambda db: official)
    return old_raw, old, new, reg, base, mapping, official


@pytest.mark.parametrize('changes', [
    {'evidence_snippet': 'UNREVIEWED BODY'}, {'capacity': 99999},
    {'source_label': 'UNREVIEWED METADATA'}, {'raw_venue_name': 'UNREVIEWED RAW NAME'},
    {'url': 'https://unreviewed.example/new'},
])
def test_old_row_retained_while_normal_reviewed_new_event_continues(tmp_path, monkeypatch, changes):
    raw, old, new, reg, base, mapping, official = setup(tmp_path, monkeypatch)
    before = reg.read_bytes()
    raw.update(changes)
    kw = dict(identity_registry_path=reg, reviewed_source_map_path=mapping,
              reviewed_source_baseline_path=base, as_of_date=date(2026, 10, 6))
    result = builder.build_lp_events(**kw)
    by_id = {r['event_key']: r for r in result['events']}
    assert by_id[old['event_key']] == old
    assert by_id[new['event_key']] == project_event(new)
    assert result['summary']['identity_held_record_count'] == 1
    assert result['identity_held_records'][0]['reason'] == 'existing_publication_change_held'
    output = tmp_path / 'lp.json'
    builder.write_lp_events(result, output, identity_registry_path=reg)
    assert 'UNREVIEWED' not in output.read_text() and 'unreviewed.example' not in output.read_text()
    assert 'identity_held_records' not in json.loads(output.read_text())
    full = build_all_dates_payload(result, **{k: v for k, v in kw.items() if k != 'as_of_date'})
    assert full['events'] == result['events']
    assert reg.read_bytes() == before


def test_stale_existing_map_and_hidden_db_url_change_retain_old_row(tmp_path, monkeypatch):
    raw, old, _, reg, base, mapping, official = setup(tmp_path, monkeypatch, mapped_old=True)
    raw['url'] = 'https://unreviewed.example/detail'
    official['source-old'] = ('https://unreviewed.example/acquisition', raw['url'])
    result = builder.build_lp_events(identity_registry_path=reg, reviewed_source_map_path=mapping,
        reviewed_source_baseline_path=base, as_of_date=date(2026, 10, 6))
    assert next(r for r in result['events'] if r['event_key'] == old['event_key']) == old
    assert result['summary']['identity_held_record_count'] == 1


def test_corrupt_baseline_and_invalid_map_still_stop(tmp_path, monkeypatch):
    _, old, _, reg, base, mapping, _ = setup(tmp_path, monkeypatch)
    good = base.read_bytes()
    doc = json.loads(good)
    doc['published_rows'][old['event_key']]['evidence_snippet'] = 'tampered'
    base.write_text(json.dumps(doc))
    with pytest.raises(review.SourceMapError, match='invalid retained publication'):
        builder.build_lp_events(identity_registry_path=reg, reviewed_source_map_path=mapping, reviewed_source_baseline_path=base)
    base.write_bytes(good)
    doc = json.loads(mapping.read_text())
    doc['records'].append(deepcopy(doc['records'][0]))
    mapping.write_text(json.dumps(doc))
    with pytest.raises(review.SourceMapError, match='duplicate reviewed selection'):
        builder.build_lp_events(identity_registry_path=reg, reviewed_source_map_path=mapping, reviewed_source_baseline_path=base)


def test_identity_change_cannot_be_retained_under_old_id(tmp_path, monkeypatch):
    _, old, _, reg, base, _, official = setup(tmp_path, monkeypatch)
    row = deepcopy(old)
    row['event_start_time'] = '19:00'
    registry, _ = ids.load_registry(reg)
    with pytest.raises(review.SourceMapError, match='changed identity'):
        review.guard_new_ids([row], ids.canonical_bytes({'schema_version': 1, 'records': []}),
            base.read_bytes(), set(), official, registry=registry, retained_changes=[])


def test_unresolved_identity_change_cannot_silently_remove_existing_id(tmp_path, monkeypatch):
    raw, _, _, reg, base, mapping, _ = setup(tmp_path, monkeypatch)
    raw['event_start_time'] = '19:00'
    with pytest.raises(review.SourceMapError, match='unresolved identity change'):
        builder.build_lp_events(identity_registry_path=reg, reviewed_source_map_path=mapping,
            reviewed_source_baseline_path=base, as_of_date=date(2026, 10, 6))


@pytest.mark.parametrize('suppressed', [False, True])
def test_retention_does_not_resurrect_missing_or_suppressed_occurrence(tmp_path, monkeypatch, suppressed):
    _, old, new, reg, base, mapping, _ = setup(tmp_path, monkeypatch)
    current = [record('new', source_id='venue_web_discovery')]
    if suppressed:
        current.append(record('old', event_status='cancelled'))
    monkeypatch.setattr(builder, 'load_lp_records', lambda **kw: current)
    result = builder.build_lp_events(identity_registry_path=reg, reviewed_source_map_path=mapping,
        reviewed_source_baseline_path=base, as_of_date=date(2026, 10, 6))
    assert [r['event_key'] for r in result['events']] == [new['event_key']]
    assert old['event_key'] not in {r['event_key'] for r in result['events']}


def test_baseline_extension_preserves_old_source_decisions_and_binds_new_id(tmp_path, monkeypatch):
    _, old, new, _, base, _, official = setup(tmp_path, monkeypatch)
    previous = json.loads(base.read_bytes())
    asset = payload([record('old'), record('new', source_id='venue_web_discovery')])
    asset.update(history_scope='all_verified_retained', events=[old, new])
    raw = ids.canonical_bytes(asset)
    official['source-old'] = ('https://unreviewed.example/acquisition', old['url'])
    extended = review.extend_publication_baseline(base.read_bytes(), raw, ids.digest(raw), official, [new['event_key']])
    assert extended['event_sources'][old['event_key']] == previous['event_sources'][old['event_key']]
    assert set(extended['published_rows']) == {old['event_key'], new['event_key']}
    held = []
    rows = [deepcopy(old), deepcopy(new)]
    registry = registry_for([old, new])
    assert review.guard_new_ids(rows, ids.canonical_bytes({'schema_version': 1, 'records': []}),
        ids.canonical_bytes(extended), set(), official, registry=registry, retained_changes=held) == set()
    assert len(held) == 1 and held[0]['event_key'] == old['event_key']


def test_baseline_extension_rejects_unreviewed_ids_or_old_content_changes(tmp_path, monkeypatch):
    _, old, new, _, base, _, official = setup(tmp_path, monkeypatch)
    asset = payload([record('old'), record('new', source_id='venue_web_discovery')])
    asset.update(history_scope='all_verified_retained', events=[old, new])
    raw = ids.canonical_bytes(asset)
    with pytest.raises(review.SourceMapError, match='exact reviewed new ID set'):
        review.extend_publication_baseline(base.read_bytes(), raw, ids.digest(raw), official, ['other'])
    asset['events'][0]['evidence_snippet'] = 'UNREVIEWED'
    raw = ids.canonical_bytes(asset)
    with pytest.raises(review.SourceMapError, match='changed an existing public row'):
        review.extend_publication_baseline(base.read_bytes(), raw, ids.digest(raw), official, [new['event_key']])

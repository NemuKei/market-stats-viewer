"""Private drafts are diagnostic, never an automatic public-source approval."""
from datetime import date
import json
from types import SimpleNamespace

import requests

from scripts import collect_league_review as watch


def test_one_blocked_route_keeps_other_route_and_does_not_retry_or_publish(tmp_path):
    calls = []
    def collect(source, start, through, venues, **kw):
        calls.append((source,start,through))
        if source == 'jleague-ftokyo':
            response = requests.Response()
            response.status_code = 403
            raise requests.HTTPError('MUST NOT PRINT https://private.invalid/', response=response)
        return {'schema_version':1,'run_at_utc':'2026-11-08T00:00:00Z','candidates':[]}, {}, 1
    result = watch.collect_review(sources=['jleague-ftokyo','bleague-asue'],
        start=date(2026,11,8), through=date(2027,1,31), venue_names={'Asueアリーナ大阪'},
        private_dir=tmp_path/'drafts', collect=collect, confirmed=[])
    assert len([x for x in calls if x[0]=='jleague-ftokyo']) == 1
    assert len([x for x in calls if x[0]=='bleague-asue']) == 3
    assert result['source_results'][0]['status'] == 'http_access_denied'
    # Three blocked windows and three empty, unverified windows: no false
    # completeness claim simply because the unrelated route returned zero.
    assert result['unmeasured_or_blocked_windows'] == 6
    assert 'private.invalid' not in json.dumps(result)
    assert result['publication_changes'] == 0
    assert len(list((tmp_path/'drafts').glob('*.json'))) == 3


def test_exact_known_match_and_start_time_change_are_distinct_review_counts(tmp_path):
    known = dict(event_start_date='2026-11-21',venue_name='テスト',artist_name='A vs B',
                 event_start_time='15:00',url='https://official.example/match/1')
    shifted = dict(known,event_start_time='17:00')
    new = dict(known,event_start_date='2026-11-22',url='https://official.example/match/2')
    other_source = dict(known,url='https://second-official.example/match/1')
    def collect(*args,**kw):
        return dict(schema_version=1,run_at_utc='2026-11-08T00:00:00Z',candidates=[known,shifted,new,other_source]), {}, 1
    result = watch.collect_review(sources=['bleague-asue'],start=date(2026,11,8),through=date(2026,11,30),
        venue_names={'テスト'},private_dir=tmp_path/'drafts',collect=collect,confirmed=[known])
    counts = result['source_results'][0]
    assert counts['already_confirmed_exact'] == counts['changed_known_match'] == counts['unreviewed_candidate'] == 1
    assert counts['known_match_other_source'] == 1
    assert 'official.example' not in json.dumps(result)
    assert len(json.loads(next((tmp_path/'drafts').glob('*.json')).read_bytes())['candidates']) == 4


def test_access_denial_does_not_switch_to_another_route_on_the_same_host(tmp_path):
    calls=[]
    def collect(source,*args,**kw):
        calls.append(source)
        response=requests.Response()
        response.status_code=403
        raise requests.HTTPError(response=response)
    result=watch.collect_review(sources=['jleague-ftokyo','jleague-tokyov'],
        start=date(2026,11,8),through=date(2026,11,30),venue_names={'テスト'},
        private_dir=tmp_path/'drafts',collect=collect)
    assert calls == ['jleague-ftokyo']
    assert result['source_results'][1]['status']=='not_attempted_after_access_denial'


def test_private_outputs_cannot_use_the_public_checkout_or_reuse_existing_dir(tmp_path):
    import pytest
    with pytest.raises(ValueError,match='private'):
        watch.validate_private_dir(watch.REPO_ROOT/'unreviewed')
    target = tmp_path/'existing'
    target.mkdir()
    with pytest.raises(ValueError,match='new'):
        watch.validate_private_dir(target)


def test_parent_traversal_cannot_hide_a_public_output_directory(tmp_path,monkeypatch):
    import pytest
    public=tmp_path/'public'
    public.mkdir()
    outside=tmp_path/'outside'
    outside.mkdir()
    monkeypatch.setattr(watch,'REPO_ROOT',public)
    with pytest.raises(ValueError,match='private'):
        watch.validate_private_dir(outside/'..'/'public'/'drafts')


def test_unknown_venue_and_unreviewed_source_do_not_fetch_or_create_output(tmp_path,monkeypatch):
    monkeypatch.setattr(watch,'load_registry',lambda: [SimpleNamespace(venue_id='real',venue_name='テスト')])
    assert watch.main(['--source','bleague-asue','--venue-id','unknown','--start','2026-11-08',
        '--through','2026-11-30','--private-dir',str(tmp_path/'drafts')]) == 2
    assert not (tmp_path/'drafts').exists()


def test_summary_hardlink_cannot_modify_confirmation_input(tmp_path,monkeypatch):
    data=tmp_path/'data'
    data.mkdir()
    config=data/'venue_web_discovery_config.json'
    config.write_text('{"confirmed_events":[]}')
    before=config.read_bytes()
    alias=tmp_path/'summary'
    alias.hardlink_to(config)
    monkeypatch.setattr(watch,'DATA',data)
    monkeypatch.setattr(watch,'load_registry',lambda: [SimpleNamespace(venue_id='real',venue_name='テスト')])
    called=[]
    monkeypatch.setattr(watch,'collect_review',lambda **kw: called.append(kw) or dict(source_results=[],unmeasured_or_blocked_windows=0))
    assert watch.main(['--source','bleague-asue','--venue-id','real','--start','2026-11-08',
        '--through','2026-11-30','--private-dir',str(tmp_path/'drafts'),'--summary',str(alias)])==2
    assert config.read_bytes()==before and called==[]

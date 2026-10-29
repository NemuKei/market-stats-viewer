from copy import deepcopy

import pytest

from scripts.compare_category_reviews import compare


def fixture():
    old = dict(events=[dict(event_uid='day', title='Fictional Music Fes', start_date='2026-01-01', event_category='未分類')])
    new = deepcopy(old)
    new['events'][0]['event_category'] = 'コンサート'
    previous = dict(database_sha256='a' * 64, row_count=1, before={'コンサート': 1}, rule_sha256='b' * 64,
                    changes=[dict(event_uid='db', title='Fictional Music Fes', date='2026-01-01', old_category='コンサート', new_category='未分類')])
    current = dict(previous, changes=[], rule_sha256='c' * 64)
    return old, new, previous, current


def test_restoration_to_stored_category_is_not_lost_from_comparison():
    report = compare(*fixture())
    assert report['saved']['restored_music'][0]['event_uid'] == 'day'
    assert report['database']['restored_music'][0]['event_uid'] == 'db'
    assert report['database']['removed_music'] == []


def test_rejects_changed_inputs_instead_of_counting_them_as_category_corrections():
    args = fixture()
    args[1]['events'][0]['start_date'] = '2026-01-02'
    with pytest.raises(ValueError, match='outside category'):
        compare(*args)
    args = fixture()
    args[3]['database_sha256'] = 'd' * 64
    with pytest.raises(ValueError, match='baseline changed'):
        compare(*args)

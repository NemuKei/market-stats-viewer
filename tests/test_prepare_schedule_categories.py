from copy import deepcopy
import hashlib
import json

import pytest

from scripts.prepare_schedule_categories import prepare, revise_categories
from test_public_schedule_days import package


def test_category_only_copy_and_deterministic_rules(tmp_path):
    original, baseline = package(tmp_path)
    source = deepcopy(original)
    source['events'][0]['title'] = 'DEEN LIVE JOY-Break27'
    uid = source['events'][0]['event_uid']
    source['schedule_metadata'][uid]['observedTitles'] = [source['events'][0]['title']]
    candidate, changes = revise_categories(source)
    assert candidate['events'][0]['event_category'] == 'コンサート'
    assert changes[0]['rule'] == 'concert_keyword:live'
    assert source['events'][0]['event_category'] == '未分類'
    restored = deepcopy(candidate)
    for before, after in zip(source['events'], restored['events']):
        after['event_category'] = before['event_category']
    assert restored == source
    assert revise_categories(source) == (candidate, changes)


def test_prepare_pins_inputs_and_refuses_to_overwrite(tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    package(source_dir)
    path = source_dir / 'public_schedule_days.json'
    raw = path.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    root = tmp_path / 'review'
    result = prepare(source_dir, root, expected)
    assert result['count'] == 3
    assert path.read_bytes() == raw
    assert (root / 'category-diff.csv').read_text().count('\n') == 4
    assert json.loads((root / 'category-summary.json').read_text())['status'] == 'review_only'
    with pytest.raises(FileExistsError):
        prepare(source_dir, root, expected)
    with pytest.raises(ValueError):
        prepare(source_dir, tmp_path / 'bad', '0' * 64)
    assert not (tmp_path / 'bad').exists()

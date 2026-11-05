from copy import deepcopy
import hashlib
import json

import pytest

from scripts.prepare_schedule_categories import apply_reviewed_corrections, prepare, revise_categories
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


def review_for(source, source_sha):
    row = source['events'][0]
    return dict(schema_version=1, input_public_sha256=source_sha, corrections=[dict(
        event_uid=row['event_uid'], title=row['title'], start_date=row['start_date'],
        venue_name=row['venue_name'], old_category=row['event_category'], new_category='コンサート',
        source_class='artist_official', evidence_url='https://artist.example.test/concert',
        evidence_summary='Fictional concert, date and venue.', verified_on='2026-11-05')])


def test_reviewed_mode_changes_only_exact_row_and_preserves_review(tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    source, _ = package(source_dir)
    raw = (source_dir / 'public_schedule_days.json').read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    review = review_for(source, source_sha)
    review_path = tmp_path / 'review.json'
    review_path.write_text(json.dumps(review))
    root = tmp_path / 'output'
    summary = prepare(source_dir, root, source_sha, review_path)
    candidate = json.loads((root / 'public_schedule_days.json').read_bytes())
    assert summary['changed_count'] == 1
    assert summary['reviewed_corrections_sha256'] == hashlib.sha256(review_path.read_bytes()).hexdigest()
    assert (root / 'reviewed-corrections.json').read_bytes() == review_path.read_bytes()
    assert (root / 'public_schedule_baseline.json').read_bytes() == (source_dir / 'public_schedule_baseline.json').read_bytes()
    assert candidate['events'][0]['event_category'] == 'コンサート'
    candidate['events'][0]['event_category'] = source['events'][0]['event_category']
    assert candidate == source
    assert (source_dir / 'public_schedule_days.json').read_bytes() == raw


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(input_public_sha256='0' * 64),
    lambda r: r['corrections'].append(deepcopy(r['corrections'][0])),
    lambda r: r['corrections'][0].update(event_uid='missing'),
    lambda r: r['corrections'][0].update(start_date='2026-01-01'),
    lambda r: r['corrections'][0].update(title='changed'),
    lambda r: r['corrections'][0].update(venue_name='changed'),
    lambda r: r['corrections'][0].update(old_category='その他'),
    lambda r: r['corrections'][0].update(new_category='未分類'),
    lambda r: r['corrections'][0].update(evidence_url='http://artist.example.test/concert'),
    lambda r: r['corrections'][0].update(evidence_summary=''),
    lambda r: r['corrections'][0].update(verified_on='yesterday'),
    lambda r: r['corrections'][0].update(source_class='social_media'),
])
def test_reviewed_mode_rejects_stale_or_incomplete_evidence(tmp_path, mutation):
    source, _ = package(tmp_path)
    source_sha = hashlib.sha256((tmp_path / 'public_schedule_days.json').read_bytes()).hexdigest()
    review = review_for(source, source_sha)
    mutation(review)
    with pytest.raises(ValueError):
        apply_reviewed_corrections(source, review, source_sha)


def test_failed_review_and_repository_output_create_nothing(tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    source, _ = package(source_dir)
    source_sha = hashlib.sha256((source_dir / 'public_schedule_days.json').read_bytes()).hexdigest()
    review = review_for(source, source_sha)
    review['corrections'][0]['venue_name'] = 'different venue'
    review_path = tmp_path / 'review.json'
    review_path.write_text(json.dumps(review))
    output = tmp_path / 'rejected'
    with pytest.raises(ValueError, match='venue_name mismatch'):
        prepare(source_dir, output, source_sha, review_path)
    assert not output.exists()

    repository = tmp_path / 'repository'
    repository.mkdir()
    (repository / '.git').mkdir()
    with pytest.raises(ValueError, match='Git-free'):
        prepare(source_dir, repository / 'output', source_sha)
    assert not (repository / 'output').exists()

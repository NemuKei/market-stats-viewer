"""Compare reviewed predictions without changing source rows or databases."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def _changes(before, after):
    rows = [dict(event_uid=uid, title=after[uid]['title'], date=after[uid]['date'],
                 previous_category=before[uid]['category'], new_category=after[uid]['category'])
            for uid in sorted(before) if before[uid]['category'] != after[uid]['category']]
    return dict(changed_count=len(rows), transitions=dict(Counter(r['previous_category'] + ' -> ' + r['new_category'] for r in rows)),
                restored_music=[r for r in rows if r['previous_category'] == '未分類' and r['new_category'] == 'コンサート'],
                removed_music=[r for r in rows if r['previous_category'] == 'コンサート' and r['new_category'] != 'コンサート'], changes=rows)


def compare(previous_asset, current_asset, previous_impact, current_impact):
    old = {r['event_uid']: r for r in previous_asset['events']}
    new = {r['event_uid']: r for r in current_asset['events']}
    if set(old) != set(new) or any({k:v for k,v in old[uid].items() if k != 'event_category'} !=
                                 {k:v for k,v in new[uid].items() if k != 'event_category'} for uid in old):
        raise ValueError('saved schedules differ outside category')
    if any(previous_impact[k] != current_impact[k] for k in ('database_sha256', 'row_count', 'before')):
        raise ValueError('database baseline changed between reviews')
    saved = _changes({uid: dict(category=r['event_category'], title=r['title'], date=r['start_date']) for uid,r in old.items()},
                     {uid: dict(category=r['event_category'], title=r['title'], date=r['start_date']) for uid,r in new.items()})
    a, b = ({r['event_uid']: r for r in report['changes']} for report in (previous_impact, current_impact))
    before, after = {}, {}
    for uid in a.keys() | b.keys():
        record = b.get(uid, a.get(uid))
        baseline = record['old_category']
        if uid in a and uid in b and a[uid]['old_category'] != b[uid]['old_category']:
            raise ValueError('stored category differs between reviews')
        before[uid] = dict(category=a[uid]['new_category'] if uid in a else baseline, title=record['title'], date=record['date'])
        after[uid] = dict(category=b[uid]['new_category'] if uid in b else baseline, title=record['title'], date=record['date'])
    return dict(status='review_only', previous_rule_sha256=previous_impact['rule_sha256'],
                current_rule_sha256=current_impact['rule_sha256'], database_row_count=current_impact['row_count'],
                saved=saved, database=_changes(before, after),
                database_original_concert_exclusions=[r for r in current_impact['changes']
                    if r['old_category'] == 'コンサート' and r['new_category'] != 'コンサート'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-review', type=Path, required=True)
    parser.add_argument('--current-review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def read(root, name):
        return json.loads((root / name).read_bytes())
    report = compare(read(args.previous_review, 'public_schedule_days.preview.json'),
        read(args.current_review, 'public_schedule_days.preview.json'),
        read(args.previous_review, 'db-impact.json'), read(args.current_review, 'db-impact.json'))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()

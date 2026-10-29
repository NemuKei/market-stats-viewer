"""Prepare a category-only public schedule package for review, never publish it.

Observation provenance remains unchanged: categories are derived from the exact
public title. Rule/input/output hashes and reasons are kept in the review report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

from .build_public_schedule_days import validate_public_asset, validate_public_package
from .events import category


def revise_categories(source):
    validate_public_asset(source)
    if not source['events']:
        raise ValueError('category review requires nonempty saved schedules')
    result = deepcopy(source)
    changes = []
    for row in result['events']:
        old = row['event_category']
        new, reason = category.classify_event_category_with_reason(row['title'], '', '')
        row['event_category'] = new
        changes.append(dict(event_uid=row['event_uid'], old_category=old, new_category=new,
                            rule=reason, title=row['title'], venue_name=row['venue_name'], date=row['start_date']))
    validate_public_asset(result)
    return result, changes


def prepare(source_dir: Path, output_root: Path, expected_sha: str):
    # Exclusive new output outside repositories; never replace an input or a public asset.
    output_root = output_root.absolute()
    if '..' in output_root.parts or any(p.is_symlink() or (p / '.git').exists() for p in [output_root, *output_root.parents]):
        raise ValueError('output must be Git-free and without symlinks')
    validate_public_package(source_dir, expected_public_sha256=expected_sha)
    raw = (source_dir / 'public_schedule_days.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('source changed during preparation')
    result, changes = revise_categories(json.loads(raw))
    data = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
    summary = dict(status='review_only', input_public_sha256=expected_sha,
                   output_public_sha256=hashlib.sha256(data).hexdigest(),
                   rule_sha256=hashlib.sha256(Path(category.__file__).read_bytes()).hexdigest(),
                   count=len(changes), changed_count=sum(r['old_category'] != r['new_category'] for r in changes),
                   before=dict(Counter(r['old_category'] for r in changes)),
                   after=dict(Counter(r['new_category'] for r in changes)),
                   samples={name: [r for r in changes if r['new_category'] == name][:10]
                            for name in sorted({r['new_category'] for r in changes})})
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / 'public_schedule_days.json').write_bytes(data)
    (output_root / 'public_schedule_baseline.json').write_bytes((source_dir / 'public_schedule_baseline.json').read_bytes())
    (output_root / 'category-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    with (output_root / 'category-diff.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(changes[0]))
        writer.writeheader()
        writer.writerows(changes)
    validate_public_package(output_root)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--expected-public-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_root, args.expected_public_sha256), ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Prepare a category-only public schedule package for review, never publish it.

Observation provenance remains unchanged. The default derives categories from
public titles; an explicit, hash-pinned review can instead correct individual
rows using separately documented evidence. Neither mode publishes the result.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

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


def apply_reviewed_corrections(source, review, expected_sha):
    """Apply only exact, reviewed row corrections; reject stale or partial reviews."""
    validate_public_asset(source)
    if not isinstance(review, dict) or review.get('schema_version') != 1:
        raise ValueError('invalid category review schema')
    if review.get('input_public_sha256') != expected_sha:
        raise ValueError('category review input hash does not match source')
    entries = review.get('corrections')
    if not isinstance(entries, list) or not entries:
        raise ValueError('category review requires corrections')
    indexed = {}
    required = ('event_uid', 'title', 'start_date', 'venue_name', 'old_category',
                'new_category', 'source_class', 'evidence_url', 'evidence_summary', 'verified_on')
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in required):
            raise ValueError('incomplete category correction')
        uid = entry['event_uid']
        if uid in indexed:
            raise ValueError('duplicate category correction: ' + uid)
        if entry['source_class'] not in {'venue_official', 'artist_official', 'promoter_official'}:
            raise ValueError('unsupported evidence source class: ' + uid)
        url = urlsplit(entry['evidence_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('invalid evidence URL: ' + uid)
        try:
            date.fromisoformat(entry['verified_on'])
        except ValueError as exc:
            raise ValueError('invalid verification date: ' + uid) from exc
        if entry['old_category'] == entry['new_category'] or entry['new_category'] not in {
            category.EVENT_CATEGORY_CONCERT, category.EVENT_CATEGORY_BASEBALL,
            category.EVENT_CATEGORY_OTHER, category.EVENT_CATEGORY_UNKNOWN,
        }:
            raise ValueError('invalid category transition: ' + uid)
        indexed[uid] = entry

    result = deepcopy(source)
    changes = []
    matched = set()
    for row in result['events']:
        old = row['event_category']
        entry = indexed.get(row['event_uid'])
        reason = 'preserved'
        if entry:
            for key in ('title', 'start_date', 'venue_name'):
                if row[key] != entry[key]:
                    raise ValueError(f'category review {key} mismatch: {row["event_uid"]}')
            if old != entry['old_category']:
                raise ValueError('category review old category mismatch: ' + row['event_uid'])
            row['event_category'] = entry['new_category']
            reason = 'reviewed:' + entry['evidence_url']
            matched.add(row['event_uid'])
        changes.append(dict(event_uid=row['event_uid'], old_category=old,
                            new_category=row['event_category'], rule=reason, title=row['title'],
                            venue_name=row['venue_name'], date=row['start_date']))
    if matched != set(indexed):
        raise ValueError('category review contains unknown event IDs')
    validate_public_asset(result)
    return result, changes


def prepare(source_dir: Path, output_root: Path, expected_sha: str, reviewed_corrections: Path | None = None):
    # Exclusive new output outside repositories; never replace an input or a public asset.
    output_root = output_root.absolute()
    if '..' in output_root.parts or any(p.is_symlink() or (p / '.git').exists() for p in [output_root, *output_root.parents]):
        raise ValueError('output must be Git-free and without symlinks')
    validate_public_package(source_dir, expected_public_sha256=expected_sha)
    raw = (source_dir / 'public_schedule_days.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('source changed during preparation')
    review_raw = reviewed_corrections.read_bytes() if reviewed_corrections is not None else None
    if review_raw is None:
        result, changes = revise_categories(json.loads(raw))
    else:
        result, changes = apply_reviewed_corrections(json.loads(raw), json.loads(review_raw), expected_sha)
    data = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
    summary = dict(status='review_only', input_public_sha256=expected_sha,
                   output_public_sha256=hashlib.sha256(data).hexdigest(),
                   rule_sha256=hashlib.sha256(Path(category.__file__).read_bytes()).hexdigest(),
                   count=len(changes), changed_count=sum(r['old_category'] != r['new_category'] for r in changes),
                   before=dict(Counter(r['old_category'] for r in changes)),
                   after=dict(Counter(r['new_category'] for r in changes)),
                   samples={name: [r for r in changes if r['new_category'] == name][:10]
                            for name in sorted({r['new_category'] for r in changes})})
    if review_raw is not None:
        summary['reviewed_corrections_sha256'] = hashlib.sha256(review_raw).hexdigest()
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / 'public_schedule_days.json').write_bytes(data)
    (output_root / 'public_schedule_baseline.json').write_bytes((source_dir / 'public_schedule_baseline.json').read_bytes())
    if review_raw is not None:
        (output_root / 'reviewed-corrections.json').write_bytes(review_raw)
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
    parser.add_argument('--reviewed-corrections', type=Path,
                        help='Apply only the individually reviewed corrections in this JSON file')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_root, args.expected_public_sha256,
                             args.reviewed_corrections), ensure_ascii=False))


if __name__ == '__main__':
    main()

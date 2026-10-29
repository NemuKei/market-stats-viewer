"""Read-only category impact report for the current event database."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from .events import category


def audit(database: Path):
    raw_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        records = connection.execute('SELECT event_uid, title, start_date, artist_name_resolved, description, event_category FROM events ORDER BY event_uid').fetchall()
    changes = []
    after = Counter()
    for uid, title, day, artist, description, old in records:
        new, rule = category.classify_event_category_with_reason(title, artist, description)
        after[new] += 1
        if old != new:
            changes.append(dict(event_uid=uid, title=title, date=day, old_category=old, new_category=new, rule=rule))
    if hashlib.sha256(database.read_bytes()).hexdigest() != raw_hash:
        raise ValueError('database changed during read-only audit')
    return dict(database_sha256=raw_hash, rule_sha256=hashlib.sha256(Path(category.__file__).read_bytes()).hexdigest(),
                row_count=len(records), changed_count=len(changes),
                before=dict(Counter(row[-1] for row in records)), after=dict(after),
                transitions=dict(Counter(r['old_category'] + ' -> ' + r['new_category'] for r in changes)),
                concert_drop_count=sum(r['old_category'] == 'コンサート' for r in changes), changes=changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.database.resolve() == args.output.resolve():
        raise ValueError('output must not replace the database')
    args.output.write_text(json.dumps(audit(args.database), ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()

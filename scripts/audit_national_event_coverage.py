"""Read-only coverage inventory. No HTTP, DB writes, Git writes, or source changes.

Configuration presence is not fetch success or a claim of nationwide completeness.
Print JSON to stdout. Exit 0: report produced; 1: identity/orphan blockers;
2: invalid or incomplete input. A zero exit code is not deployment approval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import unicodedata
from urllib.parse import urlparse

PREFECTURES = (
    '北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県','茨城県','栃木県','群馬県',
    '埼玉県','千葉県','東京都','神奈川県','新潟県','富山県','石川県','福井県','山梨県','長野県',
    '岐阜県','静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県','奈良県','和歌山県',
    '鳥取県','島根県','岡山県','広島県','山口県','徳島県','香川県','愛媛県','高知県','福岡県',
    '佐賀県','長崎県','熊本県','大分県','宮崎県','鹿児島県','沖縄県',
)


def _normal(value: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def _text(row: dict, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing or invalid {key}')
    return value.strip()


def _index(rows: list, label: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f'{label}: expected a list')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f'{label}: expected object rows')
        key = _text(row, 'venue_id')
        if key in result:
            raise ValueError(f'{label}: duplicate venue_id {key}')
        result[key] = row
    return result


def _enabled(row: dict) -> bool:
    value = row.get('is_enabled')
    if value not in ('0', '1'):
        raise ValueError('is_enabled must be 0 or 1')
    return value == '1'


def _capacity(row: dict) -> int | None:
    value = row.get('capacity')
    if value == '':
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError('capacity must be an unsigned integer or empty')
    return int(value)


def audit(registry: list[dict], discovery: dict, ticketjam: list[dict]) -> dict:
    """Inspect configured routes without mutating any input or inferring publication rights."""
    venues = _index(registry, 'registry')
    if not isinstance(discovery, dict) or 'watch_venues' not in discovery:
        raise ValueError('discovery must explicitly contain watch_venues')
    watches = _index(discovery['watch_venues'], 'watch_venues')
    tickets = _index(ticketjam, 'ticketjam')
    ticket_flags = {key: _enabled(row) for key, row in tickets.items()}
    names: dict[str, set[str]] = {}
    for key, row in venues.items():
        names.setdefault(_normal(_text(row, 'venue_name')), set()).add(key)
    for key, row in watches.items():
        aliases = row.get('aliases', [])
        if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError('aliases must be a list of nonempty strings')
        for name in [_text(row, 'venue_name'), *aliases]:
            names.setdefault(_normal(name), set()).add(key)

    conflicts = []
    for alias, owners in sorted(names.items()):
        if len(owners) > 1:
            ordered = sorted(owners)
            for i, owner in enumerate(ordered):
                for other in ordered[i + 1:]:
                    conflicts.append(dict(alias=alias, owner_id=owner, other_id=other,
                                          action='manual_identity_review_no_auto_merge'))
    rows, name_reviews = [], []
    prefectures = [dict(pref_code=f'{i:02d}', pref_name=name, registered=0,
                        official_enabled=0, web_watch_configured=0, ticketjam_enabled=0,
                        review_status='not_assessed')
                   for i, name in enumerate(PREFECTURES, 1)]
    for key, row in sorted(venues.items()):
        pref = _text(row, 'pref_code')
        if pref not in {f'{i:02d}' for i in range(1, 48)}:
            raise ValueError(f'{key}: pref_code must be 01..47')
        name = _text(row, 'venue_name')
        official = _enabled(row)
        capacity = _capacity(row)
        url = row.get('official_url') or ''
        if not isinstance(url, str):
            raise ValueError('official_url must be a string')
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        url_review = []
        if parsed.scheme not in ('http', 'https') or not host:
            url_review.append('missing_or_invalid_official_url')
        if any(host == d or host.endswith('.'+d) for d in ('ticketjam.jp', 'wikipedia.org')):
            url_review.append('reference_only_domain')
        if parsed.username or parsed.password:
            raise ValueError('Credential-bearing URL is not allowed')
        for source, collection in [('web_watch', watches), ('ticketjam', tickets)]:
            if key in collection:
                other_name = _text(collection[key], 'venue_name')
                if _normal(name) != _normal(other_name):
                    name_reviews.append(dict(venue_id=key, source=source,
                        registry_name=name, other_name=other_name,
                        action='review_names_not_a_proven_conflict'))
        item = dict(venue_id=key, venue_name=name, pref_code=pref,
                    capacity_from_registry=capacity, official_url=url,
                    official_enabled=official, web_watch_configured=key in watches,
                    ticketjam_enabled=ticket_flags.get(key, False),
                    scope_review='required', runtime_fetch_status='not_measured',
                    url_review=url_review)
        rows.append(item)
        area = prefectures[int(pref)-1]
        area['registered'] += 1
        for field in ('official_enabled', 'web_watch_configured', 'ticketjam_enabled'):
            area[field] += int(item[field])
    summary = dict(registered_venues=len(rows), official_enabled=sum(r['official_enabled'] for r in rows),
                   web_watch_configured=len(watches), ticketjam_rows=len(tickets),
                   ticketjam_enabled=sum(ticket_flags.values()),
                   represented_prefectures=sum(p['registered'] > 0 for p in prefectures),
                   unknown_capacity=sum(r['capacity_from_registry'] is None for r in rows))
    return dict(report_version=1, scope='current_registry_only_not_national_census',
                runtime_coverage_verified=False, summary=summary,
                orphan_web_watch_ids=sorted(set(watches)-set(venues)),
                orphan_ticketjam_ids=sorted(set(tickets)-set(venues)),
                identity_conflicts=conflicts, name_reviews=name_reviews,
                prefectures=prefectures, venues=rows)


def _csv_bytes(raw: bytes, required: set[str]) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError('CSV is missing required headers: '+', '.join(sorted(required)))
    rows = list(reader)
    for row in rows:
        if None in row or any(row.get(field) is None for field in required):
            raise ValueError('CSV row has missing or extra required values')
    return rows


def read_inputs(registry: Path, discovery: Path, ticketjam: Path) -> dict:
    raw_registry = registry.read_bytes()
    rows = _csv_bytes(raw_registry, {'venue_id','venue_name','pref_code','capacity','is_enabled','official_url'})
    raw_discovery, raw_ticketjam = discovery.read_bytes(), ticketjam.read_bytes()
    watch = json.loads(raw_discovery.decode('utf-8-sig'))
    tickets = _csv_bytes(raw_ticketjam, {'venue_id','venue_name','is_enabled'})
    report = audit(rows, watch, tickets)
    report['input_sha256'] = {name: hashlib.sha256(raw).hexdigest()
        for name, raw in [('registry',raw_registry),('discovery',raw_discovery),('ticketjam',raw_ticketjam)]}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=Path('data/venue_registry.csv'))
    parser.add_argument('--discovery', type=Path, default=Path('data/venue_web_discovery_config.json'))
    parser.add_argument('--ticketjam', type=Path, default=Path('data/ticketjam_venue_pages.csv'))
    args = parser.parse_args(argv)
    try:
        report = read_inputs(args.registry, args.discovery, args.ticketjam)
    except (OSError, ValueError, UnicodeError, csv.Error) as exc:
        print(f'Coverage audit failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report['identity_conflicts'] or report['orphan_web_watch_ids'] or report['orphan_ticketjam_ids']))


if __name__ == '__main__':
    raise SystemExit(main())

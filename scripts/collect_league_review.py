"""Collect known league calendars into private review drafts and counts only.

Uses existing parsers and the existing inbox shape. Does not write the inbox,
config, IDs, DB, LP or any public asset. No new cron, reviewer or approval store.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlsplit

import requests

from .events.registry import load_registry
from .prepare_league_programme_inbox import collect as collect_programmes, SOURCES as SOURCE_ROUTES
from .update_events_data import DomainThrottle, ThrottledSession

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / 'data'
# SV League HTTP access is still restricted. Its ordinary-browser review stays
# manual; do not silently substitute another endpoint or create many retries.
SOURCES = ('jleague-ftokyo', 'jleague-tokyov', 'bleague-ariake', 'bleague-asue', 'leagueone')


def validate_private_dir(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('private directory must not contain parent traversal')
    if any(p.is_symlink() or (p / '.git').exists() for p in (path, *path.parents)):
        raise ValueError('private directory must be outside Git and symlink paths')
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ValueError('private drafts must be outside the public checkout')
    if path.exists():
        raise ValueError('private draft directory must be new')
    return path


def validate_summary(path):
    path = Path(path).absolute()
    if ('..' in path.parts or path == REPO_ROOT or REPO_ROOT in path.parents
            or any(p.is_symlink() or (p / '.git').exists() for p in (path, *path.parents))):
        raise ValueError('summary must stay outside public/Git/symlink/traversal paths')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('summary requires a regular file without hardlinks')
    return path


def append_summary(path, report):
    path = validate_summary(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('summary must not alias another file')
        with os.fdopen(fd, 'a', closefd=False) as stream:
            stream.write('\n### League review drafts (counts only)\n\n')
            stream.write('|Route|From|Through|State|Candidates|Known|Other source|Changed|Review|\n|---|---|---|---|---:|---:|---:|---:|---:|\n')
            for r in report['source_results']:
                stream.write(f"|{r['source']}|{r['start']}|{r['through']}|{r['status']}|{r['candidate_count']}|"
                    f"{r['already_confirmed_exact']}|{r['known_match_other_source']}|{r['changed_known_match']}|{r['unreviewed_candidate']}|\n")
            stream.write('\nPrivate drafts are not uploaded as artifacts or committed. SV League remains a separate access review.\n')
    finally:
        os.close(fd)


def months(start, through):
    while start <= through:
        following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        end = min(through, following - timedelta(days=1))
        yield start, end
        start = following


def match_key(row):
    # Diagnostic exact comparison only. Different participants/facilities/dates
    # cannot become the same match through fuzzy normalization or title guesses.
    return tuple(row.get(k) or '' for k in ('event_start_date','venue_name','artist_name','url'))


def collect_review(*, sources, start, through, venue_names, private_dir,
                   collect=collect_programmes, confirmed=(), session=None):
    if (not sources or len(sources) != len(set(sources)) or set(sources) - set(SOURCES)
            or not venue_names or start > through or (through - start).days > 92):
        raise ValueError('known routes, selected venues and at most 93 days required')
    private_dir = validate_private_dir(private_dir)
    private_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    known, known_facts = {}, {}
    for row in confirmed:
        known.setdefault(match_key(row), set()).add(row.get('event_start_time') or '')
        known_facts.setdefault(match_key(row)[:3], set()).add(row.get('event_start_time') or '')
    session = session or ThrottledSession(requests.Session(), DomainThrottle(min_interval=3.0))
    results, blocked_hosts = [], set()
    for source in sources:
        source_host = urlsplit(SOURCE_ROUTES[source][1]).hostname
        for first, last in months(start, through):
            item = dict(source=source,start=first.isoformat(),through=last.isoformat(),
                observed_page_count=0,candidate_count=0,already_confirmed_exact=0,
                changed_known_match=0,known_match_other_source=0,unreviewed_candidate=0)
            results.append(item)
            if source_host in blocked_hosts:
                item['status'] = 'not_attempted_after_access_denial'
                continue
            try:
                draft, skipped, pages = collect(source,first,last,venue_names,session=session)
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else None
                denied = code in {401,403,429}
                if denied:
                    blocked_hosts.add(source_host)
                item.update(status='http_access_denied' if denied else 'http_failed',http_status=code)
                continue
            except requests.RequestException:
                item['status'] = 'transport_failed'
                continue
            except ValueError:
                item['status'] = 'parse_or_validation_failed'
                continue
            # Private file retains actual observed facts for this isolated run.
            # No draft facts, detail URLs, raw text or error strings enter logs.
            with (private_dir / f'{source}-{first:%Y-%m}.json').open('x') as stream:
                json.dump(draft,stream,ensure_ascii=False,indent=2)
                stream.write('\n')
            item.update(status='draft_requires_review' if draft['candidates'] else 'empty_unverified',
                candidate_count=len(draft['candidates']),observed_page_count=pages,
                skipped_count=sum(skipped.values()))
            for row in draft['candidates']:
                key = match_key(row)
                old, facts = known.get(key), known_facts.get(key[:3])
                clock = row.get('event_start_time') or ''
                if facts is None:
                    item['unreviewed_candidate'] += 1
                elif clock not in facts:
                    item['changed_known_match'] += 1
                elif old is not None and clock in old:
                    item['already_confirmed_exact'] += 1
                else:
                    item['known_match_other_source'] += 1
    return dict(report_version=1,publication_changes=0,coverage_verified=False,source_results=results,
        unmeasured_or_blocked_windows=sum(r['status'] != 'draft_requires_review' for r in results),
        interpretation='counts_only_private_drafts_require_fact_link_ID_review_no_auto_adoption',
        excluded_routes={'svleague-men':'HTTP_access_requires_separate_normal_browser_review',
                         'svleague-women':'HTTP_access_requires_separate_normal_browser_review'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=SOURCES,action='append',required=True)
    parser.add_argument('--venue-id',action='append',required=True)
    parser.add_argument('--start',type=date.fromisoformat,required=True)
    parser.add_argument('--through',type=date.fromisoformat,required=True)
    parser.add_argument('--private-dir',type=Path,required=True)
    parser.add_argument('--summary',type=Path)
    args = parser.parse_args(argv)
    try:
        venues = {v.venue_id:v.venue_name for v in load_registry()}
        if set(args.venue_id) - set(venues):
            raise ValueError('unknown registered venue ID')
        config = DATA / 'venue_web_discovery_config.json'
        before = hashlib.sha256(config.read_bytes()).hexdigest()
        if args.summary:
            validate_summary(args.summary)
        report = collect_review(sources=args.source,start=args.start,through=args.through,
            venue_names={venues[k] for k in args.venue_id},private_dir=args.private_dir,
            confirmed=json.loads(config.read_bytes())['confirmed_events'])
        if hashlib.sha256(config.read_bytes()).hexdigest() != before:
            raise ValueError('confirmation input changed during collection; discard this diagnostic')
        if args.summary:
            append_summary(args.summary, report)
        print(json.dumps(report,sort_keys=True))
        if report['unmeasured_or_blocked_windows'] or any(r['changed_known_match'] or r['unreviewed_candidate'] or r['known_match_other_source'] for r in report['source_results']):
            print('::warning::League review is pending or unmeasured; other updates can continue. No publication changed.')
        return 0
    except (OSError, ValueError) as exc:
        print(f'League review preparation failed: {type(exc).__name__}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

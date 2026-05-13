"""Audit K-Style event-signal coverage without mutating local data.

The audit separates four causes that can all look like "missing events":

- frequency/recency risk: the current cadence may not revisit candidates soon enough
- entry risk: the candidate appears in one entry point but not another
- page-limit risk: the candidate is beyond the configured scan limit
- parser risk: the article is discovered, but current parser logic cannot extract dates
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .signals.sources.kstyle import KstyleMusicSource
from .signals.types import SignalSourceRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNALS_DB_PATH = REPO_ROOT / "data" / "event_signals.sqlite"
DEFAULT_SOURCE_URL = (
    "https://kstyle.com/search.ksn?"
    "searchWord=%E2%96%A0%E5%85%AC%E6%BC%94%E6%83%85%E5%A0%B1"
)
DEFAULT_UPDATE_FREQUENCY_HOURS = 12
USER_AGENT = "market-stats-viewer-signals-bot/1.0 (+https://deltahelmlab.com/)"
KNOWN_COVERAGE_SAMPLE_URLS = [
    "https://kstyle.com/article.ksn?articleNo=2278604",
    "https://kstyle.com/article.ksn?articleNo=2277247",
    "https://kstyle.com/article.ksn?articleNo=2276584",
    "https://kstyle.com/article.ksn?articleNo=2276235",
    "https://kstyle.com/article.ksn?articleNo=2276393",
]


@dataclass
class Candidate:
    url: str
    title: str
    published_at_utc: str
    entry_points: set[str] = field(default_factory=set)
    min_search_page: int | None = None
    sitemap_rank: int | None = None

    def merge(
        self,
        *,
        title: str,
        published_at_utc: str,
        entry_point: str,
        search_page: int | None = None,
        sitemap_rank: int | None = None,
    ) -> None:
        if title and len(title) > len(self.title):
            self.title = title
        if published_at_utc and not self.published_at_utc:
            self.published_at_utc = published_at_utc
        self.entry_points.add(entry_point)
        if search_page is not None:
            if self.min_search_page is None or search_page < self.min_search_page:
                self.min_search_page = search_page
        if sitemap_rank is not None:
            if self.sitemap_rank is None or sitemap_rank < self.sitemap_rank:
                self.sitemap_rank = sitemap_rank


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit K-Style news article coverage against event_signals.sqlite"
    )
    parser.add_argument("--db-path", default=str(SIGNALS_DB_PATH))
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--pages", type=int, default=8)
    parser.add_argument("--sitemap-max-candidates", type=int, default=80)
    parser.add_argument("--max-detail-fetch", type=int, default=80)
    parser.add_argument(
        "--extra-list-url",
        action="append",
        default=[],
        help="Additional K-Style list/category/newest URL to scan once.",
    )
    parser.add_argument(
        "--known-url",
        action="append",
        default=[],
        help="Known K-Style article URL to include as a regression coverage sample.",
    )
    parser.add_argument(
        "--skip-default-known-samples",
        action="store_true",
        help="Do not include the built-in K-Style coverage regression samples.",
    )
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--indent", type=int, default=2)
    return parser.parse_args()


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def load_source_record(db_path: Path) -> SignalSourceRecord:
    if not db_path.exists():
        return SignalSourceRecord(
            source_id="kstyle_music",
            source_name="Kstyle MUSIC",
            source_url=DEFAULT_SOURCE_URL,
            source_type="html_list",
            config_json=None,
            is_enabled=True,
        )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_id, source_name, source_url, source_type, config_json,
                   is_enabled, last_signature
            FROM signal_sources
            WHERE source_id = 'kstyle_music'
            """
        ).fetchone()
    if row is None:
        return SignalSourceRecord(
            source_id="kstyle_music",
            source_name="Kstyle MUSIC",
            source_url=DEFAULT_SOURCE_URL,
            source_type="html_list",
            config_json=None,
            is_enabled=True,
        )
    return SignalSourceRecord(
        source_id=str(row[0]),
        source_name=str(row[1]),
        source_url=str(row[2]),
        source_type=str(row[3]),
        config_json=str(row[4] or ""),
        is_enabled=bool(row[5]),
        last_signature=str(row[6] or ""),
    )


def load_existing_kstyle(db_path: Path) -> tuple[set[str], dict[str, int]]:
    if not db_path.exists():
        return set(), {}
    urls: set[str] = set()
    occurrence_counts: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        for url, count in conn.execute(
            """
            SELECT url, COUNT(*)
            FROM signals
            WHERE source_id = 'kstyle_music'
            GROUP BY url
            """
        ):
            clean_url = str(url or "").strip()
            if not clean_url:
                continue
            urls.add(clean_url)
            occurrence_counts[clean_url] = int(count or 0)
    return urls, occurrence_counts


def add_candidate(
    candidates: dict[str, Candidate],
    *,
    url: str,
    title: str,
    published_at_utc: str,
    entry_point: str,
    search_page: int | None = None,
    sitemap_rank: int | None = None,
) -> None:
    clean_url = url.strip()
    if not clean_url:
        return
    existing = candidates.get(clean_url)
    if existing is None:
        existing = Candidate(
            url=clean_url,
            title=title.strip(),
            published_at_utc=published_at_utc.strip(),
        )
        candidates[clean_url] = existing
    existing.merge(
        title=title.strip(),
        published_at_utc=published_at_utc.strip(),
        entry_point=entry_point,
        search_page=search_page,
        sitemap_rank=sitemap_rank,
    )


def collect_sitemap_candidates(
    source: KstyleMusicSource,
    candidates: dict[str, Candidate],
    *,
    max_candidates: int,
) -> int:
    resp = source._get_with_retry(source.RECENT_NEWS_SITEMAP_URL, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    parsed = source._parse_recent_news_sitemap(resp.text)
    articles_scanned = 0
    for rank, (title, abs_url, published_at_utc) in enumerate(parsed, start=1):
        articles_scanned += 1
        if rank > max_candidates:
            break
        if not source._is_event_candidate(title, title):
            continue
        add_candidate(
            candidates,
            url=abs_url,
            title=title,
            published_at_utc=published_at_utc,
            entry_point="sitemap",
            sitemap_rank=rank,
        )
    return min(articles_scanned, max_candidates)


def collect_search_candidates(
    source: KstyleMusicSource,
    candidates: dict[str, Candidate],
    *,
    source_url: str,
    pages: int,
) -> int:
    articles_scanned = 0
    search_urls = source._resolve_search_urls(
        source_url,
        {"search_words": list(source.SEARCH_WORDS)},
    )
    for search_url in search_urls:
        for page_num in range(1, max(1, pages) + 1):
            page_url = source._with_page_param(search_url, page_num)
            resp = source._get_with_retry(page_url, timeout=30)
            if resp.status_code != 200:
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            page_candidates = extract_list_candidates(source, soup, resp.url)
            if not page_candidates:
                break
            for title, abs_url, published_at_utc in page_candidates:
                articles_scanned += 1
                add_candidate(
                    candidates,
                    url=abs_url,
                    title=title,
                    published_at_utc=published_at_utc,
                    entry_point="search",
                    search_page=page_num,
                )
    return articles_scanned


def collect_extra_list_candidates(
    source: KstyleMusicSource,
    candidates: dict[str, Candidate],
    *,
    list_urls: list[str],
) -> int:
    articles_scanned = 0
    for list_url in list_urls:
        resp = source._get_with_retry(list_url, timeout=30)
        if resp.status_code != 200:
            continue
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for title, abs_url, published_at_utc in extract_list_candidates(
            source, soup, resp.url
        ):
            articles_scanned += 1
            add_candidate(
                candidates,
                url=abs_url,
                title=title,
                published_at_utc=published_at_utc,
                entry_point="extra_list",
            )
    return articles_scanned


def collect_known_url_candidates(
    source: KstyleMusicSource,
    candidates: dict[str, Candidate],
    *,
    urls: list[str],
) -> int:
    articles_scanned = 0
    for article_url in urls:
        clean_url = str(article_url or "").strip()
        if not clean_url:
            continue
        try:
            resp = source._get_with_retry(clean_url, timeout=30)
        except Exception:
            add_candidate(
                candidates,
                url=clean_url,
                title=clean_url,
                published_at_utc="",
                entry_point="known_sample",
            )
            continue
        if resp.status_code != 200:
            add_candidate(
                candidates,
                url=clean_url,
                title=clean_url,
                published_at_utc="",
                entry_point="known_sample",
            )
            continue
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        title = source._extract_article_title(soup, clean_url)
        articles_scanned += 1
        add_candidate(
            candidates,
            url=clean_url,
            title=title or clean_url,
            published_at_utc=extract_article_published_at(source, soup),
            entry_point="known_sample",
        )
    return articles_scanned


def extract_article_published_at(source: KstyleMusicSource, soup: BeautifulSoup) -> str:
    for selector, attr in [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ("time[datetime]", "datetime"),
    ]:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = str(node.get(attr) or "").strip()
        parsed = source._to_utc_datetime_from_iso(value)
        if parsed:
            return parsed
    text = " ".join(soup.get_text(" ", strip=True).split())
    match = source.DATETIME_RE.search(text)
    return source._to_utc_datetime(match.group(1)) if match else ""


def extract_list_candidates(
    source: KstyleMusicSource, soup: BeautifulSoup, page_url: str
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()
    for a in soup.select('a[href*="article.ksn?articleNo="]'):
        href = (a.get("href") or "").strip()
        title = " ".join(a.get_text(" ", strip=True).split())
        if not href or not title:
            continue
        abs_url = urljoin(page_url, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        container = find_container_with_datetime(source, a)
        context = (
            " ".join(container.get_text(" ", strip=True).split()) if container else ""
        )
        if not source._is_event_candidate(title, context):
            continue
        dt_match = source.DATETIME_RE.search(context)
        published_at_utc = source._to_utc_datetime(dt_match.group(1)) if dt_match else ""
        out.append((title, abs_url, published_at_utc or ""))
    return out


def find_container_with_datetime(source: KstyleMusicSource, tag: Tag) -> Tag | None:
    node: Tag | None = tag
    for _ in range(6):
        if node is None:
            return None
        text = " ".join(node.get_text(" ", strip=True).split())
        if source.DATETIME_RE.search(text):
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return None


def audit_details(
    source: KstyleMusicSource,
    candidates: dict[str, Candidate],
    *,
    existing_urls: set[str],
    existing_occurrence_counts: dict[str, int],
    configured_pages: int,
    configured_sitemap_max_candidates: int,
    max_detail_fetch: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sorted_candidates = sorted(
        candidates.values(),
        key=lambda c: ("known_sample" in c.entry_points, c.published_at_utc or "", c.url),
        reverse=True,
    )
    for idx, candidate in enumerate(sorted_candidates):
        detail_checked = idx < max_detail_fetch or "known_sample" in candidate.entry_points
        section_found = False
        parser_occurrences: list[tuple[str, str, str, str]] = []
        japan_occurrence = False
        if detail_checked:
            detail = source._fetch_article_detail(candidate.url, candidate.title)
            if detail is not None:
                section_lines, _, _ = detail
                section_found = True
                default_year = source._default_year_from_utc(candidate.published_at_utc)
                parser_occurrences = source._extract_occurrences(
                    section_lines,
                    default_year=default_year,
                )
                japan_occurrence = source._is_japan_occurrence(
                    section_lines, parser_occurrences
                )

        existing_count = existing_occurrence_counts.get(candidate.url, 0)
        miss_reasons = classify_miss_reasons(
            candidate,
            existing=existing_count > 0,
            parser_occurrence_count=len(parser_occurrences),
            section_found=section_found,
            detail_checked=detail_checked,
            configured_pages=configured_pages,
            configured_sitemap_max_candidates=configured_sitemap_max_candidates,
        )
        rows.append(
            {
                "url": candidate.url,
                "title": candidate.title,
                "published_at_utc": candidate.published_at_utc,
                "entry_points": sorted(candidate.entry_points),
                "min_search_page": candidate.min_search_page,
                "sitemap_rank": candidate.sitemap_rank,
                "exists_in_db": candidate.url in existing_urls,
                "existing_occurrence_count": existing_count,
                "detail_checked": detail_checked,
                "section_found": section_found,
                "parser_occurrence_count": len(parser_occurrences),
                "japan_occurrence": japan_occurrence,
                "parser_occurrences": [
                    {
                        "event_start_date": event_date,
                        "venue_name": venue_name,
                        "event_info": event_info,
                        "pref_name": pref_name,
                    }
                    for event_date, venue_name, event_info, pref_name in parser_occurrences
                ],
                "miss_reason": miss_reasons,
            }
        )
    return rows


def classify_miss_reasons(
    candidate: Candidate,
    *,
    existing: bool,
    parser_occurrence_count: int,
    section_found: bool,
    detail_checked: bool,
    configured_pages: int,
    configured_sitemap_max_candidates: int,
) -> list[str]:
    if existing:
        return []
    reasons: list[str] = []
    if "search" not in candidate.entry_points:
        reasons.append("entry_gap")
    if (
        candidate.min_search_page is not None
        and candidate.min_search_page > configured_pages
    ) or (
        candidate.sitemap_rank is not None
        and candidate.sitemap_rank > configured_sitemap_max_candidates
    ):
        reasons.append("page_limit_gap")
    if not detail_checked:
        reasons.append("detail_not_checked")
    elif not section_found or parser_occurrence_count == 0:
        reasons.append("parser_gap")
    if not reasons:
        reasons.append("coverage_gap")
    return reasons


def configured_limits(source_record: SignalSourceRecord) -> tuple[int, int]:
    cfg = KstyleMusicSource._load_config(source_record.config_json)
    return (
        max(1, int(cfg.get("pages", 2))),
        max(0, int(cfg.get("sitemap_max_candidates", 40))),
    )


def summarize(
    *,
    candidates: dict[str, Candidate],
    rows: list[dict[str, object]],
    articles_scanned_by_entry: dict[str, int],
    configured_pages: int,
    configured_sitemap_max_candidates: int,
) -> dict[str, object]:
    missed = [row for row in rows if not row["exists_in_db"]]
    missed_occurrences = [
        row
        for row in missed
        if int(row.get("parser_occurrence_count") or 0) > 0
    ]
    candidate_dates = [
        str(row["published_at_utc"])
        for row in rows
        if str(row.get("published_at_utc") or "")
    ]
    reason_counts: dict[str, int] = {}
    for row in missed:
        for reason in row.get("miss_reason") or []:
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    recommended_pages = configured_pages
    for row in missed:
        page = row.get("min_search_page")
        if isinstance(page, int) and page > recommended_pages:
            recommended_pages = page
    recommended_sitemap_max = configured_sitemap_max_candidates
    for row in missed:
        rank = row.get("sitemap_rank")
        if isinstance(rank, int) and rank > recommended_sitemap_max:
            recommended_sitemap_max = rank
    return {
        "source_id": "kstyle_music",
        "configured_frequency_hours": DEFAULT_UPDATE_FREQUENCY_HOURS,
        "configured_pages": configured_pages,
        "configured_sitemap_max_candidates": configured_sitemap_max_candidates,
        "articles_scanned": articles_scanned_by_entry,
        "candidate_articles": len(candidates),
        "matched_existing_articles": sum(1 for row in rows if row["exists_in_db"]),
        "missed_candidate_articles": len(missed),
        "missed_occurrences": sum(
            int(row.get("parser_occurrence_count") or 0) for row in missed_occurrences
        ),
        "miss_reason_counts": dict(sorted(reason_counts.items())),
        "oldest_candidate_in_scan": min(candidate_dates) if candidate_dates else "",
        "newest_candidate_in_scan": max(candidate_dates) if candidate_dates else "",
        "recommended_frequency_hours": DEFAULT_UPDATE_FREQUENCY_HOURS,
        "recommended_pages": recommended_pages,
        "recommended_sitemap_max_candidates": recommended_sitemap_max,
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    rows = report["candidates"]
    lines = [
        "# K-Style Coverage Audit",
        "",
        "## Summary",
        f"- candidate_articles: {summary['candidate_articles']}",
        f"- matched_existing_articles: {summary['matched_existing_articles']}",
        f"- missed_candidate_articles: {summary['missed_candidate_articles']}",
        f"- missed_occurrences: {summary['missed_occurrences']}",
        f"- miss_reason_counts: {json.dumps(summary['miss_reason_counts'], ensure_ascii=False)}",
        f"- recommended_frequency_hours: {summary['recommended_frequency_hours']}",
        f"- recommended_pages: {summary['recommended_pages']}",
        f"- recommended_sitemap_max_candidates: {summary['recommended_sitemap_max_candidates']}",
        "",
        "## Missed Candidates",
        "| title | reason | parser_occurrences | entry_points | url |",
        "|---|---:|---:|---|---|",
    ]
    for row in rows:
        if row["exists_in_db"]:
            continue
        lines.append(
            "| {title} | {reason} | {count} | {entry_points} | {url} |".format(
                title=str(row["title"]).replace("|", "\\|"),
                reason=",".join(row.get("miss_reason") or []),
                count=row.get("parser_occurrence_count", 0),
                entry_points=",".join(row.get("entry_points") or []),
                url=row["url"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    source_record = load_source_record(db_path)
    configured_pages, configured_sitemap_max = configured_limits(source_record)

    session = build_session()
    source = KstyleMusicSource(session)
    candidates: dict[str, Candidate] = {}
    articles_scanned_by_entry: dict[str, int] = {}

    articles_scanned_by_entry["sitemap"] = collect_sitemap_candidates(
        source,
        candidates,
        max_candidates=max(args.sitemap_max_candidates, configured_sitemap_max),
    )
    articles_scanned_by_entry["search"] = collect_search_candidates(
        source,
        candidates,
        source_url=args.source_url or source_record.source_url,
        pages=max(args.pages, configured_pages),
    )
    if args.extra_list_url:
        articles_scanned_by_entry["extra_list"] = collect_extra_list_candidates(
            source,
            candidates,
            list_urls=args.extra_list_url,
        )
    known_urls = list(args.known_url)
    if not args.skip_default_known_samples:
        known_urls.extend(KNOWN_COVERAGE_SAMPLE_URLS)
    if known_urls:
        deduped_known_urls = list(dict.fromkeys(known_urls))
        articles_scanned_by_entry["known_sample"] = collect_known_url_candidates(
            source,
            candidates,
            urls=deduped_known_urls,
        )

    existing_urls, existing_occurrence_counts = load_existing_kstyle(db_path)
    rows = audit_details(
        source,
        candidates,
        existing_urls=existing_urls,
        existing_occurrence_counts=existing_occurrence_counts,
        configured_pages=configured_pages,
        configured_sitemap_max_candidates=configured_sitemap_max,
        max_detail_fetch=args.max_detail_fetch,
    )
    report = {
        "summary": summarize(
            candidates=candidates,
            rows=rows,
            articles_scanned_by_entry=articles_scanned_by_entry,
            configured_pages=configured_pages,
            configured_sitemap_max_candidates=configured_sitemap_max,
        ),
        "candidates": rows,
    }
    json_text = json.dumps(report, ensure_ascii=False, indent=args.indent)
    write_text(args.output_json, json_text + "\n")
    write_text(args.output_md, render_markdown(report))
    if not args.output_json:
        sys.stdout.write(json_text)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()

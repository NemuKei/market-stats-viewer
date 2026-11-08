"""Prepare primary-league facts for the existing review inbox; never publish.

Known public calendars only. The caller selects registered venue IDs and a date
window; unknown venues/dates/times are not guessed. No source, ID, policy, DB or
workflow writes. A draft is not a source/public-link approval.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from .apply_venue_discovery_inbox import MAX_CANDIDATES, _check_schema, _dedup_key
from .events.registry import load_registry
from .signals.entity_aliases import load_artist_lookup_maps, load_venue_lookup_maps, normalize_with_lookup

SOURCES = {
    "jleague-ftokyo": ("jleague", "https://www.jleague.jp/club/ftokyo/day/"),
    "jleague-tokyov": ("jleague", "https://www.jleague.jp/club/tokyov/day/"),
    "bleague-ariake": ("bleague", "https://www.bleague.jp/arena_detail/?ArenaCD=646"),
    "bleague-asue": ("bleague", "https://www.bleague.jp/arena_detail/?ArenaCD=475"),
    "leagueone": ("leagueone", "https://league-one.jp/schedule/"),
    "svleague-men": ("svleague", "https://www.svleague.jp/match/sv/men/"),
    "svleague-women": ("svleague", "https://www.svleague.jp/match/sv/women/"),
}
ARENAS = {
    "bleague-ariake": ("有明アリーナ(メイン)", "有明アリーナ"),
    "bleague-asue": ("Asueアリーナ大阪(大阪市中央体育館)", "Asueアリーナ大阪"),
}


def text(node):
    return (
        unicodedata.normalize("NFKC", " ".join(node.get_text(" ", strip=True).split()))
        if node
        else ""
    )


def clock(value):
    value = unicodedata.normalize("NFKC", value).strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s*KO)?", value)
    if not match:
        if not value or value in {"未定", "調整中", "TIP OFF調整中"}:
            return None
        raise ValueError(
            f"unrecognized or unlabelled league start time: {value[:80]!r}"
        )
    hour, minute = map(int, match.groups())
    if hour > 23 or minute > 59:
        raise ValueError("invalid league start time")
    return f"{hour:02d}:{minute:02d}"


def official_link(base, href, kind):
    target = urljoin(base, href or "")
    parsed = urlparse(target)
    paths = {
        "jleague": r"/match/[^/]+/20\d{2}/\d+/",
        "bleague": r"/game_detail/",
        "leagueone": r"/match/\d+",
        "svleague": r"/match/detail/\d+/",
    }
    if (
        parsed.scheme != "https"
        or parsed.netloc != urlparse(base).netloc
        or not re.fullmatch(paths[kind], parsed.path)
        or parsed.fragment
    ):
        raise ValueError("detail link is not a known primary-league match route")
    if kind == "bleague" and not re.fullmatch(r"ScheduleKey=\d+", parsed.query):
        raise ValueError("invalid basketball match key")
    return target


def parse_page(
    html, source, source_url, *, start, through, venue_names, venue_maps, verified_at
):
    """Parse one observed calendar page, preserving acquisition vs detail URLs."""
    kind, base = SOURCES[source]
    parsed_url, known = urlparse(source_url), urlparse(base)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != known.netloc
        or parsed_url.path != known.path
    ):
        raise ValueError("unexpected league acquisition URL")
    if kind != "svleague" and parsed_url.query != known.query:
        raise ValueError("unexpected league acquisition parameters")
    stamp = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    if stamp.utcoffset() != timedelta(0) or start > through or not venue_names:
        raise ValueError("UTC observation, selected venues and valid window required")
    soup = BeautifulSoup(html, "html.parser")
    rows, skipped = [], Counter()

    def status_requires_review(node):
        if any(word in text(node) for word in ("中止", "延期", "中断")):
            skipped["status_requires_review"] += 1
            return True
        return False

    def emit(day, raw_venue, home, away, start_time, detail, label, *, observed_venue=None):
        # Only exact dictionary/alias lookup. Do not strip a facility suffix:
        # a sub-arena must never inherit the main arena's identity.
        raw_venue = re.sub(
            r"\s*\((?:北海道|東京都|京都府|大阪府|[^()]+県)\)\s*$",
            "",
            unicodedata.normalize("NFKC", raw_venue),
        ).strip()
        venue, matched = normalize_with_lookup(raw_venue, *venue_maps)
        if not matched or venue not in venue_names:
            skipped["unregistered_or_unselected_facility"] += 1
            return
        if not start <= day <= through:
            skipped["outside_window"] += 1
            return
        if not home or not away or home == away:
            raise ValueError("unverified league participants")
        start_time = clock(start_time)
        subject = f"{home} vs {away}"
        title = f"{label} {subject}"
        row = dict(
            event_start_date=day.isoformat(),
            event_end_date=day.isoformat(),
            venue_name=venue,
            raw_venue_name=observed_venue or raw_venue,
            artist_name=subject,
            title=title,
            source_class="promoter_official",
            evidence_url=source_url,
            url=official_link(base, detail, kind),
            verified_at_utc=verified_at,
            content_extractor="requests_bs4",
            confidence="high",
            evidence_snippet=f"リーグ公式日程本文: {day.isoformat()} {venue} {title}"
            + (
                f" 開始{start_time}。"
                if start_time
                else "。開始時刻は未定または本文に未掲載。"
            ),
        )
        if start_time:
            row["event_start_time"] = start_time
        if len(row["evidence_snippet"]) > 400:
            raise ValueError("league evidence exceeds existing inbox limit")
        rows.append(row)

    if kind == "jleague":
        cards = soup.select(".m-schedule[id]")
        if not cards:
            raise ValueError("J.League calendar structure not found")
        for card in cards:
            if status_requires_review(card):
                continue
            match = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})\d{2}", card["id"])
            if not match:
                raise ValueError("J.League match lacks verified calendar date")
            day = date(*map(int, match.groups()))
            heading = card.find_previous("h2")
            date_label = re.match(r"(20\d{2})/(\d{1,2})/(\d{1,2})", text(heading))
            if not date_label or date(*map(int, date_label.groups())) != day:
                raise ValueError("J.League date label and match key disagree")
            stadiums = {
                text(n)
                for n in card.select('.m-schedule__info-stadium[data-media="pc"]')
            }
            if len(stadiums) != 1:
                raise ValueError("missing or conflicting match venue labels")
            link = card.select_one("a.m-schedule__link[href]")
            if link is None:
                raise ValueError("J.League match detail link missing")
            home = text(
                card.select_one(
                    '.m-schedule__team-home .m-schedule__team-name[data-media="pc"]'
                )
            )
            away = text(
                card.select_one(
                    '.m-schedule__team-away .m-schedule__team-name[data-media="pc"]'
                )
            )
            time_node = card.select_one(
                ".m-schedule__status-time, .m-schedule__time-text"
            )
            emit(
                day,
                stadiums.pop(),
                home,
                away,
                text(time_node),
                link["href"],
                "J.LEAGUE",
            )
    elif kind == "bleague":
        expected_label, arena = ARENAS[source]
        if text(soup.select_one("h1")).split(" | ")[0] != expected_label:
            raise ValueError("basketball primary arena identity changed")
        cards = soup.select(".matchSchedule")
        if not cards:
            raise ValueError("basketball calendar structure not found")
        for card in cards:
            if status_requires_review(card):
                continue
            day = date.fromisoformat(
                text(card.select_one(".matchSchedule-date")).replace(".", "-")
            )
            link = card.select_one("a.matchSchedule-main[href]")
            if link is None:
                raise ValueError("basketball match detail link missing")
            time_node = card.select_one(".matchSchedule-info-venue")
            parts = (
                [p.strip() for p in time_node.get_text("\n", strip=True).splitlines()]
                if time_node
                else []
            )
            start_time = parts[-1] if len(parts) > 1 else ""
            emit(
                day,
                arena,
                text(card.select_one(".matchSchedule-home .matchSchedule-name")),
                text(card.select_one(".matchSchedule-away .matchSchedule-name")),
                start_time,
                link["href"],
                "B.LEAGUE",
                observed_venue=expected_label,
            )
    elif kind == "leagueone":
        cards = soup.select(".c-schedule")
        if not cards:
            raise ValueError("League One calendar structure not found")
        for card in cards:
            if status_requires_review(card):
                continue
            title = text(card.select_one(".ttl"))
            key = re.search(r"\((20\d{2})D\d+\)", title)
            raw_day = re.fullmatch(
                r"(\d{2})\.(\d{2})\s*[月火水木金土日]?",
                text(card.select_one(".datetime .date")),
            )
            if not key or not raw_day:
                skipped["date_not_confirmed"] += 1
                continue
            day = date(int(key[1]), *map(int, raw_day.groups()))
            link = card.select_one("a.btn-match-detail[href]")
            if link is None:
                raise ValueError("League One detail link missing")
            emit(
                day,
                text(card.select_one(".place a")),
                text(card.select_one(".game .home .name.only-pc")),
                text(card.select_one(".game .away .name.only-pc")),
                text(card.select_one(".datetime .time")),
                link["href"],
                title,
            )
    else:
        query = parse_qs(parsed_url.query)
        if set(query) != {"s", "y", "m", "d"} or any(
            len(v) != 1 for v in query.values()
        ):
            raise ValueError("SV League requires one explicit source year/month/day")
        season, year, month, dom = (int(query[k][0]) for k in ("s", "y", "m", "d"))
        day = date(year, month, dom)
        check_sv_month(soup, season, year, month)
        if soup.select_one(f".div_day.active#div_day_{dom}") is None:
            raise ValueError("SV League ignored the requested day")
        match_list = soup.select_one("dl#match-list")
        if match_list is None:
            raise ValueError("SV League match list missing")
        for heading in match_list.find_all("dt", recursive=False):
            card = heading.find_next_sibling()
            if card is None or card.name != "dd":
                raise ValueError("SV League fixture structure changed")
            if status_requires_review(card):
                continue
            teams = card.select("ul > li > b")
            if len(teams) != 2:
                raise ValueError("SV League match participants missing")
            link = card.select_one('a[href^="/match/detail/"]')
            if link is None:
                raise ValueError("SV League detail link missing")
            raw_time = text(card.select_one(".time"))
            if raw_time.startswith("GAME START "):
                raw_time = raw_time[len("GAME START ") :]
            emit(
                day,
                text(heading.select_one("p a")),
                text(teams[0]),
                text(teams[1]),
                raw_time,
                link["href"],
                "SV.LEAGUE " + text(heading.select_one("b")),
            )
    keys = [
        (r["event_start_date"], r.get("event_start_time"), r["venue_name"], r["title"])
        for r in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate league candidates require review")
    # The existing inbox deliberately treats a changed clock as review, not a
    # new show. Do not emit two distinct match URLs it would silently dedup.
    artist_maps = load_artist_lookup_maps()
    inbox_keys = [_dedup_key(row, venue_maps, artist_maps) for row in rows]
    if len(inbox_keys) != len(set(inbox_keys)):
        raise ValueError("same-day same-card sessions exceed existing inbox identity; explicit session review required")
    return rows, dict(skipped)


def check_sv_month(soup, season, year, month):
    selected_seasons = {
        o.get("value") for o in soup.select("#select-year option[selected]")
    }
    selected_months = {
        o.get("value")
        for o in soup.select("#select-ym option[selected]")
        if o.get("value")
    }
    if selected_seasons != {str(season)} or selected_months != {f"{year}:{month}"}:
        raise ValueError("SV League ignored the requested season or month")


def collect(source, start, through, venue_names, *, session=None):
    if start > through or not venue_names:
        raise ValueError("valid date window and selected registered venues required")
    session = session or requests.Session()
    kind, base = SOURCES[source]
    pages, rows, skipped = [], [], Counter()

    def fetch(url):
        response = session.get(
            url,
            timeout=(10, 30),
            headers={
                "User-Agent": "market-stats-viewer-events-bot/1.0 (+https://deltahelmlab.com/)"
            },
        )
        response.raise_for_status()
        if response.url != url:
            raise ValueError("primary calendar unexpectedly redirected")
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    if kind == "svleague":
        if (start.year, start.month) != (through.year, through.month):
            raise ValueError("choose one calendar month per SV League review draft")
        # Season follows the source's explicit selector, not a guessed rollover.
        entry = BeautifulSoup(fetch(base), "html.parser")
        selected = entry.select("#select-year option[selected]")
        if len(selected) != 1 or not str(selected[0].get("value", "")).isdecimal():
            raise ValueError("SV League season selector missing")
        season = int(selected[0]["value"])
        prefix = base + "?" + urlencode(dict(s=season, y=start.year, m=start.month))
        month_html = fetch(prefix)
        month_soup = BeautifulSoup(month_html, "html.parser")
        check_sv_month(month_soup, season, start.year, start.month)
        day_numbers = sorted(
            {
                int(n["id"].removeprefix("div_day_"))
                for n in month_soup.select('.div_day[id^="div_day_"]')
            }
        )
        if not day_numbers or len(day_numbers) > 31:
            raise ValueError("SV League calendar day navigation missing")
        for dom in day_numbers:
            day = date(start.year, start.month, dom)
            if start <= day <= through:
                url = prefix + "&d=" + str(dom)
                pages.append((url, fetch(url)))
    else:
        pages.append((base, fetch(base)))
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    venue_maps = load_venue_lookup_maps()
    for url, html in pages:
        found, notes = parse_page(
            html,
            source,
            url,
            start=start,
            through=through,
            venue_names=venue_names,
            venue_maps=venue_maps,
            verified_at=stamp,
        )
        rows.extend(found)
        skipped.update(notes)
    if len(rows) > MAX_CANDIDATES:
        raise ValueError(
            "league draft exceeds inbox limit; reduce window/venues (no truncation)"
        )
    if len({row["url"] for row in rows}) != len(rows):
        raise ValueError("one league match detail appeared more than once; review date switching")
    payload = dict(schema_version=1, run_at_utc=stamp, candidates=rows)
    _check_schema(payload)
    return payload, dict(skipped), len(pages)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    parser.add_argument("--venue-id", action="append", required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New private review draft only"
    )
    args = parser.parse_args(argv)
    try:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        if (
            args.output.exists()
            or args.output.name == "venue_discovery_inbox.json"
            or data_dir in args.output.resolve().parents
        ):
            raise ValueError(
                "existing files and the live inbox/data directory are prohibited"
            )
        venues = {v.venue_id: v.venue_name for v in load_registry()}
        if set(args.venue_id) - set(venues):
            raise ValueError("unknown registered venue ID")
        payload, skipped, page_count = collect(
            args.source, args.start, args.through, {venues[k] for k in args.venue_id}
        )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                dict(
                    status="DRAFT_requires_fact_link_ID_review",
                    candidate_count=len(payload["candidates"]),
                    observed_page_count=page_count,
                    skipped=skipped,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"League programme preparation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

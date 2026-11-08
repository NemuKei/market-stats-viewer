"""Prepare official programme facts for the existing Venue Web Discovery inbox.

This is a review aid, not a scheduled collector or publication approval. It
fetches only the known primary calendars, keeps acquisition/detail URLs
separate and emits every dated game/show separately. No DB/config/ID writes.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from .apply_venue_discovery_inbox import MAX_CANDIDATES, _check_schema

SOURCES = {
    "osaka-marvelous": (
        "https://www.osaka-marvelous.com/game/score/2026/index.html",
        "Asueアリーナ大阪",
        "promoter_official",
    ),
    "lala-arena": (
        "https://lalaarenatokyo-bay.com/event/",
        "ららアリーナ 東京ベイ",
        "venue_official",
    ),
    "bigbang-kyocera": (
        "https://ygex.jp/bigbang/20th-anniv/live/tour.php?id=1003004&fdate=2026-11-27&ldate=2026-11-29",
        "京セラドーム大阪",
        "artist_official",
    ),
}


def text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def explicit_times(value: str) -> list[str]:
    # Only labelled start times. Door/priority-entry times never count.
    result = []
    for match in re.finditer(
        r"(?:試合開始|開演)\s*[：:]?\s*(\d{1,2}[：:]\d{2}(?:\s*[/／]\s*\d{1,2}[：:]\d{2})*)",
        value,
    ):
        for hour, minute in re.findall(r"(\d{1,2})[：:](\d{2})", match.group(1)):
            if int(hour) > 23 or int(minute) > 59:
                raise ValueError("invalid explicitly labelled programme time")
            result.append(f"{int(hour):02d}:{int(minute):02d}")
    return list(dict.fromkeys(result))


def candidate(source, day, title, subject, start_time, detail_url, verified_at):
    acquisition, venue, source_class = SOURCES[source]
    if urlparse(detail_url).hostname != urlparse(acquisition).hostname:
        raise ValueError("calendar detail URL leaves the primary source domain")
    row = dict(
        event_start_date=day,
        event_end_date=day,
        venue_name=venue,
        artist_name=subject or title,
        title=title,
        source_class=source_class,
        evidence_url=acquisition,
        url=detail_url,
        verified_at_utc=verified_at,
        content_extractor="requests_bs4",
        confidence="high",
        evidence_snippet=f"公式日程本文: {day} {venue} {title}"
        + (f" 開始 {start_time}。" if start_time else "。開始時刻は未確認。"),
    )
    if start_time:
        row["event_start_time"] = start_time
    if source == "osaka-marvelous":
        # These verified home-game cards are volleyball. A club name in the
        # legacy artist field must not turn the match into a concert.
        row["event_category"] = "その他"
    if len(row["evidence_snippet"]) > 400:
        raise ValueError("programme facts exceed the existing inbox evidence limit")
    return row


def parse_programmes(
    html: str, source: str, *, start: date, through: date, verified_at: str
) -> tuple[list[dict], dict]:
    if source not in SOURCES or start > through:
        raise ValueError("unknown source or invalid programme window")
    stamp = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("observation timestamp must be UTC")
    soup = BeautifulSoup(html, "html.parser")
    rows, skipped = [], Counter()
    acquisition, expected_venue, _ = SOURCES[source]
    if source == "osaka-marvelous":
        cards = soup.select("li.gameData")
        if not cards:
            raise ValueError("official team programme structure not found")
        for card in cards:
            if "homegame" not in card.get("class", []):
                skipped["not_home_programme"] += 1
                continue
            venue = re.sub(
                r"\s*（[^）]+）\s*$", "", text(card.select_one(".txtKaijyo dd"))
            )
            if venue != expected_venue:
                skipped["other_facility"] += 1
                continue
            time_node = card.select_one(".txtGameStart time[datetime]")
            if time_node is None:
                raise ValueError(
                    "home programme has no source datetime; manual review required"
                )
            dt = datetime.strptime(time_node["datetime"], "%Y-%m-%d %H:%M")
            if not start <= dt.date() <= through:
                skipped["outside_window"] += 1
                continue
            teams = [text(n) for n in card.select(".vsBox figcaption")]
            if len(teams) != 2 or teams[0] != "大阪マーヴェラス":
                raise ValueError("unexpected home programme participants")
            if any(word in text(card) for word in ("中止", "延期")):
                skipped["status_requires_review"] += 1
                continue
            rows.append(
                candidate(
                    source,
                    dt.date().isoformat(),
                    " vs ".join(teams),
                    teams[0],
                    dt.strftime("%H:%M"),
                    acquisition,
                    verified_at,
                )
            )
    elif source == "bigbang-kyocera":
        cards = soup.select("ul.tourData__lists")
        if not cards or "BIGBANG" not in text(soup.title).upper():
            raise ValueError("official artist tour structure not found")
        for card in cards:
            if text(card.select_one(".js-tourDataPlace")) != expected_venue:
                skipped["other_facility"] += 1
                continue
            match = re.fullmatch(r"(\d{4})\.(\d{2})\.(\d{2})\[[A-Za-z]+\]", text(card.select_one(".tourData__date")))
            if match is None:
                raise ValueError("artist programme has no verified source date")
            day = date(*map(int, match.groups()))
            if not start <= day <= through:
                skipped["outside_window"] += 1
                continue
            if any(word in text(card) for word in ("中止", "延期")):
                skipped["status_requires_review"] += 1
                continue
            starts = explicit_times(text(card.select_one(".tourData__list--time")))
            if len(starts) != 1:
                raise ValueError("artist programme needs one labelled start per dated card")
            row = candidate(source, day.isoformat(), "BIGBANG", "BIGBANG", starts[0], acquisition, verified_at)
            row["event_category"] = "コンサート"
            rows.append(row)
    else:
        months = {}
        for tab in soup.select("[data-target]"):
            year, month = (
                text(tab.select_one(".c-tab__year")),
                text(tab.select_one(".c-tab__month")),
            )
            if year.isdecimal() and month.isdecimal():
                value = (int(year), int(month))
                target = tab["data-target"]
                if target in months and months[target] != value:
                    raise ValueError("conflicting calendar month labels")
                months[target] = value
        if not months or not soup.select(".p-eventbox"):
            raise ValueError("official arena programme structure not found")
        for card in soup.select(".p-eventbox"):
            group = card.find_parent(class_="p-cards")
            if group is None or group.get("id") not in months:
                raise ValueError("programme has no verified calendar year/month")
            year, month = months[group["id"]]
            match = re.fullmatch(
                r"(\d{1,2})\.(\d{1,2})\s*\S*",
                text(card.select_one(".p-eventbox__date")),
            )
            if not match or int(match.group(1)) != month:
                raise ValueError("programme date disagrees with calendar month")
            day = date(year, month, int(match.group(2)))
            if not start <= day <= through:
                skipped["outside_window"] += 1
                continue
            title = text(card.select_one(".p-eventbox__title"))
            if not title or title.casefold() in {"reserved", "tba", "tbd"}:
                skipped["unannounced_programme"] += 1
                continue
            if any(word in text(card) for word in ("中止", "延期")):
                skipped["status_requires_review"] += 1
                continue
            link = card.select_one("a.p-eventbox__link[href]")
            if link is None:
                raise ValueError("programme has no primary detail link")
            detail_url = urljoin(acquisition, link["href"])
            for start_time in explicit_times(text(card)) or [None]:
                rows.append(
                    candidate(
                        source,
                        day.isoformat(),
                        title,
                        text(card.select_one(".p-eventbox__artist")),
                        start_time,
                        detail_url,
                        verified_at,
                    )
                )
    keys = [
        (r["event_start_date"], r.get("event_start_time"), r["venue_name"], r["title"])
        for r in rows
    ]
    if len(set(keys)) != len(keys):
        raise ValueError(
            "duplicate calendar programmes require review before inbox import"
        )
    if len(rows) > MAX_CANDIDATES:
        raise ValueError(
            f"{len(rows)} candidates exceed inbox limit; choose a smaller date window (no truncation)"
        )
    return rows, dict(skipped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private draft file, never the live inbox.",
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
                "prepare a new review draft; existing or live inbox output is prohibited"
            )
        acquisition = SOURCES[args.source][0]
        response = requests.get(
            acquisition,
            timeout=30,
            headers={
                "User-Agent": "market-stats-viewer-events-bot/1.0 (+https://deltahelmlab.com/)"
            },
        )
        response.raise_for_status()
        if urlparse(response.url).hostname != urlparse(acquisition).hostname:
            raise ValueError("primary calendar redirected to another domain")
        response.encoding = response.apparent_encoding or "utf-8"
        verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rows, skipped = parse_programmes(
            response.text,
            args.source,
            start=args.start,
            through=args.through,
            verified_at=verified_at,
        )
        payload = dict(schema_version=1, run_at_utc=verified_at, candidates=rows)
        _check_schema(payload)
        # Exclusive creation: preparation must not replace any existing work.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(
            json.dumps(
                dict(
                    candidate_count=len(rows),
                    skipped=skipped,
                    status="draft_only_requires_fact_link_and_fixed_id_review",
                ),
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"Programme preparation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify supported discovery leads against NPB and Zepp official schedule bodies.

Outputs review decisions and an attempt receipt. It never writes source DBs.
Unsupported or unmatched leads remain for Codex's official-page review.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from .build_lp_events import write_lp_events, today_jst
from .events.category import classify_event_category
from .events.sources.html import _ZeppSchedule
from .ticketjam_review_state import fingerprint
from .signals.entity_aliases import load_artist_lookup_maps, normalize_with_lookup

NPB_VENUES = {
    "東京ドーム": ("東京ドーム", "東京都"),
    "横浜スタジアム": ("横浜", "神奈川県"),
    "阪神甲子園球場": ("甲子園", "兵庫県"),
    "ZOZOマリンスタジアム": ("ZOZOマリン", "千葉県"),
    "みずほPayPayドーム福岡": ("みずほPayPay", "福岡県"),
    "エスコンフィールドHOKKAIDO": ("エスコンF", "北海道"),
    "ベルーナドーム": ("ベルーナドーム", "埼玉県"),
    "バンテリンドームナゴヤ": ("バンテリンドーム", "愛知県"),
    "京セラドーム大阪": ("京セラD大阪", "大阪府"),
}
NPB_TEAMS = {
    "巨人",
    "中日",
    "DeNA",
    "ヤクルト",
    "阪神",
    "広島",
    "ロッテ",
    "楽天",
    "西武",
    "日本ハム",
    "オリックス",
    "ソフトバンク",
}
NPB_TEAM_ARTISTS = {
    "巨人": "読売ジャイアンツ",
    "中日": "中日ドラゴンズ",
    "DeNA": "横浜DeNAベイスターズ",
    "ヤクルト": "東京ヤクルトスワローズ",
    "阪神": "阪神タイガース",
    "広島": "広島東洋カープ",
    "ロッテ": "千葉ロッテマリーンズ",
    "楽天": "東北楽天ゴールデンイーグルス",
    "西武": "埼玉西武ライオンズ",
    "日本ハム": "北海道日本ハムファイターズ",
    "オリックス": "オリックス・バファローズ",
    "ソフトバンク": "福岡ソフトバンクホークス",
}
ZEPP_VENUES = {
    "Zepp札幌": ("sapporo", "北海道"),
    "Zepp Haneda(Tokyo)": ("haneda", "東京都"),
    "Zepp DiverCity(Tokyo)": ("divercity", "東京都"),
    "Zepp Namba(Osaka)": ("namba", "大阪府"),
    "Zepp Osaka Bayside": ("osakabayside", "大阪府"),
    "Zepp Nagoya": ("nagoya", "愛知県"),
    "Zepp Fukuoka": ("fukuoka", "福岡県"),
    "KT Zepp Yokohama": ("yokohama", "神奈川県"),
    "Zepp Shinjuku(TOKYO)": ("shinjuku", "東京都"),
}


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


@lru_cache(maxsize=1)
def artist_maps():
    return load_artist_lookup_maps()


def artist_is_supported(artist: str, headings: list[str]) -> bool:
    keep, compact = artist_maps()
    canonical, _ = normalize_with_lookup(
        artist, keep, compact, allow_parenthetical_base=True
    )
    variants = {normalized(artist), normalized(canonical)}
    base = re.sub(r"\([^()]*\)$", "", unicodedata.normalize("NFKC", artist)).strip()
    variants.add(normalized(base))
    for heading in headings:
        resolved, _ = normalize_with_lookup(
            heading, keep, compact, allow_parenthetical_base=True
        )
        forms = {normalized(heading), normalized(resolved)}
        for variant in variants - {""}:
            if variant in forms or (
                len(variant) >= 4 and any(variant in form for form in forms)
            ):
                return True
    return False


def source_for(candidate: dict) -> tuple[str, str] | None:
    event_date = date.fromisoformat(candidate["event_date"])
    venue = candidate["venue_name"]
    parts = re.split(r"\s+vs\s+", candidate.get("title", ""), flags=re.I)
    if (
        venue in NPB_VENUES
        and len(parts) == 2
        and all(part in NPB_TEAMS for part in parts)
    ):
        return (
            "npb",
            f"https://npb.jp/games/{event_date.year}/schedule_{event_date.month:02d}_detail.html",
        )
    if venue in ZEPP_VENUES:
        slug = ZEPP_VENUES[venue][0]
        return (
            "zepp",
            f"https://www.zepp.co.jp/hall/{slug}/schedule/?_y={event_date.year}&_m={event_date.month}",
        )
    return None


def verify_npb(candidate: dict, html, url: str) -> dict | None:
    source = source_for(candidate)
    if not source or source[0] != "npb" or url != source[1]:
        return None
    if not candidate.get("event_start_time"):
        return None
    event_date = date.fromisoformat(candidate["event_date"])
    soup = BeautifulSoup(html, "html.parser")
    text = unicodedata.normalize("NFKC", soup.get_text(" ", strip=True))
    year_headings = [
        h.get_text(" ", strip=True)
        for h in soup.find_all(["h1", "h2", "h3", "h4"])
        if re.match(r"^\d{4}年", h.get_text(strip=True))
    ]
    if not year_headings or not year_headings[0].startswith(f"{event_date.year}年"):
        return None
    dates = list(re.finditer(r"(?<!\d)(\d{1,2})/(\d{1,2})\([^)]*\)", text))
    home, away = re.split(r"\s+vs\s+", candidate["title"], flags=re.I)
    artist_base = re.sub(
        r"\([^()]*\)$",
        "",
        unicodedata.normalize("NFKC", candidate.get("artist_name") or ""),
    ).strip()
    if normalized(artist_base) not in {
        normalized(home),
        normalized(NPB_TEAM_ARTISTS[home]),
    }:
        return None
    venue, pref = NPB_VENUES[candidate["venue_name"]]
    wanted = normalized(f"{home}-{away}{venue}{candidate['event_start_time']}")
    for i, match in enumerate(dates):
        if (int(match[1]), int(match[2])) != (event_date.month, event_date.day):
            continue
        section = text[
            match.end() : dates[i + 1].start() if i + 1 < len(dates) else len(text)
        ]
        if wanted in normalized(section):
            return {
                "title": candidate["title"],
                "url": url,
                "evidence_url": url,
                "event_status": "scheduled",
                "pref_name": pref,
                "event_category": "野球",
                "source_class": "promoter_official",
            }
    return None


def verify_zepp(candidate: dict, html, url: str) -> dict | None:
    venue = ZEPP_VENUES.get(candidate["venue_name"])
    if (
        not venue
        or urlparse(url).hostname != "www.zepp.co.jp"
        or f"/hall/{venue[0]}/schedule/" not in urlparse(url).path
    ):
        return None
    soup = BeautifulSoup(html, "html.parser")
    candidate_title = normalized(candidate.get("title") or "")
    if len(candidate_title) < 8:
        return None
    matches = []
    for anchor in soup.find_all("a", href=True):
        if "rid=" not in anchor["href"]:
            continue
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if _ZeppSchedule._extract_zepp_date(text) != candidate["event_date"]:
            continue
        headings = [
            tag.get_text(" ", strip=True) for tag in anchor.find_all(["h2", "h3", "h4"])
        ]
        if not artist_is_supported(candidate.get("artist_name") or "", headings):
            continue
        starts = re.findall(r"\[START\]\s*(\d{1,2}:\d{2})", text)
        starts = {
            f"{int(value.split(':')[0]):02d}:{value.split(':')[1]}" for value in starts
        }
        if candidate.get(
            "event_start_time"
        ) not in starts or candidate_title not in normalized(text):
            continue
        title = anchor.find("h4") or anchor.find("h3")
        if title is None:
            continue
        event_status = (
            "cancelled"
            if "公演中止" in text
            else "postponed"
            if "公演延期" in text
            else "scheduled"
        )
        detail_url = urljoin(url, anchor["href"])
        if urlparse(detail_url).hostname != "www.zepp.co.jp":
            continue
        official_title = " ".join(title.get_text(" ", strip=True).split())
        matches.append(
            {
                "title": official_title,
                "url": detail_url,
                "evidence_url": url,
                "event_status": event_status,
                "pref_name": venue[1],
                "source_class": "venue_official",
                "event_category": classify_event_category(
                    official_title, candidate.get("artist_name") or "", ""
                ),
            }
        )
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=120)
    args = parser.parse_args()
    if args.max_candidates < 1:
        parser.error("max-candidates must be positive")
    if len({p.resolve() for p in (args.queue, args.decisions, args.receipt)}) != 3:
        parser.error("input and output paths must be distinct")
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    selected = [
        c
        for c in queue["candidates"]
        if c.get("review_due", True)
        and c["status"] not in {"expired", "ancillary_ticket"}
        and source_for(c)
    ]
    selected.sort(key=lambda c: (c["event_date"], c["event_key"]))
    selected = selected[: args.max_candidates]
    groups = defaultdict(list)
    for candidate in selected:
        groups[source_for(candidate)].append(candidate)
    decisions, attempts = [], []
    checked = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    today = today_jst()
    if date.fromisoformat(queue["as_of_date"]) != today:
        parser.error(
            "queue as_of_date is stale; regenerate it for the current Japan date"
        )
    session = requests.Session()
    for (kind, url), candidates in groups.items():
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            if urlparse(response.url).hostname not in {"npb.jp", "www.zepp.co.jp"}:
                raise ValueError("unexpected redirect host")
        except (requests.RequestException, ValueError) as exc:
            attempts.append(
                {
                    "url": url,
                    "result": "fetch_failed",
                    "candidate_keys": [c["event_key"] for c in candidates],
                    "error": str(exc),
                }
            )
            continue
        body_hash = hashlib.sha256(response.content).hexdigest()
        verified = []
        for candidate in candidates:
            event = (verify_npb if kind == "npb" else verify_zepp)(
                candidate, response.content, url
            )
            if event is None:
                continue
            interval = (
                1
                if (date.fromisoformat(candidate["event_date"]) - today).days <= 7
                else 3
            )
            event.update(
                event_id="ticketjam-official-" + candidate["event_key"],
                enabled=True,
                artist_name=candidate["artist_name"],
                venue_name=candidate["venue_name"],
                event_start_date=candidate["event_date"],
                event_end_date=candidate["event_date"],
                event_start_time=candidate["event_start_time"],
                content_extractor="requests_bs4",
                confidence="high",
                score=95,
                evidence_snippet=f"公式日程本文で照合: {candidate['event_date']} {candidate['venue_name']} {event['title']} 開始{candidate['event_start_time']}。",
            )
            decisions.append(
                {
                    "event_key": candidate["event_key"],
                    "candidate_fingerprint": fingerprint(candidate),
                    "status": "confirmed",
                    "reason": "公式日程本文の同じ日付区間・会場・公演・START時刻を照合。開場時刻は採用しない。",
                    "checked_at_utc": checked,
                    "next_check_date": (today + timedelta(days=interval)).isoformat(),
                    "verification_method": f"{kind}_official_schedule_exact_match",
                    "source_body_sha256": body_hash,
                    "official_event": event,
                    "evidence_url": event["evidence_url"],
                }
            )
            verified.append(candidate["event_key"])
        attempts.append(
            {
                "url": url,
                "result": "checked",
                "source_body_sha256": body_hash,
                "confirmed_keys": verified,
                "unmatched_keys": [
                    c["event_key"] for c in candidates if c["event_key"] not in verified
                ],
            }
        )
    write_lp_events(decisions, args.decisions)
    write_lp_events(
        {
            "schema_version": 1,
            "checked_at_utc": checked,
            "selected_count": len(selected),
            "confirmed_count": len(decisions),
            "attempts": attempts,
        },
        args.receipt,
    )
    print(
        f"Official schedule checks: {len(decisions)} confirmed / {len(selected)} selected / {len(groups)} pages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

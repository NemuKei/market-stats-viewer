"""Build inferred artist map for venue-official events from title matching.

Usage:
    uv run python -m scripts.build_events_artist_inferred
    uv run python -m scripts.build_events_artist_inferred --limit 500 --verbose
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

from .signals.artist_registry import (
    ArtistEntry,
    build_artist_index,
    choose_primary_match,
    load_registry,
    match_artists_in_title,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVENTS_DB_PATH = DATA_DIR / "events.sqlite"
JP_SEED_PATH = DATA_DIR / "artist_registry.jp.seed.csv"
OUTPUT_PATH = DATA_DIR / "events_artist_inferred.csv"

logger = logging.getLogger(__name__)

AMBIGUOUS_SINGLE_TOKENS = {
    "京",
    "阪",
    "東",
    "西",
    "南",
    "北",
    "中",
}

MUSIC_HINT_KEYWORDS = [
    "ライブ",
    "コンサート",
    "公演",
    "ツアー",
    "フェス",
    "ファンミ",
    "fan meeting",
    "world tour",
    "tour",
    "concert",
    "live",
    "showcase",
    "dome",
    "arena",
    "hall",
    "zepp",
    "oneman",
    "one man",
]

NON_MUSIC_EXCLUDE_KEYWORDS = [
    "vs",
    "ｖｓ",
    "対戦",
    "リーグ",
    "野球",
    "baseball",
    "wbc",
    "ラグビー",
    "サッカー",
    "バスケット",
    "中日",
    "阪神",
    "巨人",
    "ヤクルト",
    "広島",
    "ドラゴンズ",
    "タイガース",
    "ベイスターズ",
]


def _parse_aliases_json(raw: object) -> tuple[str, ...]:
    text = str(raw or "").strip()
    if not text:
        return tuple()
    try:
        parsed = json.loads(text)
    except Exception:
        return tuple()
    if not isinstance(parsed, list):
        return tuple()
    aliases = [str(item).strip() for item in parsed if str(item).strip()]
    return tuple(dict.fromkeys(aliases))


def _load_artist_entries_from_csv(path: Path) -> list[ArtistEntry]:
    if not path.exists():
        return []
    rows: list[ArtistEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("is_enabled", "1")).strip() != "1":
                continue
            artist_id = str(row.get("artist_id", "")).strip()
            canonical_name = str(row.get("canonical_name", "")).strip()
            if not artist_id or not canonical_name:
                continue
            rows.append(
                ArtistEntry(
                    artist_id=artist_id,
                    canonical_name=canonical_name,
                    aliases=_parse_aliases_json(row.get("aliases_json")),
                    source=str(row.get("source", "")).strip(),
                    is_enabled=True,
                )
            )
    return rows


def _compact_text(text: str) -> str:
    return re.sub(r"[\s\-_/.,()\[\]{}<>【】［］＜＞'\"`]+", "", str(text or ""))


def _is_valid_match(canonical_name: str, matched_alias: str) -> bool:
    canonical_compact = _compact_text(canonical_name)
    alias_compact = _compact_text(matched_alias)
    if len(canonical_compact) <= 1 or len(alias_compact) <= 1:
        return False
    if alias_compact in AMBIGUOUS_SINGLE_TOKENS:
        return False
    if re.fullmatch(r"[A-Za-z0-9]+", alias_compact) and len(alias_compact) <= 2:
        return False
    return True


def _is_music_like_title(title: str) -> bool:
    text = str(title or "").strip().lower()
    if not text:
        return False
    if any(keyword in text for keyword in NON_MUSIC_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in MUSIC_HINT_KEYWORDS)


def load_merged_registry(jp_seed_path: Path) -> list[ArtistEntry]:
    merged: dict[str, ArtistEntry] = {}
    for entry in load_registry():
        merged[entry.artist_id] = entry
    for entry in _load_artist_entries_from_csv(jp_seed_path):
        merged[entry.artist_id] = entry
    return list(merged.values())


def load_target_titles(events_db_path: Path, limit: int = 0) -> list[str]:
    if not events_db_path.exists():
        return []
    with sqlite3.connect(events_db_path) as conn:
        df = conn.execute(
            """
            SELECT DISTINCT title
            FROM events
            WHERE COALESCE(TRIM(performers), '') = ''
              AND COALESCE(TRIM(title), '') <> ''
            ORDER BY title
            """
        ).fetchall()
    titles = [str(row[0]).strip() for row in df if row and str(row[0]).strip()]
    if limit > 0:
        return titles[:limit]
    return titles


def infer_title_artist(
    title: str, artist_index: dict[str, object]
) -> tuple[str, str, str] | None:
    if not _is_music_like_title(title):
        return None
    matches = match_artists_in_title(title, artist_index)
    primary, confidence = choose_primary_match(matches)
    if primary is None or confidence != "high":
        return None
    canonical_name = str(primary.get("canonical_name", "")).strip()
    matched_alias = str(primary.get("matched_alias", "")).strip()
    if not canonical_name or not matched_alias:
        return None
    if not _is_valid_match(canonical_name, matched_alias):
        return None
    return canonical_name, confidence, matched_alias


def write_csv_noop(rows: list[dict[str, str]], output_path: Path) -> bool:
    columns = [
        "title",
        "artist_name",
        "artist_confidence",
        "matched_alias",
        "updated_at",
    ]
    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in columns})
    new_content = buf.getvalue()

    if output_path.exists():
        old_content = output_path.read_text(encoding="utf-8")
        if old_content == new_content:
            return False

    output_path.write_text(new_content, encoding="utf-8", newline="")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build inferred artist map for events")
    parser.add_argument("--db-path", default=str(EVENTS_DB_PATH))
    parser.add_argument("--jp-seed-path", default=str(JP_SEED_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    events_db_path = Path(args.db_path)
    jp_seed_path = Path(args.jp_seed_path)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    titles = load_target_titles(events_db_path, limit=max(0, int(args.limit)))
    if not titles:
        logger.warning("No target titles found. Skip.")
        return

    registry = load_merged_registry(jp_seed_path)
    artist_index = build_artist_index(registry)
    updated_at = date.today().isoformat()

    rows: list[dict[str, str]] = []
    for idx, title in enumerate(titles, start=1):
        inferred = infer_title_artist(title, artist_index)
        if inferred is None:
            continue
        artist_name, confidence, matched_alias = inferred
        rows.append(
            {
                "title": title,
                "artist_name": artist_name,
                "artist_confidence": confidence,
                "matched_alias": matched_alias,
                "updated_at": updated_at,
            }
        )
        if idx % 500 == 0:
            logger.info("Processed %d/%d titles", idx, len(titles))

    rows.sort(key=lambda row: row["title"])
    changed = write_csv_noop(rows, output_path)
    if changed:
        logger.info("Wrote %d inferred rows to %s", len(rows), output_path)
    else:
        logger.info("No changes in %s", output_path)


if __name__ == "__main__":
    main()

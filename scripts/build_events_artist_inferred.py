"""Build inferred artist map for venue-official events from title/description matching.

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

from .events.category import classify_event_category
from .signals.entity_aliases import load_artist_lookup_maps, normalize_with_lookup
from .signals.artist_registry import (
    ArtistEntry,
    build_artist_index,
    choose_primary_match,
    load_registry,
    match_artists_in_title,
    normalize_text,
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

AMBIGUOUS_ALIAS_TOKENS = {
    "ベン",
    "たま",
    "ナビ",
    "声",
    "dream",
}
AMBIGUOUS_ALIAS_COMPACT_TOKENS = {
    re.sub(r"[\s\-_/.,()\[\]{}<>【】［］＜＞'\"`]+", "", str(token)).lower()
    for token in AMBIGUOUS_ALIAS_TOKENS
}

GENERIC_ALIAS_TOKENS = {
    "dome",
    "arena",
    "hall",
    "live",
    "tour",
    "concert",
    "show",
    "showcase",
    "festival",
    "fes",
    "oneman",
    "onelive",
    "fanmeeting",
    "ticket",
    "open",
    "start",
    "vol",
    "part",
    "event",
    "music",
    "special",
    "the",
    "with",
    "and",
    "dream",
    "ライブ",
    "コンサート",
    "ツアー",
    "公演",
    "イベント",
    "フェス",
    "ワンマン",
    "ドーム",
    "アリーナ",
    "ホール",
}
GENERIC_ALIAS_COMPACT_TOKENS = {
    re.sub(r"[\s\-_/.,()\[\]{}<>【】［］＜＞'\"`]+", "", str(token)).lower()
    for token in GENERIC_ALIAS_TOKENS
}

MUSIC_HINT_KEYWORDS = [
    "ライブ",
    "コンサート",
    "公演",
    "ツアー",
    "フェス",
    "ファンミ",
    "リサイタル",
    "オーケストラ",
    "弾き語り",
    "ワンマン",
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
    "ホークス",
    "ファイターズ",
    "ライオンズ",
    "マリーンズ",
    "フットサル",
    "マラソン",
    "グランプリ",
    "m-1",
    "スポーツフェスティバル",
    "就活",
    "就職",
    "説明会",
    "展示会",
    "見本市",
    "expo",
    "フェア",
    "学会",
    "大会",
    "カップ",
    "式典",
    "授与式",
    "卒業式",
    "入学式",
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
    return re.sub(r"[\s\-_/.,()\[\]{}<>【】［］＜＞'\"`]+", "", str(text or "")).lower()


def _is_valid_match(canonical_name: str, matched_alias: str) -> bool:
    canonical_compact = _compact_text(canonical_name)
    alias_compact = _compact_text(matched_alias)
    if len(alias_compact) <= 1:
        return False
    # Allow one-character canonical names (e.g. 嵐) when alias token is
    # sufficiently specific; otherwise keep them filtered out.
    if len(canonical_compact) <= 1 and len(alias_compact) <= 2:
        return False
    if alias_compact in AMBIGUOUS_SINGLE_TOKENS:
        return False
    if alias_compact in AMBIGUOUS_ALIAS_COMPACT_TOKENS:
        return False
    if alias_compact in GENERIC_ALIAS_COMPACT_TOKENS:
        return False
    if re.fullmatch(r"[a-z0-9]+", alias_compact) and len(alias_compact) <= 2:
        return False
    return True


def _contains_non_music_exclude_keyword(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in NON_MUSIC_EXCLUDE_KEYWORDS)


def _is_music_like_text(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if _contains_non_music_exclude_keyword(normalized):
        return False
    return any(keyword in normalized for keyword in MUSIC_HINT_KEYWORDS)


def load_merged_registry(extra_seed_path: Path | None) -> list[ArtistEntry]:
    merged: dict[str, ArtistEntry] = {}
    for entry in load_registry():
        merged[entry.artist_id] = entry
    if extra_seed_path and extra_seed_path.exists():
        for entry in _load_artist_entries_from_csv(extra_seed_path):
            if entry.artist_id not in merged:
                merged[entry.artist_id] = entry
    return list(merged.values())


def load_target_events(events_db_path: Path, limit: int = 0) -> list[dict[str, str]]:
    if not events_db_path.exists():
        return []
    with sqlite3.connect(events_db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_uid, title, COALESCE(description, '')
            FROM events
            WHERE COALESCE(TRIM(performers), '') = ''
              AND COALESCE(TRIM(title), '') <> ''
            ORDER BY start_date, event_uid
            """
        ).fetchall()
    out = [
        {
            "event_uid": str(row[0]).strip(),
            "title": str(row[1]).strip(),
            "description": str(row[2]).strip(),
        }
        for row in rows
        if row and str(row[0]).strip() and str(row[1]).strip()
    ]
    if limit > 0:
        return out[:limit]
    return out


def _infer_from_text(
    text: str, artist_index: dict[str, object]
) -> tuple[str, str, str] | None:
    matches = [
        match
        for match in match_artists_in_title(text, artist_index)
        if _is_valid_match(
            str(match.get("canonical_name", "")).strip(),
            str(match.get("matched_alias", "")).strip(),
        )
    ]
    primary, confidence = choose_primary_match(matches)
    if primary is None:
        return None
    canonical_name = str(primary.get("canonical_name", "")).strip()
    matched_alias = str(primary.get("matched_alias", "")).strip()
    if not canonical_name or not matched_alias:
        return None
    if confidence != "high":
        if confidence != "medium":
            return None
        is_strong_medium = any(
            str(match.get("canonical_name", "")).strip() == canonical_name
            and int(match.get("pos", -1)) == 0
            and int(match.get("length", 0)) >= 4
            for match in matches
        )
        if not is_strong_medium:
            return None
    return canonical_name, confidence, matched_alias


def infer_event_artist(
    title: str, description: str, artist_index: dict[str, object]
) -> tuple[str, str, str, str] | None:
    title_text = str(title or "").strip()
    description_text = str(description or "").strip()
    title_is_music_like = _is_music_like_text(title_text)
    desc_is_music_like = _is_music_like_text(description_text)

    title_match = _infer_from_text(title_text, artist_index) if title_text else None
    if title_match is not None:
        if title_is_music_like:
            return (*title_match, "title")
        # Accept exact title=artist matches even without music hint words.
        # This recovers venue pages that list only artist names as event titles.
        matched_canonical, _confidence, matched_alias = title_match
        title_compact = normalize_text(title_text, mode="compact")
        if title_compact:
            canonical_compact = normalize_text(matched_canonical, mode="compact")
            alias_compact = normalize_text(matched_alias, mode="compact")
            if title_compact in {canonical_compact, alias_compact}:
                return (*title_match, "title")

    if not description_text:
        return None
    if not (title_is_music_like or desc_is_music_like):
        return None

    description_match = _infer_from_text(description_text, artist_index)
    if description_match is not None:
        return (*description_match, "description")

    combined_text = f"{title_text} {description_text}".strip()
    combined_match = _infer_from_text(combined_text, artist_index)
    if combined_match is not None:
        return (*combined_match, "title+description")
    return None


def _normalize_cross_venue_title_key(title: object) -> str:
    text = " ".join(str(title or "").strip().split())
    if not text:
        return ""
    text = re.sub(r"^\s*(?:コンサート|ライブ|公演|イベント|野球)\s*", "", text)
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    text = re.sub(r"[「」『』]", "", text)
    return normalize_text(text, mode="compact")


def _build_cross_venue_title_artist_map(
    rows: list[tuple[str, ...]],
    artist_keep_map: dict[str, str],
    artist_compact_map: dict[str, str],
) -> dict[str, str]:
    title_candidates: dict[str, set[str]] = {}
    for _event_uid, title, performers, *_ in rows:
        performers_text = str(performers or "").strip()
        if not performers_text:
            continue
        normalized, matched = normalize_with_lookup(
            performers_text, artist_keep_map, artist_compact_map
        )
        artist_name = normalized if matched and normalized else performers_text
        artist_name = str(artist_name or "").strip()
        title_key = _normalize_cross_venue_title_key(title)
        if not artist_name or not title_key:
            continue
        title_candidates.setdefault(title_key, set()).add(artist_name)
    return {
        key: next(iter(names))
        for key, names in title_candidates.items()
        if len(names) == 1
    }


def write_csv_noop(rows: list[dict[str, str]], output_path: Path) -> bool:
    columns = [
        "event_uid",
        "title",
        "artist_name",
        "artist_confidence",
        "matched_alias",
        "matched_field",
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


def ensure_events_artist_columns(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]).strip()
        for row in conn.execute("PRAGMA table_info(events)").fetchall()
        if len(row) >= 2
    }
    if "artist_name_resolved" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN artist_name_resolved TEXT")
    if "artist_confidence" not in cols:
        conn.execute(
            "ALTER TABLE events ADD COLUMN artist_confidence TEXT NOT NULL DEFAULT 'low'"
        )
    if "event_category" not in cols:
        conn.execute(
            "ALTER TABLE events ADD COLUMN event_category TEXT NOT NULL DEFAULT 'その他'"
        )


def sync_resolved_artists_to_events(
    events_db_path: Path,
    inferred_rows: list[dict[str, str]],
) -> tuple[int, int]:
    if not events_db_path.exists():
        return 0, 0

    inferred_map = {
        str(row.get("event_uid", "")).strip(): (
            str(row.get("artist_name", "")).strip(),
            str(row.get("artist_confidence", "")).strip().lower() or "low",
        )
        for row in inferred_rows
        if str(row.get("event_uid", "")).strip() and str(row.get("artist_name", "")).strip()
    }
    artist_keep_map, artist_compact_map = load_artist_lookup_maps()

    with sqlite3.connect(events_db_path) as conn:
        ensure_events_artist_columns(conn)
        rows = conn.execute(
            """
            SELECT
                event_uid,
                COALESCE(TRIM(title), ''),
                COALESCE(TRIM(description), ''),
                COALESCE(TRIM(performers), ''),
                COALESCE(TRIM(artist_name_resolved), ''),
                COALESCE(TRIM(artist_confidence), 'low'),
                COALESCE(TRIM(event_category), '')
            FROM events
            """
        ).fetchall()
        cross_venue_title_artist_map = _build_cross_venue_title_artist_map(
            [(event_uid, title, performers) for event_uid, title, _description, performers, *_ in rows],
            artist_keep_map,
            artist_compact_map,
        )

        updates: list[tuple[str, str, str, str]] = []
        for (
            event_uid,
            title,
            description,
            performers,
            current_resolved,
            current_confidence,
            current_category,
        ) in rows:
            event_uid = str(event_uid or "").strip()
            performers = str(performers or "").strip()
            title = str(title or "").strip()
            description = str(description or "").strip()
            current_resolved = str(current_resolved or "").strip()
            current_confidence = str(current_confidence or "low").strip().lower() or "low"
            current_category = str(current_category or "").strip() or "その他"

            new_resolved = ""
            new_confidence = "low"
            if performers:
                normalized, matched = normalize_with_lookup(
                    performers, artist_keep_map, artist_compact_map
                )
                if matched and normalized and normalized != performers:
                    new_resolved = normalized
                    new_confidence = "source_normalized"
                else:
                    new_resolved = performers
                    new_confidence = "source"
            else:
                inferred = inferred_map.get(event_uid)
                if inferred:
                    new_resolved = inferred[0]
                    new_confidence = inferred[1]
                else:
                    title_key = _normalize_cross_venue_title_key(title)
                    cross_venue_artist = cross_venue_title_artist_map.get(title_key, "")
                    if cross_venue_artist:
                        new_resolved = cross_venue_artist
                        new_confidence = "cross_venue_title"

            new_category = classify_event_category(title, new_resolved, description)
            if (
                new_resolved != current_resolved
                or new_confidence != current_confidence
                or new_category != current_category
            ):
                updates.append((new_resolved, new_confidence, new_category, event_uid))

        if updates:
            conn.executemany(
                """
                UPDATE events
                SET artist_name_resolved = ?,
                    artist_confidence = ?,
                    event_category = ?
                WHERE event_uid = ?
                """,
                updates,
            )
        conn.commit()
        return len(rows), len(updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build inferred artist map for events")
    parser.add_argument("--db-path", default=str(EVENTS_DB_PATH))
    parser.add_argument(
        "--jp-seed-path",
        default=str(JP_SEED_PATH),
        help="Optional additional seed CSV path (merged on top of default registry).",
    )
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    events_db_path = Path(args.db_path)
    extra_seed_path = Path(args.jp_seed_path)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    targets = load_target_events(events_db_path, limit=max(0, int(args.limit)))
    if not targets:
        logger.warning("No target events found for inference. Continue with DB sync only.")
    else:
        registry = load_merged_registry(extra_seed_path)
        artist_index = build_artist_index(registry)
        updated_at = date.today().isoformat()

        for idx, event in enumerate(targets, start=1):
            inferred = infer_event_artist(
                title=event["title"],
                description=event["description"],
                artist_index=artist_index,
            )
            if inferred is None:
                continue
            artist_name, confidence, matched_alias, matched_field = inferred
            rows.append(
                {
                    "event_uid": event["event_uid"],
                    "title": event["title"],
                    "artist_name": artist_name,
                    "artist_confidence": confidence,
                    "matched_alias": matched_alias,
                    "matched_field": matched_field,
                    "updated_at": updated_at,
                }
            )
            if idx % 500 == 0:
                logger.info("Processed %d/%d events", idx, len(targets))

    rows.sort(key=lambda row: (row["event_uid"], row["title"]))
    changed = write_csv_noop(rows, output_path)
    if changed:
        logger.info("Wrote %d inferred rows to %s", len(rows), output_path)
    else:
        logger.info("No changes in %s", output_path)

    total_events, updated_events = sync_resolved_artists_to_events(events_db_path, rows)
    logger.info(
        "Synced resolved artists into events.sqlite: updated %d / %d rows",
        updated_events,
        total_events,
    )


if __name__ == "__main__":
    main()

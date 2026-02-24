"""Artist registry loader and title-based matching helpers for signals."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SEED_PATH = DATA_DIR / "artist_registry.seed.csv"
MANUAL_PATH = DATA_DIR / "artist_registry.manual.csv"


@dataclass(frozen=True)
class ArtistEntry:
    artist_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    source: str
    is_enabled: bool


def load_registry() -> list[ArtistEntry]:
    merged: dict[str, ArtistEntry] = {}
    for path in (SEED_PATH, MANUAL_PATH):
        if not path.exists():
            continue
        for row in _read_registry_csv(path):
            merged[row.artist_id] = row
    return sorted(merged.values(), key=lambda row: row.canonical_name)


def normalize_text(s: str, mode: str = "keep") -> str:
    text = unicodedata.normalize("NFKC", str(s or "")).lower()
    text = text.replace("\u3000", " ")
    text = text.replace("＆", "&")
    text = re.sub(r"[‐–—―ー−]", "-", text)
    text = _strip_leading_decorations(text)
    text = re.sub(r"\s+", " ", text).strip()

    if mode == "compact":
        text = re.sub(r"[\s\-_/.,()\[\]{}<>【】［］＜＞'\"`]+", "", text)
    return text


def build_artist_index(registry: list[ArtistEntry]) -> dict[str, object]:
    keep_map: dict[str, list[dict[str, object]]] = {}
    compact_map: dict[str, list[dict[str, object]]] = {}

    for entry in registry:
        tokens = [entry.canonical_name, *entry.aliases]
        for token in tokens:
            alias = str(token or "").strip()
            if not alias:
                continue
            normalized_keep = normalize_text(alias, mode="keep")
            normalized_compact = normalize_text(alias, mode="compact")
            is_canonical = alias == entry.canonical_name

            if _should_index_key(normalized_keep):
                keep_map.setdefault(normalized_keep, []).append(
                    {
                        "artist_id": entry.artist_id,
                        "canonical_name": entry.canonical_name,
                        "matched_alias": alias,
                        "is_canonical_match": is_canonical,
                    }
                )

            if _should_index_key(normalized_compact):
                compact_map.setdefault(normalized_compact, []).append(
                    {
                        "artist_id": entry.artist_id,
                        "canonical_name": entry.canonical_name,
                        "matched_alias": alias,
                        "is_canonical_match": is_canonical,
                    }
                )

    return {
        "keep": keep_map,
        "compact": compact_map,
    }


def match_artists_in_title(title_raw: str, index: dict[str, object]) -> list[dict[str, object]]:
    title_keep = normalize_text(title_raw, mode="keep")
    title_compact = normalize_text(title_raw, mode="compact")

    matches: list[dict[str, object]] = []
    matches.extend(_match_with_mode(title_keep, index.get("keep", {}), mode="keep"))
    matches.extend(
        _match_with_mode(title_compact, index.get("compact", {}), mode="compact")
    )
    return matches


def choose_primary_match(
    matches: list[dict[str, object]],
) -> tuple[dict[str, object] | None, str]:
    if not matches:
        return None, "low"

    scored: list[tuple[int, dict[str, object]]] = []
    for match in matches:
        score = _to_int(match.get("length"))
        score -= _to_int(match.get("pos"))
        if match.get("is_canonical_match"):
            score += 12
        if match.get("match_mode") == "keep":
            score += 8
        if match.get("word_boundary_ok"):
            score += 5
        scored.append((score, match))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_match = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -999

    confidence = "medium"
    if best_match.get("match_mode") == "keep" and best_match.get("word_boundary_ok"):
        confidence = "high"
    if best_score - second_score <= 2:
        confidence = "medium"

    primary = {
        "artist_id": best_match.get("artist_id", ""),
        "canonical_name": best_match.get("canonical_name", ""),
        "matched_alias": best_match.get("matched_alias", ""),
        "confidence": confidence,
    }
    return primary, confidence


def _read_registry_csv(path: Path) -> list[ArtistEntry]:
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
            aliases = _parse_aliases(row.get("aliases_json"))
            rows.append(
                ArtistEntry(
                    artist_id=artist_id,
                    canonical_name=canonical_name,
                    aliases=aliases,
                    source=str(row.get("source", "")).strip(),
                    is_enabled=True,
                )
            )
    return rows


def _parse_aliases(raw: object) -> tuple[str, ...]:
    if raw is None:
        return tuple()
    text = str(raw).strip()
    if not text:
        return tuple()
    try:
        parsed = json.loads(text)
    except Exception:
        return tuple()
    if not isinstance(parsed, list):
        return tuple()
    out = [str(item).strip() for item in parsed if str(item).strip()]
    return tuple(dict.fromkeys(out))


def _strip_leading_decorations(text: str) -> str:
    out = text.strip()
    for _ in range(8):
        next_out = re.sub(
            r"^\s*(?:【[^】]*】|\[[^\]]*\]|［[^］]*］|＜[^＞]*＞|<[^>]*>|\([^)]*\))\s*",
            "",
            out,
        )
        if next_out == out:
            break
        out = next_out
    return out.strip()


def _is_ascii_alnum_key(key: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+", key))


def _should_index_key(key: str) -> bool:
    if not key:
        return False
    if _is_ascii_alnum_key(key) and len(key) <= 2:
        return False
    return True


def _needs_word_boundary(key: str) -> bool:
    return _is_ascii_alnum_key(key) and len(key) <= 4


def _match_with_mode(
    normalized_title: str,
    index_map: object,
    mode: str,
) -> list[dict[str, object]]:
    if not isinstance(index_map, dict):
        return []

    out: list[dict[str, object]] = []
    keys = sorted((k for k in index_map.keys() if isinstance(k, str)), key=len, reverse=True)
    for key in keys:
        if not key:
            continue
        entries = index_map.get(key)
        if not isinstance(entries, list):
            continue

        if _needs_word_boundary(key):
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])")
            for matched in pattern.finditer(normalized_title):
                for entry in entries:
                    out.append(
                        {
                            "artist_id": entry.get("artist_id", ""),
                            "canonical_name": entry.get("canonical_name", ""),
                            "matched_alias": entry.get("matched_alias", ""),
                            "match_mode": mode,
                            "pos": matched.start(),
                            "length": len(key),
                            "is_canonical_match": bool(entry.get("is_canonical_match")),
                            "word_boundary_ok": True,
                        }
                    )
            continue

        start = normalized_title.find(key)
        while start != -1:
            for entry in entries:
                out.append(
                    {
                        "artist_id": entry.get("artist_id", ""),
                        "canonical_name": entry.get("canonical_name", ""),
                        "matched_alias": entry.get("matched_alias", ""),
                        "match_mode": mode,
                        "pos": start,
                        "length": len(key),
                        "is_canonical_match": bool(entry.get("is_canonical_match")),
                        "word_boundary_ok": True,
                    }
                )
            start = normalized_title.find(key, start + 1)

    return out


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except Exception:
            return 0
    return 0

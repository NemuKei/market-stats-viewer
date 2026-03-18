"""Alias-based normalization helpers for signals entities."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .artist_registry import load_registry as load_artist_registry
from .artist_registry import normalize_text

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
VENUE_REGISTRY_PATH = DATA_DIR / "venue_registry.csv"
VENUE_ALIAS_PATH = DATA_DIR / "venue_aliases.csv"
VENUE_LABEL_PREFIX_RE = re.compile(
    r"^(?:会場名?|場所|venue)\s*[:：_\-]\s*", re.IGNORECASE
)
VENUE_LEADING_MARKERS_RE = re.compile(r"^[\s\u3000○〇●•・◆■□▲△▽▼▶▷►→※＊*]+")
VENUE_SPLIT_RE = re.compile(r"\s*[・/／|｜]\s*")
TRAILING_PAREN_SUFFIX_RE = re.compile(r"\s*[（(][^()（）]{1,20}[）)]\s*$")


@dataclass(frozen=True)
class VenueAliasEntry:
    venue_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    source: str
    is_enabled: bool


def load_artist_lookup_maps() -> tuple[dict[str, str], dict[str, str]]:
    try:
        registry = load_artist_registry()
    except Exception:
        return {}, {}

    entries: list[tuple[str, tuple[str, ...]]] = []
    for row in registry:
        canonical = str(getattr(row, "canonical_name", "") or "").strip()
        aliases = tuple(str(a or "").strip() for a in getattr(row, "aliases", tuple()))
        if canonical:
            entries.append((canonical, aliases))
    return _build_lookup_maps(entries)


def load_venue_lookup_maps() -> tuple[dict[str, str], dict[str, str]]:
    merged: dict[str, VenueAliasEntry] = {}

    for row in _read_venue_registry(VENUE_REGISTRY_PATH):
        merged[row.venue_id] = row
    for row in _read_venue_aliases(VENUE_ALIAS_PATH):
        merged[row.venue_id] = row

    entries = [
        (row.canonical_name, row.aliases)
        for row in merged.values()
        if row.canonical_name.strip()
    ]
    return _build_lookup_maps(entries)


def normalize_with_lookup(
    raw_value: object, keep_map: dict[str, str], compact_map: dict[str, str]
) -> tuple[str, bool]:
    text = str(raw_value or "").strip()
    if not text:
        return "", False
    sanitized = _strip_html_tags(text)
    keep_key = normalize_text(sanitized, mode="keep")
    if keep_key:
        canonical = keep_map.get(keep_key)
        if canonical:
            return canonical, True
    compact_key = normalize_text(sanitized, mode="compact")
    if compact_key:
        canonical = compact_map.get(compact_key)
        if canonical:
            return canonical, True
    return sanitized, False


def normalize_venue_with_lookup(
    raw_value: object, keep_map: dict[str, str], compact_map: dict[str, str]
) -> tuple[str, bool]:
    text = str(raw_value or "").strip()
    if not text:
        return "", False
    sanitized = _strip_html_tags(text)
    for candidate in _iter_venue_lookup_candidates(sanitized):
        canonical, matched = normalize_with_lookup(candidate, keep_map, compact_map)
        if matched:
            return canonical, True
    return sanitized, False


def _build_lookup_maps(
    entries: list[tuple[str, tuple[str, ...]]],
) -> tuple[dict[str, str], dict[str, str]]:
    keep_candidates: dict[str, set[str]] = {}
    compact_candidates: dict[str, set[str]] = {}

    for canonical_name, aliases in entries:
        canonical = str(canonical_name or "").strip()
        if not canonical:
            continue
        tokens = list(dict.fromkeys([canonical, *list(aliases)]))
        for token in tokens:
            alias = str(token or "").strip()
            if not alias:
                continue
            keep_key = normalize_text(alias, mode="keep")
            compact_key = normalize_text(alias, mode="compact")
            if keep_key:
                keep_candidates.setdefault(keep_key, set()).add(canonical)
            if compact_key:
                compact_candidates.setdefault(compact_key, set()).add(canonical)

    keep_map = {
        key: next(iter(names))
        for key, names in keep_candidates.items()
        if len(names) == 1
    }
    compact_map = {
        key: next(iter(names))
        for key, names in compact_candidates.items()
        if len(names) == 1
    }
    return keep_map, compact_map


def _read_venue_registry(path: Path) -> list[VenueAliasEntry]:
    if not path.exists():
        return []
    rows: list[VenueAliasEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            venue_id = str(row.get("venue_id", "")).strip()
            canonical_name = str(row.get("venue_name", "")).strip()
            if not venue_id or not canonical_name:
                continue
            rows.append(
                VenueAliasEntry(
                    venue_id=venue_id,
                    canonical_name=canonical_name,
                    aliases=(canonical_name,),
                    source="official",
                    is_enabled=True,
                )
            )
    return rows


def _read_venue_aliases(path: Path) -> list[VenueAliasEntry]:
    if not path.exists():
        return []
    rows: list[VenueAliasEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("is_enabled", "1")).strip() != "1":
                continue
            venue_id = str(row.get("venue_id", "")).strip()
            canonical_name = str(row.get("canonical_name", "")).strip()
            if not venue_id or not canonical_name:
                continue
            aliases = _parse_aliases(row.get("aliases_json"))
            rows.append(
                VenueAliasEntry(
                    venue_id=venue_id,
                    canonical_name=canonical_name,
                    aliases=aliases,
                    source=str(row.get("source", "")).strip(),
                    is_enabled=True,
                )
            )
    return rows


def _parse_aliases(raw: object) -> tuple[str, ...]:
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


def _strip_html_tags(text: str) -> str:
    cleaned = re.sub(r"</?[^>]+>", "", str(text or ""))
    return " ".join(cleaned.split())


def _iter_venue_lookup_candidates(text: str):
    queue = [" ".join(str(text or "").split())]
    seen: set[str] = set()

    while queue:
        candidate = queue.pop(0).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        yield candidate

        stripped = VENUE_LEADING_MARKERS_RE.sub("", candidate).strip()
        stripped = VENUE_LABEL_PREFIX_RE.sub("", stripped).strip()
        if stripped and stripped != candidate:
            queue.append(stripped)

        without_suffix = _strip_trailing_parenthetical_suffix(stripped or candidate)
        if without_suffix and without_suffix != candidate:
            queue.append(without_suffix)

        for split_candidate in _split_venue_candidate(stripped or candidate):
            if split_candidate and split_candidate != candidate:
                queue.append(split_candidate)
            trimmed_split = _strip_trailing_parenthetical_suffix(split_candidate)
            if trimmed_split and trimmed_split != split_candidate:
                queue.append(trimmed_split)


def _split_venue_candidate(text: str) -> list[str]:
    candidate = " ".join(str(text or "").split())
    if not candidate:
        return []
    parts = VENUE_SPLIT_RE.split(candidate, maxsplit=1)
    if len(parts) != 2:
        return []
    _, tail = parts
    tail = tail.strip()
    if not tail:
        return []
    return [tail]


def _strip_trailing_parenthetical_suffix(text: str) -> str:
    candidate = " ".join(str(text or "").split())
    while candidate:
        updated = TRAILING_PAREN_SUFFIX_RE.sub("", candidate).strip()
        if updated == candidate:
            break
        candidate = updated
    return candidate

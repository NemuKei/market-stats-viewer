"""Audit unresolved artist/venue aliases in event_signals."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_with_lookup,
)

SIGNALS_DB_PATH = REPO_ROOT / "data" / "event_signals.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit alias candidates from signals DB")
    parser.add_argument(
        "--db-path",
        default=str(SIGNALS_DB_PATH),
        help="Path to event_signals.sqlite",
    )
    parser.add_argument("--top", type=int, default=20, help="Top N candidates to print")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    artist_keep, artist_compact = load_artist_lookup_maps()
    venue_keep, venue_compact = load_venue_lookup_maps()

    unknown_artists: Counter[str] = Counter()
    unknown_venues: Counter[str] = Counter()
    normalized_artist_pairs: Counter[tuple[str, str]] = Counter()
    normalized_venue_pairs: Counter[tuple[str, str]] = Counter()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT labels_json FROM signals WHERE labels_json IS NOT NULL AND TRIM(labels_json) <> ''"
        ).fetchall()

    for (labels_json,) in rows:
        try:
            labels = json.loads(labels_json)
        except Exception:
            continue
        if not isinstance(labels, dict):
            continue

        artist_raw = str(
            labels.get("raw_artist_name", labels.get("artist_name", ""))
        ).strip()
        artist_name = str(labels.get("artist_name", "")).strip()
        if artist_raw:
            normalized, matched = normalize_with_lookup(
                artist_raw, artist_keep, artist_compact
            )
            if not matched:
                unknown_artists[artist_raw] += 1
            elif normalized and normalized != artist_raw:
                normalized_artist_pairs[(artist_raw, artist_name)] += 1

        venue_raw = str(labels.get("raw_venue_name", labels.get("venue_name", ""))).strip()
        venue_name = str(labels.get("venue_name", "")).strip()
        if venue_raw:
            normalized, matched = normalize_with_lookup(venue_raw, venue_keep, venue_compact)
            if not matched:
                unknown_venues[venue_raw] += 1
            elif normalized and normalized != venue_raw:
                normalized_venue_pairs[(venue_raw, venue_name)] += 1

    top_n = max(1, int(args.top))
    print(f"signals_rows={len(rows)}")
    print("")
    print("=== Unknown Artist Candidates ===")
    if not unknown_artists:
        print("(none)")
    else:
        for name, count in unknown_artists.most_common(top_n):
            print(f"{count:4d} | {name}")

    print("")
    print("=== Unknown Venue Candidates ===")
    if not unknown_venues:
        print("(none)")
    else:
        for name, count in unknown_venues.most_common(top_n):
            print(f"{count:4d} | {name}")

    print("")
    print("=== Normalized Artist Examples ===")
    if not normalized_artist_pairs:
        print("(none)")
    else:
        for (raw, normalized), count in normalized_artist_pairs.most_common(top_n):
            print(f"{count:4d} | {raw} => {normalized}")

    print("")
    print("=== Normalized Venue Examples ===")
    if not normalized_venue_pairs:
        print("(none)")
    else:
        for (raw, normalized), count in normalized_venue_pairs.most_common(top_n):
            print(f"{count:4d} | {raw} => {normalized}")


if __name__ == "__main__":
    main()

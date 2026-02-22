"""Load venue_registry.csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .types import VenueRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "data" / "venue_registry.csv"


def load_registry(path: Path | None = None) -> list[VenueRecord]:
    """Return list of VenueRecord from CSV."""
    p = path or REGISTRY_PATH
    records: list[VenueRecord] = []
    with p.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cap_str = row.get("capacity", "").strip()
            capacity = int(cap_str) if cap_str else None
            is_enabled = row.get("is_enabled", "0").strip() == "1"
            config_raw = row.get("config_json", "").strip()
            records.append(
                VenueRecord(
                    venue_id=row["venue_id"].strip(),
                    venue_name=row["venue_name"].strip(),
                    pref_code=row["pref_code"].strip().zfill(2),
                    pref_name=row["pref_name"].strip(),
                    capacity=capacity,
                    official_url=row.get("official_url", "").strip(),
                    source_type=row["source_type"].strip(),
                    source_url=row["source_url"].strip(),
                    config_json=config_raw if config_raw else None,
                    is_enabled=is_enabled,
                )
            )
    return records

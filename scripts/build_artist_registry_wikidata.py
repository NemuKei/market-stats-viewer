"""Build artist registry seed CSV from Wikidata SPARQL results."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import time
from datetime import date
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SEED_PATH = DATA_DIR / "artist_registry.seed.csv"
MANUAL_PATH = DATA_DIR / "artist_registry.manual.csv"

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "market-stats-viewer/1.0 (+https://github.com/NemuKei/market-stats-viewer)"

SPARQL_QUERY_LEGACY = """
SELECT ?item ?itemLabel (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases) WHERE {
  { ?item wdt:P31/wdt:P279* wd:Q215380 . } UNION { ?item wdt:P31 wd:Q5 . }
  ?item wdt:P136 wd:Q213665 .
  OPTIONAL { ?item skos:altLabel ?alias . FILTER (lang(?alias) IN ("ja","en","ko")) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en,ko,[AUTO_LANGUAGE],mul". }
}
GROUP BY ?item ?itemLabel
""".strip()

COUNTRY_QID_MAP = {
    "jp": "Q17",  # Japan
    "kr": "Q884",  # South Korea
}

logger = logging.getLogger(__name__)
SEED_COLUMNS = [
    "artist_id",
    "canonical_name",
    "aliases_json",
    "source",
    "updated_at",
    "is_enabled",
    "ticketjam_watch",
    "ticketjam_benchmark_tier",
    "ticketjam_watch_reason",
]


def fetch_sparql_with_retry(
    endpoint: str,
    query: str,
    max_attempts: int = 5,
    base_wait: float = 1.5,
    request_timeout: int = 60,
) -> dict:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    params = {"query": query, "format": "json"}

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(
                endpoint, params=params, headers=headers, timeout=request_timeout
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"retryable status={resp.status_code}")
            resp.raise_for_status()
        except Exception as exc:
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Wikidata fetch failed after {attempt} attempts"
                ) from exc
            wait = base_wait * (2 ** (attempt - 1)) + random.uniform(0.0, 0.6)
            logger.warning(
                "Retry %d/%d after error: %s (wait %.1fs)",
                attempt,
                max_attempts,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError("Wikidata fetch failed")


def build_seed_rows(payload: dict) -> list[dict[str, object]]:
    bindings = (
        payload.get("results", {}).get("bindings", [])
        if isinstance(payload, dict)
        else []
    )

    rows: list[dict[str, object]] = []
    for item in bindings:
        if not isinstance(item, dict):
            continue
        item_uri = _value(item, "item")
        canonical_name = _value(item, "itemLabel")
        aliases_raw = _value(item, "aliases")
        artist_id = _qid_from_uri(item_uri)
        if not artist_id or not canonical_name:
            continue

        alias_items = []
        if aliases_raw:
            alias_items = [
                part.strip() for part in aliases_raw.split("|") if part.strip()
            ]
        aliases = [alias for alias in alias_items if alias and alias != canonical_name]
        aliases = list(dict.fromkeys(aliases))

        rows.append(
            {
                "artist_id": f"wd:{artist_id}",
                "canonical_name": canonical_name,
                "aliases_json": json.dumps(aliases, ensure_ascii=False),
                "source": "wikidata",
                "updated_at": "",
                "is_enabled": 1,
                "ticketjam_watch": 0,
                "ticketjam_benchmark_tier": "",
                "ticketjam_watch_reason": "",
            }
        )

    rows.sort(key=lambda row: str(row["canonical_name"]))
    return rows


def _load_existing_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            artist_id = str(row.get("artist_id", "")).strip()
            if not artist_id:
                continue
            out[artist_id] = {
                "artist_id": artist_id,
                "canonical_name": str(row.get("canonical_name", "")).strip(),
                "aliases_json": str(row.get("aliases_json", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "updated_at": str(row.get("updated_at", "")).strip(),
                "is_enabled": str(row.get("is_enabled", "")).strip(),
                "ticketjam_watch": str(row.get("ticketjam_watch", "") or "").strip(),
                "ticketjam_benchmark_tier": str(
                    row.get("ticketjam_benchmark_tier", "") or ""
                ).strip(),
                "ticketjam_watch_reason": str(
                    row.get("ticketjam_watch_reason", "") or ""
                ).strip(),
            }
    return out


def _is_same_seed_payload(new_row: dict[str, object], old_row: dict[str, str]) -> bool:
    for key in ["canonical_name", "aliases_json", "source", "is_enabled"]:
        if str(new_row.get(key, "")).strip() != str(old_row.get(key, "")).strip():
            return False
    return True


def stabilize_updated_at_with_existing(
    rows: list[dict[str, object]], path: Path, updated_at: str
) -> list[dict[str, object]]:
    existing = _load_existing_rows(path)
    stabilized: list[dict[str, object]] = []
    for row in rows:
        artist_id = str(row.get("artist_id", "")).strip()
        old_row = existing.get(artist_id)
        row_copy = dict(row)
        if old_row and _is_same_seed_payload(row_copy, old_row):
            row_copy["updated_at"] = old_row.get("updated_at", "") or updated_at
        else:
            row_copy["updated_at"] = updated_at
        if old_row:
            row_copy["ticketjam_watch"] = old_row.get("ticketjam_watch", "") or 0
            row_copy["ticketjam_benchmark_tier"] = (
                old_row.get("ticketjam_benchmark_tier", "") or ""
            )
            row_copy["ticketjam_watch_reason"] = (
                old_row.get("ticketjam_watch_reason", "") or ""
            )
        stabilized.append(row_copy)
    stabilized.sort(key=lambda item: str(item.get("canonical_name", "")))
    return stabilized


def write_seed_csv_noop(rows: list[dict[str, object]], path: Path) -> bool:
    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=SEED_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in SEED_COLUMNS})
    new_content = buf.getvalue()

    if path.exists():
        old_content = path.read_text(encoding="utf-8")
        if old_content == new_content:
            return False

    path.write_text(new_content, encoding="utf-8", newline="")
    return True


def ensure_manual_csv(path: Path) -> None:
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEED_COLUMNS, lineterminator="\n")
        writer.writeheader()


def _value(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, dict):
        return ""
    raw = value.get("value")
    return str(raw).strip() if raw is not None else ""


def _qid_from_uri(uri: str) -> str:
    if not uri:
        return ""
    if "/entity/" not in uri:
        return ""
    qid = uri.rsplit("/", 1)[-1].strip()
    if not qid.startswith("Q"):
        return ""
    return qid


def build_country_filtered_query(country_codes: list[str]) -> str:
    country_qids = [
        COUNTRY_QID_MAP[code] for code in country_codes if code in COUNTRY_QID_MAP
    ]
    if not country_qids:
        return SPARQL_QUERY_LEGACY

    values = " ".join(f"wd:{qid}" for qid in country_qids)
    return f"""
SELECT ?item ?itemLabel (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases) WHERE {{
  VALUES ?country {{ {values} }}
  {{
    ?item wdt:P31 wd:Q5 ;
          wdt:P27 ?country ;
          wdt:P106/wdt:P279* wd:Q639669 .
  }}
  UNION
  {{
    ?item wdt:P31/wdt:P279* wd:Q215380 ;
          wdt:P495 ?country .
  }}
  OPTIONAL {{ ?item skos:altLabel ?alias . FILTER (lang(?alias) IN ("ja","en","ko")) }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en,ko,[AUTO_LANGUAGE],mul". }}
}}
GROUP BY ?item ?itemLabel
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build artist registry seed CSV from Wikidata."
    )
    parser.add_argument(
        "--countries",
        default="",
        help="Comma-separated country codes (supported: jp,kr). Empty keeps legacy query.",
    )
    parser.add_argument(
        "--output",
        default=str(SEED_PATH),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=60,
        help="SPARQL request timeout seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    countries = [
        c.strip().lower()
        for c in str(args.countries).split(",")
        if c and c.strip()
    ]
    query = build_country_filtered_query(countries)
    output_path = Path(args.output)
    payload = fetch_sparql_with_retry(
        SPARQL_ENDPOINT, query, request_timeout=max(10, int(args.request_timeout))
    )
    rows = build_seed_rows(payload)
    rows = stabilize_updated_at_with_existing(
        rows=rows,
        path=output_path,
        updated_at=date.today().strftime("%Y-%m-%d"),
    )
    changed = write_seed_csv_noop(rows, output_path)
    ensure_manual_csv(MANUAL_PATH)

    if changed:
        logger.info("Wrote %d rows to %s", len(rows), output_path)
    else:
        logger.info("No changes in %s", output_path)


if __name__ == "__main__":
    main()

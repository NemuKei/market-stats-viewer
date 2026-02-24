"""Build artist registry seed CSV from Wikidata SPARQL results."""

from __future__ import annotations

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

SPARQL_QUERY = """
SELECT ?item ?itemLabel (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases) WHERE {
  { ?item wdt:P31/wdt:P279* wd:Q215380 . } UNION { ?item wdt:P31 wd:Q5 . }
  ?item wdt:P136 wd:Q213665 .
  OPTIONAL { ?item skos:altLabel ?alias . FILTER (lang(?alias) IN ("ja","en","ko")) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en,ko,[AUTO_LANGUAGE],mul". }
}
GROUP BY ?item ?itemLabel
""".strip()

logger = logging.getLogger(__name__)


def fetch_sparql_with_retry(
    endpoint: str,
    query: str,
    max_attempts: int = 5,
    base_wait: float = 1.5,
) -> dict:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    params = {"query": query, "format": "json"}

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(endpoint, params=params, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"retryable status={resp.status_code}")
            resp.raise_for_status()
        except Exception as exc:
            if attempt >= max_attempts:
                raise RuntimeError(f"Wikidata fetch failed after {attempt} attempts") from exc
            wait = base_wait * (2 ** (attempt - 1)) + random.uniform(0.0, 0.6)
            logger.warning("Retry %d/%d after error: %s (wait %.1fs)", attempt, max_attempts, exc, wait)
            time.sleep(wait)

    raise RuntimeError("Wikidata fetch failed")


def build_seed_rows(payload: dict) -> list[dict[str, object]]:
    bindings = (
        payload.get("results", {}).get("bindings", [])
        if isinstance(payload, dict)
        else []
    )

    rows: list[dict[str, object]] = []
    updated_at = date.today().strftime("%Y-%m-%d")

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
            alias_items = [part.strip() for part in aliases_raw.split("|") if part.strip()]
        aliases = [alias for alias in alias_items if alias and alias != canonical_name]
        aliases = list(dict.fromkeys(aliases))

        rows.append(
            {
                "artist_id": f"wd:{artist_id}",
                "canonical_name": canonical_name,
                "aliases_json": json.dumps(aliases, ensure_ascii=False),
                "source": "wikidata",
                "updated_at": updated_at,
                "is_enabled": 1,
            }
        )

    rows.sort(key=lambda row: str(row["canonical_name"]))
    return rows


def write_seed_csv_noop(rows: list[dict[str, object]], path: Path) -> bool:
    columns = [
        "artist_id",
        "canonical_name",
        "aliases_json",
        "source",
        "updated_at",
        "is_enabled",
    ]

    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in columns})
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
    columns = [
        "artist_id",
        "canonical_name",
        "aliases_json",
        "source",
        "updated_at",
        "is_enabled",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = fetch_sparql_with_retry(SPARQL_ENDPOINT, SPARQL_QUERY)
    rows = build_seed_rows(payload)
    changed = write_seed_csv_noop(rows, SEED_PATH)
    ensure_manual_csv(MANUAL_PATH)

    if changed:
        logger.info("Wrote %d rows to %s", len(rows), SEED_PATH)
    else:
        logger.info("No changes in %s", SEED_PATH)


if __name__ == "__main__":
    main()

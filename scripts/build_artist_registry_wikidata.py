"""Build artist registry seeds; Japan fetches IDs before API attributes."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import random
import time
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SEED_PATH = DATA_DIR / "artist_registry.seed.csv"
MANUAL_PATH = DATA_DIR / "artist_registry.manual.csv"

API_ENDPOINT = "https://www.wikidata.org/w/api.php"
REQUEST_INTERVAL_SECONDS = 5.0
MAX_SINGLE_WAIT_SECONDS = 300.0
MAX_FETCH_SECONDS = 4.5 * 60 * 60
MIN_SEED_ROW_RATIO = 0.9
OCCUPATION_BATCH_SIZE = 50
MUSICIAN_OCCUPATIONS_QUERY = (
    "SELECT DISTINCT ?occupation WHERE { ?occupation wdt:P279* wd:Q639669 . }"
)

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


class WikidataQueryTimeout(RuntimeError):
    """A query partition exceeded the server/client time limit."""


class AcquisitionLimitError(RuntimeError):
    """Stop rather than exceed a wait limit or the acquisition deadline."""


def _check_deadline(deadline: float, required_seconds: float = 0.0) -> None:
    if deadline - time.monotonic() <= required_seconds:
        raise AcquisitionLimitError("Wikidata acquisition deadline exhausted")


def _sleep_with_budget(seconds: float, deadline: float, reserve: float = 0.0) -> None:
    if not math.isfinite(seconds) or seconds > MAX_SINGLE_WAIT_SECONDS:
        raise AcquisitionLimitError("Wikidata wait exceeds single-wait limit")
    _check_deadline(deadline, seconds + reserve)
    time.sleep(seconds)
    _check_deadline(deadline, reserve)


def _retry_after_seconds(value: str) -> float:
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(
                0.0,
                (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _fetch_json_with_retry(
    endpoint: str,
    params: dict[str, object],
    request_timeout: int,
    max_attempts: int = 5,
    base_wait: float = 1.5,
    retry_timeouts: bool = True,
    deadline: float | None = None,
) -> dict:
    if deadline is None:
        deadline = time.monotonic() + MAX_FETCH_SECONDS
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if endpoint == SPARQL_ENDPOINT:
        headers["Accept"] = "application/sparql-results+json"
    for attempt in range(1, max_attempts + 1):
        retry_after = 0.0
        try:
            _sleep_with_budget(REQUEST_INTERVAL_SECONDS, deadline, request_timeout)
            resp = requests.get(
                endpoint, params=params, headers=headers, timeout=request_timeout
            )
            _check_deadline(deadline)
            retry_after = _retry_after_seconds(
                getattr(resp, "headers", {}).get("Retry-After", "")
            )
            if resp.status_code in {429, 500, 502, 503, 504}:
                if (
                    "TimeoutException" in getattr(resp, "text", "")
                    or resp.status_code == 504
                ):
                    raise WikidataQueryTimeout("WDQS query timed out")
                raise requests.HTTPError(f"retryable status={resp.status_code}")
            if resp.status_code != 200:
                resp.raise_for_status()
            if "TimeoutException" in getattr(resp, "text", ""):
                raise WikidataQueryTimeout("WDQS timeout in HTTP 200 body")
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError("Wikidata response must be an object")
            if "error" in payload:
                error = payload["error"]
                if isinstance(error, dict) and error.get("code") == "maxlag":
                    retry_after = max(retry_after, 5.0)
                raise RuntimeError("Wikidata API error: " + str(error))
            _check_deadline(deadline)
            return payload
        except AcquisitionLimitError:
            raise
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if attempt >= max_attempts or (
                not retry_timeouts
                and isinstance(exc, (WikidataQueryTimeout, requests.Timeout))
            ):
                error_type = (
                    WikidataQueryTimeout
                    if isinstance(exc, (WikidataQueryTimeout, requests.Timeout))
                    else RuntimeError
                )
                raise error_type(
                    f"Wikidata fetch failed after {attempt} attempts"
                ) from exc
            wait = max(
                retry_after, base_wait * (2 ** (attempt - 1)) + random.uniform(0.0, 0.6)
            )
            logger.warning(
                "Retry %d/%d after %s (wait %.1fs)",
                attempt,
                max_attempts,
                type(exc).__name__,
                wait,
            )
            _sleep_with_budget(
                wait, deadline, REQUEST_INTERVAL_SECONDS + request_timeout
            )
    raise RuntimeError("Wikidata fetch failed")


def sparql_bindings(payload: dict) -> list[dict]:
    results = payload.get("results") if isinstance(payload, dict) else None
    bindings = results.get("bindings") if isinstance(results, dict) else None
    if not isinstance(bindings, list) or any(
        not isinstance(row, dict) for row in bindings
    ):
        raise RuntimeError("Malformed Wikidata SPARQL result")
    return bindings


def fetch_sparql_with_retry(
    endpoint: str,
    query: str,
    max_attempts: int = 5,
    base_wait: float = 1.5,
    request_timeout: int = 60,
    split_on_timeout: bool = False,
    deadline: float | None = None,
) -> dict:
    payload = _fetch_json_with_retry(
        endpoint,
        {"query": query, "format": "json"},
        request_timeout,
        max_attempts,
        base_wait,
        not split_on_timeout,
        deadline=deadline,
    )
    sparql_bindings(payload)
    return payload


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


def build_country_filtered_query(
    country_codes: list[str], artist_kind: str | None = None
) -> str:
    country_qids = [
        COUNTRY_QID_MAP[code] for code in country_codes if code in COUNTRY_QID_MAP
    ]
    if not country_qids:
        return SPARQL_QUERY_LEGACY

    person_pattern = """?item wdt:P31 wd:Q5 ;
          wdt:P27 ?country ;
          wdt:P106/wdt:P279* wd:Q639669 ."""
    group_pattern = """?item wdt:P31/wdt:P279* wd:Q215380 ;
          wdt:P495 ?country ."""
    if artist_kind == "person":
        pattern = person_pattern
    elif artist_kind == "group":
        pattern = group_pattern
    elif artist_kind is None:
        pattern = "{ " + person_pattern + " } UNION { " + group_pattern + " }"
    else:
        raise ValueError(f"Unknown artist kind: {artist_kind}")
    values = " ".join(f"wd:{qid}" for qid in country_qids)
    return f"""
SELECT ?item ?itemLabel (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases) WHERE {{
  VALUES ?country {{ {values} }}
  {pattern}
  OPTIONAL {{ ?item skos:altLabel ?alias . FILTER (lang(?alias) IN ("ja","en","ko")) }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja,en,ko,[AUTO_LANGUAGE],mul". }}
}}
GROUP BY ?item ?itemLabel
""".strip()


def occupation_batches(qids: list[str]) -> list[list[str]]:
    unique = sorted(set(qids))
    broad = [[q] for q in ("Q639669", "Q177220") if q in unique]
    rest = [q for q in unique if q not in {"Q639669", "Q177220"}]
    return broad + [
        rest[i : i + OCCUPATION_BATCH_SIZE]
        for i in range(0, len(rest), OCCUPATION_BATCH_SIZE)
    ]


def fetch_musician_occupations(
    request_timeout: int, deadline: float | None = None
) -> list[str]:
    payload = fetch_sparql_with_retry(
        SPARQL_ENDPOINT,
        MUSICIAN_OCCUPATIONS_QUERY,
        request_timeout=request_timeout,
        deadline=deadline,
    )
    qids = {
        _qid_from_uri(_value(row, "occupation")) for row in sparql_bindings(payload)
    }
    if not qids or any(not re.fullmatch(r"Q[1-9][0-9]*", q) for q in qids):
        raise RuntimeError("Invalid musician occupation set")
    return sorted(qids)


def build_id_query(
    countries: list[str],
    kind: str,
    occupations: list[str] | None = None,
    prefix: str = "",
    exact: bool = False,
) -> str:
    values = " ".join(f"wd:{COUNTRY_QID_MAP[c]}" for c in countries)
    restriction = f"VALUES ?item {{ wd:Q{prefix} }}" if exact else ""
    prefix_filter = (
        f'FILTER(STRSTARTS(STR(?item), "http://www.wikidata.org/entity/Q{prefix}"))'
        if prefix and not exact
        else ""
    )
    if kind == "person":
        if not occupations or any(
            not re.fullmatch(r"Q[1-9][0-9]*", q) for q in occupations
        ):
            raise ValueError("Explicit occupations required")
        occupation_values = " ".join(f"wd:{q}" for q in occupations)
        # Preserve the original human constraint. Filter a shard before joining occupations.
        pattern = f"""?item wdt:P27 ?country .
  {prefix_filter}
  VALUES ?occupation {{ {occupation_values} }}
  ?item wdt:P106 ?occupation ; wdt:P31 wd:Q5 ."""
    elif kind == "group":
        pattern = f"?item wdt:P495 ?country . {prefix_filter} ?item wdt:P31/wdt:P279* wd:Q215380 ."
    else:
        raise ValueError("Unknown artist kind")
    return f'SELECT DISTINCT ?item WHERE {{ hint:Query hint:optimizer "None" . VALUES ?country {{ {values} }} {restriction} {pattern} }}'


def fetch_artist_ids(
    countries: list[str],
    kind: str,
    occupations: list[str] | None,
    request_timeout: int,
    prefix: str = "",
    exact: bool = False,
    deadline: float | None = None,
) -> set[str]:
    if deadline is None:
        deadline = time.monotonic() + MAX_FETCH_SECONDS
    _check_deadline(deadline)
    query = build_id_query(countries, kind, occupations, prefix, exact)
    try:
        payload = fetch_sparql_with_retry(
            SPARQL_ENDPOINT,
            query,
            request_timeout=request_timeout,
            split_on_timeout=True,
            deadline=deadline,
        )
        qids = {_qid_from_uri(_value(row, "item")) for row in sparql_bindings(payload)}
        if any(not re.fullmatch(r"Q[1-9][0-9]*", q) for q in qids):
            raise RuntimeError("Invalid artist ID result")
        return qids
    except WikidataQueryTimeout:
        if exact or len(prefix) >= 12:
            raise
        if occupations and len(occupations) > 1:
            mid = len(occupations) // 2
            return fetch_artist_ids(
                countries,
                kind,
                occupations[:mid],
                request_timeout,
                prefix,
                deadline=deadline,
            ) | fetch_artist_ids(
                countries,
                kind,
                occupations[mid:],
                request_timeout,
                prefix,
                deadline=deadline,
            )
        # Decimal prefixes exhaust the QID namespace without a high-water cutoff.
        # Keep the exact prefix itself: Q1 is not in Q10* ... Q19*.
        found = (
            fetch_artist_ids(
                countries,
                kind,
                occupations,
                request_timeout,
                prefix,
                True,
                deadline=deadline,
            )
            if prefix
            else set()
        )
        for digit in "0123456789" if prefix else "123456789":
            found |= fetch_artist_ids(
                countries,
                kind,
                occupations,
                request_timeout,
                prefix + digit,
                deadline=deadline,
            )
        return found


def fetch_entity_rows(
    qids: set[str], request_timeout: int, deadline: float | None = None
) -> list[dict[str, object]]:
    if deadline is None:
        deadline = time.monotonic() + MAX_FETCH_SECONDS
    ordered = sorted(qids, key=lambda q: int(q[1:]))
    rows = []
    for start in range(0, len(ordered), 50):
        batch = ordered[start : start + 50]
        payload = _fetch_json_with_retry(
            API_ENDPOINT,
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "labels|aliases",
                "languages": "ja|en|ko|mul",
                "maxlag": 5,
            },
            request_timeout,
            deadline=deadline,
        )
        entities = payload.get("entities")
        if not isinstance(entities, dict):
            raise RuntimeError("Malformed entity result")
        for qid in batch:
            entity = entities.get(qid)
            if not isinstance(entity, dict) or "missing" in entity:
                raise RuntimeError(f"Missing requested entity: {qid}")
            labels, aliases = entity.get("labels"), entity.get("aliases")
            if not isinstance(labels, dict) or not isinstance(aliases, dict):
                raise RuntimeError(f"Malformed entity attributes: {qid}")
            names, alternate = [], []
            for language in ("ja", "en", "ko", "mul"):
                if language in labels:
                    label = labels[language]
                    if not isinstance(label, dict) or not isinstance(
                        label.get("value"), str
                    ):
                        raise RuntimeError(f"Malformed label: {qid}")
                    names.append(label["value"])
                    if language != "mul":
                        alternate.append(label["value"])
                # mul is a canonical-name fallback; legacy aliases use ja/en/ko.
                if language == "mul":
                    continue
                language_aliases = aliases.get(language, [])
                if not isinstance(language_aliases, list):
                    raise RuntimeError(f"Malformed aliases: {qid}")
                for alias in language_aliases:
                    if not isinstance(alias, dict) or not isinstance(
                        alias.get("value"), str
                    ):
                        raise RuntimeError(f"Malformed alias: {qid}")
                    alternate.append(alias["value"])
            canonical = next((n for n in names if n.strip()), qid)
            # Build directly rather than delimiting aliases: a name can contain '|'.
            row = build_seed_rows(
                {
                    "results": {
                        "bindings": [
                            {
                                "item": {
                                    "value": f"http://www.wikidata.org/entity/{qid}"
                                },
                                "itemLabel": {"value": canonical},
                            }
                        ]
                    }
                }
            )[0]
            row["aliases_json"] = json.dumps(
                sorted(set(alternate) - {canonical, ""}), ensure_ascii=False
            )
            rows.append(row)
        logger.info(
            "Fetched attributes: %d/%d IDs", min(start + 50, len(ordered)), len(ordered)
        )
    return sorted(rows, key=lambda row: str(row["canonical_name"]))


def validate_seed_size(rows: list[dict[str, object]], path: Path) -> None:
    existing = _load_existing_rows(path)
    degraded = [
        str(row["artist_id"])
        for row in rows
        if str(row["artist_id"]) in existing
        and existing[str(row["artist_id"])]["canonical_name"]
        not in {"", str(row["artist_id"]), str(row["artist_id"]).removeprefix("wd:")}
        and str(row.get("canonical_name", ""))
        in {str(row["artist_id"]), str(row["artist_id"]).removeprefix("wd:")}
    ]
    if degraded:
        raise RuntimeError(
            f"Artist name degradation guard: {len(degraded)} named IDs became QIDs"
        )
    fetched = {str(row["artist_id"]) for row in rows}
    minimum = max(1, math.ceil(len(existing) * MIN_SEED_ROW_RATIO))
    retained = fetched & existing.keys()
    missing_watch = {
        qid
        for qid, row in existing.items()
        if str(row.get("ticketjam_watch", "")).lower() in {"1", "true", "yes"}
    } - fetched
    if missing_watch:
        raise RuntimeError(
            f"Artist watch guard: {len(missing_watch)} watched IDs missing"
        )
    if len(fetched) < minimum or (existing and len(retained) < minimum):
        raise RuntimeError(
            f"Artist seed shrink/ID-loss guard: existing={len(existing)} fetched={len(fetched)} retained={len(retained)} minimum={minimum}"
        )


def fetch_seed_rows(
    country_codes: list[str], request_timeout: int, deadline: float | None = None
) -> list[dict[str, object]]:
    if deadline is None:
        deadline = time.monotonic() + MAX_FETCH_SECONDS
    _check_deadline(deadline)
    if "jp" not in country_codes:
        payload = fetch_sparql_with_retry(
            SPARQL_ENDPOINT,
            build_country_filtered_query(country_codes),
            request_timeout=request_timeout,
            deadline=deadline,
        )
        rows = build_seed_rows(payload)
        if not rows:
            raise RuntimeError("Wikidata returned no usable artists")
        return rows
    occupations = fetch_musician_occupations(request_timeout, deadline=deadline)
    qids = set()
    batches = occupation_batches(occupations)
    for index, batch in enumerate(batches, 1):
        qids |= fetch_artist_ids(
            country_codes, "person", batch, request_timeout, deadline=deadline
        )
        logger.info(
            "Fetched person IDs: batch=%d/%d unique=%d", index, len(batches), len(qids)
        )
    qids |= fetch_artist_ids(
        country_codes, "group", None, request_timeout, deadline=deadline
    )
    if not qids:
        raise RuntimeError("Wikidata returned no usable artists")
    return fetch_entity_rows(qids, request_timeout, deadline=deadline)


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
    deadline = time.monotonic() + MAX_FETCH_SECONDS
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    countries = [
        c.strip().lower() for c in str(args.countries).split(",") if c and c.strip()
    ]
    output_path = Path(args.output)
    rows = fetch_seed_rows(
        countries, max(10, int(args.request_timeout)), deadline=deadline
    )
    _check_deadline(deadline)
    validate_seed_size(rows, output_path)
    rows = stabilize_updated_at_with_existing(
        rows=rows,
        path=output_path,
        updated_at=date.today().strftime("%Y-%m-%d"),
    )
    _check_deadline(deadline)
    changed = write_seed_csv_noop(rows, output_path)
    ensure_manual_csv(MANUAL_PATH)

    if changed:
        logger.info("Wrote %d rows to %s", len(rows), output_path)
    else:
        logger.info("No changes in %s", output_path)


if __name__ == "__main__":
    main()

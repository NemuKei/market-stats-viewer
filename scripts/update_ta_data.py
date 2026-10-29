from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import openpyxl
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl.cell.rich_text import CellRichText, TextBlock

from scripts.stats_update_store import StatsUpdate, stats_update
from stats.ta import is_ta_summary_company

TA_SOURCE_INDEX_URL = (
    "https://www.mlit.go.jp/kankocho/tokei_hakusyo/ryokogyotoriatsukaigaku.html"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SQLITE_PATH = DATA_DIR / "market_stats.sqlite"
META_PATH = DATA_DIR / "meta_ta.json"
TABLE_NAME = "ta_company_amounts"
EXTRACTOR_VERSION = 5
TA_KEY_FIELDS = ("fiscal_year", "period", "company", "segment")
HIS_MAIN_SELECTION = "his-2026-03-main-table"
HIS_MAIN_KEY = ("2025", "2026-03", "エイチ・アイ・エス（6社計 ＊4）", "total")
HIS_SOURCE_URL = "https://www.mlit.go.jp/kankocho/content/002002289.xlsx"
HIS_SOURCE_SHA256 = "c01db7269370a8cd593e3d3bdb5f97d7aee11fb52a4df9c0be1cff0391595b67"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, CellRichText):
        # MLIT corrections retain the cancelled amount as a struck run in the
        # same cell. Preserve run boundaries until the cancelled text is gone.
        current = "".join(
            str(run) for run in value
            if not (isinstance(run, TextBlock) and run.font.strike)
        )
        if not current.strip():
            raise ValueError("Corrected amount has no uncancelled value")
        value = current
    if isinstance(value, bool):
        raise ValueError("Boolean amount is not numeric")
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = normalize_text(value)
        if not text or text in {"-", "－", "…"}:
            return None
        if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", text):
            raise ValueError(f"Unrecognised amount: {text!r}")
        amount = float(text.replace(",", ""))
    if not math.isfinite(amount):
        raise ValueError("Non-finite amount")
    return amount


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def fetch_html(url: str) -> str:
    res = requests.get(url, timeout=60)
    res.raise_for_status()
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding
    return res.text


def download_file(url: str, dst: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as res:
        res.raise_for_status()
        with dst.open("wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def parse_fiscal_year(text: str) -> str | None:
    m = re.search(r"\((20\d{2})年度\)", text)
    if m:
        return m.group(1)
    m = re.search(r"(20\d{2})年度", text)
    if m:
        return m.group(1)
    return None


def parse_period_from_link_text(link_text: str) -> str | None:
    text = normalize_text(link_text).replace(" ", "")
    if "総計" in text:
        return "total"
    m = re.search(r"(20\d{2})年.*?([0-9]{1,2})月", text)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        return f"{year:04d}-{month:02d}"
    return None


def extract_fiscal_page_links(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a"):
        href = normalize_text(a.get("href"))
        text = normalize_text(a.get_text())
        if not href:
            continue

        abs_url = urljoin(base_url, href)
        if "ryokogyotoriatsukaigaku" not in abs_url:
            continue
        if not abs_url.lower().endswith(".html"):
            continue
        if "年度" not in text and "_r" not in abs_url:
            continue
        if abs_url in seen:
            continue

        seen.add(abs_url)
        out.append({"url": abs_url, "link_text": text})

    if not out:
        raise RuntimeError("No fiscal-year TA pages were found.")

    def sort_key(item: dict[str, str]) -> tuple[int, str]:
        y = parse_fiscal_year(item["link_text"]) or "0"
        return int(y), item["url"]

    return sorted(out, key=sort_key, reverse=True)


def extract_ta_excel_links(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a"):
        href = normalize_text(a.get("href"))
        text = normalize_text(a.get_text())
        if not href:
            continue

        abs_url = urljoin(base_url, href)
        lower_url = abs_url.lower()
        if not (lower_url.endswith(".xlsx") or lower_url.endswith(".xls")):
            continue
        if "各社別内訳" not in text:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"url": abs_url, "link_text": text})

    return out


def classify_segment(header_text: str) -> str | None:
    compact = header_text.replace(" ", "").replace("　", "")
    if "外国人旅行" in compact:
        return "foreign"
    if "海外旅行" in compact:
        return "overseas"
    if "国内旅行" in compact:
        return "domestic"
    if "合計" in compact:
        return "total"
    return None


def find_amount_column(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    start_col: int,
    current_period_token: str,
    end_col: int,
    annual_layout: bool = False,
) -> int | None:
    # Older monthly and annual sheets label the current amount in row 5,
    # while row 6 contains only its unit. Comparative columns can themselves
    # contain "取扱額" in row 6, so select the explicit current header first.
    for c in range(start_col, end_col):
        header = re.sub(r"\s+", "", normalize_text(ws.cell(row=5, column=c).value))
        if header == "取扱額":
            return c

    for c in range(start_col, end_col):
        year_label = normalize_text(ws.cell(row=5, column=c).value)
        unit_label = normalize_text(ws.cell(row=6, column=c).value)
        if annual_layout:
            # Annual totals put both year and measure in row 5; never fall
            # back to the previous year or a neighbouring segment.
            if re.sub(r"\s+", "", year_label) == f"{current_period_token}年度取扱額":
                return c
            continue
        if "取扱額" not in unit_label:
            continue
        if year_label == current_period_token:
            return c
    return None


def normalize_company_name(name: str) -> str:
    out = re.sub(r"\s+", " ", name).strip()
    return out


def parse_ta_excel_rows(path: Path, fiscal_year: str, period: str) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False, rich_text=True)
    ws = wb[wb.sheetnames[0]]

    segment_starts: dict[str, int] = {}
    for c in range(1, min(ws.max_column, 40) + 1):
        header = normalize_text(ws.cell(row=4, column=c).value)
        segment = classify_segment(header)
        if segment and segment not in segment_starts:
            segment_starts[segment] = c

    if not segment_starts:
        raise ValueError("Segment headers were not detected in TA workbook.")

    company_header = re.sub(r"\s+", "", normalize_text(ws.cell(row=5, column=1).value))
    annual_layout = company_header == "会社名"
    company_col = 1 if annual_layout else 2
    current_period_token = (
        fiscal_year if annual_layout else normalize_text(ws.cell(row=5, column=3).value)
    )
    amount_cols: dict[str, int] = {}
    starts = sorted(segment_starts.values())
    for segment, start_col in segment_starts.items():
        index = starts.index(start_col)
        end_col = starts[index + 1] if index + 1 < len(starts) else ws.max_column + 1
        amount_col = find_amount_column(
            ws, start_col, current_period_token, end_col, annual_layout
        )
        if amount_col is not None:
            amount_cols[segment] = amount_col

    if len(amount_cols) != len(segment_starts):
        raise ValueError("Amount columns were not detected in TA workbook.")

    records: list[dict] = []
    for r in range(7, ws.max_row + 1):
        company_raw = normalize_text(ws.cell(row=r, column=company_col).value)
        if not company_raw:
            continue
        if re.sub(r"\s+", "", company_raw) == "会社名":
            continue
        if is_ta_summary_company(company_raw) or "参考値" in company_raw:
            continue

        company = normalize_company_name(company_raw)
        for segment, col in amount_cols.items():
            cell = ws.cell(row=r, column=col)
            try:
                if cell.value is not None and cell.font.strike:
                    raise ValueError("Amount cell is cancelled without a replacement")
                amount = to_float(cell.value)
            except ValueError as exc:
                raise ValueError(f"Invalid TA amount at {ws.title}!{cell.coordinate}: {exc}") from exc
            if amount is None:
                continue
            records.append(
                {
                    "fiscal_year": fiscal_year,
                    "period": period,
                    "company": company,
                    "segment": segment,
                    "amount": amount,
                }
            )

    wb.close()
    return records


def resolve_ta_records(
    records: list[dict], *, duplicate_selection: str | None = None
) -> list[dict]:
    """Merge equal values; reject conflicts unless the caller explicitly selects
    the narrowly pinned HIS proposal. Input order never chooses the value.
    """
    if duplicate_selection not in (None, HIS_MAIN_SELECTION):
        raise ValueError("Unknown TA duplicate selection")
    groups: dict[tuple[str, ...], list[dict]] = {}
    for row in records:
        key = tuple(str(row[field]) for field in TA_KEY_FIELDS)
        amount = row["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            raise ValueError(f"Invalid TA amount for {key}")
        groups.setdefault(key, []).append(row)
    result = []
    for key, rows in sorted(groups.items()):
        amounts = {float(row["amount"]) for row in rows}
        if len(amounts) == 1:
            amount = next(iter(amounts))
        elif (
            duplicate_selection == HIS_MAIN_SELECTION
            and key == HIS_MAIN_KEY
            and amounts == {38188442.0, 38188444.0}
            and all(row.get("_source_sha256") == HIS_SOURCE_SHA256
                    and row.get("_source_url") == HIS_SOURCE_URL for row in rows)
        ):
            amount = 38188442.0
        else:
            raise ValueError(f"Conflicting TA duplicate: {key} amounts={sorted(amounts)}")
        result.append(dict(zip(TA_KEY_FIELDS, key)) | {"amount": amount})
    return result


def ta_payload_sha256(payload: list[dict]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def ta_changes(before: list[dict], after: list[dict]) -> list[dict]:
    def index(rows: list[dict]) -> dict:
        return {tuple(str(row[field]) for field in TA_KEY_FIELDS): float(row["amount"]) for row in rows}
    old, new = index(before), index(after)
    changes = []
    for key in sorted(old.keys() | new.keys()):
        if key in old and key in new and old[key] == new[key]:
            continue
        kind = "added" if key not in old else "removed" if key not in new else "changed"
        changes.append(dict(zip(TA_KEY_FIELDS, key)) | {
            "change": kind, "before_amount": old.get(key), "after_amount": new.get(key)
        })
    return changes


def validate_approved_preview(
    preview: dict, sources: list[dict], rows: list[dict], duplicate_selection: str | None
) -> None:
    """Bind a future application to the reviewed baseline, all sources and every
    resulting row/change. Reading this manifest is not itself user approval.
    """
    if (preview.get("schema_version") != 1
            or preview.get("extractor_version") != EXTRACTOR_VERSION
            or preview.get("duplicate_selection") != duplicate_selection):
        raise ValueError("TA approval preview policy/version mismatch")
    for path, field in ((SQLITE_PATH, "database_sha256"), (META_PATH, "metadata_sha256")):
        if sha256_file(path) != preview.get(field):
            raise ValueError(f"TA approval preview baseline mismatch: {path.name}")
    expected = preview.get("sources", [])
    actual_sources = sorted((row["excel_url"], row["sha256"]) for row in sources)
    expected_sources = sorted((row["excel_url"], row["sha256"]) for row in expected)
    if not actual_sources or actual_sources != expected_sources:
        raise ValueError("TA approval preview source set/hash mismatch")
    if ta_payload_sha256(rows) != preview.get("resolved_rows_sha256"):
        raise ValueError("TA approval preview rows mismatch")
    with sqlite3.connect(SQLITE_PATH.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        before = [dict(zip((*TA_KEY_FIELDS, "amount"), row)) for row in conn.execute(
            f"SELECT fiscal_year, period, company, segment, amount FROM {TABLE_NAME}"
        )]
    if ta_payload_sha256(ta_changes(before, rows)) != preview.get("changes_sha256"):
        raise ValueError("TA approval preview changes mismatch")


def build_sqlite(df: pd.DataFrame, sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(sqlite_path)) as conn:
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_period "
            f"ON {TABLE_NAME}(fiscal_year, period)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_segment "
            f"ON {TABLE_NAME}(segment)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_company "
            f"ON {TABLE_NAME}(company)"
        )


def build_signature(excel_hashes: list[dict[str, str]]) -> str:
    by_url = {item["excel_url"]: item["sha256"] for item in excel_hashes}
    payload = "\n".join(f"{url}|{by_url[url]}" for url in sorted(by_url))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_usable_ta_table(sqlite_path: Path) -> bool:
    if not sqlite_path.is_file():
        return False
    try:
        with sqlite3.connect(
            f"{sqlite_path.resolve().as_uri()}?mode=ro", uri=True
        ) as conn:
            return (
                conn.execute(
                    f"SELECT fiscal_year, period, company, segment, amount "
                    f"FROM {TABLE_NAME} LIMIT 1"
                ).fetchone()
                is not None
            )
    except sqlite3.DatabaseError:
        return False


def main(*, duplicate_selection: str | None = None, approved_preview: Path | None = None) -> int:
    preview = None
    if approved_preview is not None:
        preview = json.loads(approved_preview.read_text(encoding="utf-8"))
        if not isinstance(preview, dict):
            raise ValueError("TA approval preview must be a JSON object")
    with stats_update(SQLITE_PATH) as update:
        return _main(update, duplicate_selection=duplicate_selection, preview=preview)


def _main(update: StatsUpdate, *, duplicate_selection: str | None = None, preview: dict | None = None) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    index_html = fetch_html(TA_SOURCE_INDEX_URL)
    fiscal_pages = extract_fiscal_page_links(index_html, TA_SOURCE_INDEX_URL)
    old_meta = load_meta()

    all_records: list[dict] = []
    processed_files: list[dict] = []

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        file_counter = 0
        fetched_excel_hashes: list[dict[str, str]] = []
        fetched_excel_files: list[dict[str, str]] = []

        for page in fiscal_pages:
            page_url = page["url"]
            page_html = fetch_html(page_url)
            page_soup = BeautifulSoup(page_html, "html.parser")
            page_title = (
                normalize_text(page_soup.title.get_text())
                if page_soup.title is not None
                else ""
            )

            fiscal_year = (
                parse_fiscal_year(page["link_text"])
                or parse_fiscal_year(page_title)
                or ""
            )

            excel_links = extract_ta_excel_links(page_html, page_url)
            for link in excel_links:
                ext = Path(urlparse(link["url"]).path).suffix.lower() or ".xlsx"
                local_path = tmp_dir / f"ta_{file_counter:04d}{ext}"
                file_counter += 1

                download_file(link["url"], local_path)
                source_sha256 = sha256_file(local_path)
                period = parse_period_from_link_text(link["link_text"]) or ""

                fetched_excel_hashes.append(
                    {
                        "excel_url": link["url"],
                        "sha256": source_sha256,
                    }
                )
                fetched_excel_files.append(
                    {
                        "page_url": page_url,
                        "excel_url": link["url"],
                        "excel_link_text": link["link_text"],
                        "sha256": source_sha256,
                        "fiscal_year": fiscal_year,
                        "period": period,
                        "ext": ext,
                        "local_path": str(local_path),
                    }
                )

        if not fetched_excel_hashes:
            raise RuntimeError("No TA source Excel files were downloaded.")

        for item in fetched_excel_files:
            if not item["fiscal_year"]:
                raise RuntimeError(
                    f"TA source fiscal year unknown: {item['excel_url']}"
                )
            if not item["period"]:
                raise RuntimeError(
                    f"TA source period unknown: {item['excel_url']} "
                    f"({item['excel_link_text']})"
                )
            if item["ext"] == ".xls":
                raise RuntimeError(
                    f"TA source format unsupported (.xls): {item['excel_url']}"
                )

        signature = build_signature(fetched_excel_hashes)
        if (
            preview is None
            and old_meta.get("duplicate_selection") == duplicate_selection
            and old_meta.get("signature") == signature
            and old_meta.get("extractor_version") == EXTRACTOR_VERSION
            and has_usable_ta_table(SQLITE_PATH)
        ):
            print("No change: source Excel signature unchanged.")
            return 0

        for item in fetched_excel_files:
            fiscal_year = item["fiscal_year"]
            period = item["period"]
            link_url = item["excel_url"]
            local_path = Path(item["local_path"])
            source_sha256 = item["sha256"]

            try:
                parsed = parse_ta_excel_rows(
                    path=local_path,
                    fiscal_year=fiscal_year,
                    period=period,
                )
            except Exception as e:
                raise RuntimeError(f"TA source parse failed: {link_url} ({e})") from e

            if not parsed:
                raise RuntimeError(f"TA source has no company rows: {link_url}")

            all_records.extend(row | {"_source_sha256": source_sha256, "_source_url": link_url}
                               for row in parsed)
            processed_files.append(
                {
                    "page_url": item["page_url"],
                    "excel_url": link_url,
                    "excel_link_text": item["excel_link_text"],
                    "sha256": source_sha256,
                    "fiscal_year": fiscal_year,
                    "period": period,
                    "rows": len(parsed),
                }
            )
            print(
                f"Parsed TA file: fiscal_year={fiscal_year} period={period} "
                f"rows={len(parsed)}"
            )

    if not all_records:
        raise RuntimeError("No TA rows were parsed from source pages.")

    resolved = resolve_ta_records(all_records, duplicate_selection=duplicate_selection)
    if preview is not None:
        validate_approved_preview(preview, fetched_excel_hashes, resolved, duplicate_selection)
    df = pd.DataFrame(resolved)
    df["fiscal_year"] = df["fiscal_year"].astype(str)
    df["period"] = df["period"].astype(str)
    df["company"] = df["company"].astype(str)
    df["segment"] = df["segment"].astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="raise")

    def period_sort_value(value: str) -> tuple[int, int]:
        if value == "total":
            return 0, 0
        m = re.fullmatch(r"(\d{4})-(\d{2})", value)
        if m:
            return int(m.group(1)), int(m.group(2))
        return 9999, 99

    df["_period_sort_year"] = df["period"].map(lambda p: period_sort_value(p)[0])
    df["_period_sort_month"] = df["period"].map(lambda p: period_sort_value(p)[1])
    df = df.sort_values(
        ["fiscal_year", "_period_sort_year", "_period_sort_month", "segment", "company"]
    ).drop(columns=["_period_sort_year", "_period_sort_month"])
    df = df.reset_index(drop=True)


    meta = {
        "source_index_url": TA_SOURCE_INDEX_URL,
        "signature": signature,
        "extractor_version": EXTRACTOR_VERSION,
        "duplicate_selection": duplicate_selection,
        "last_checked_at": now_utc_iso(),
        "processed_files": processed_files,
        "row_count": int(len(df)),
        "fiscal_years": sorted(df["fiscal_year"].unique().tolist(), reverse=True),
        "periods": sorted(df["period"].unique().tolist()),
        "segments": sorted(df["segment"].unique().tolist()),
        "unit": "thousand_yen",
    }
    if preview is not None:
        # Recheck immediately before the recoverable DB/meta save as well.
        validate_approved_preview(preview, fetched_excel_hashes, resolved, duplicate_selection)
    update.save(META_PATH, meta, lambda path: build_sqlite(df, path))

    print(
        f"Updated {TABLE_NAME}: rows={len(df)} files={len(processed_files)} "
        f"fiscal_years={len(meta['fiscal_years'])}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh TA statistics; explicit selections require prior user approval.")
    parser.add_argument("--duplicate-selection", choices=[HIS_MAIN_SELECTION], default=None)
    parser.add_argument("--approved-preview", type=Path, help="Reviewed preview manifest to verify before writing")
    args = parser.parse_args()
    raise SystemExit(main(duplicate_selection=args.duplicate_selection, approved_preview=args.approved_preview))

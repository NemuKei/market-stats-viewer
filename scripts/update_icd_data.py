from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

ICD_SOURCE_PAGE_URL = "https://www.mlit.go.jp/kankocho/tokei_hakusyo/gaikokujinshohidoko.html"

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SQLITE_PATH = DATA_DIR / "market_stats.sqlite"
META_PATH = DATA_DIR / "meta_icd.json"

SPEND_TABLE_NAME = "icd_spend_items"
ENTRY_TABLE_NAME = "icd_entry_port_summary"

SPEND_SHEET_TARGETS = [
    ("参考2", "all"),
    ("参考10", "leisure"),
]
ENTRY_METRIC_SHEET_TARGETS = [
    ("表4-1", "all", "avg_nights"),
    ("参考1", "all", "spend_yen"),
    ("参考7", "leisure", "avg_nights"),
    ("参考9", "leisure", "spend_yen"),
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = normalize_text(value).replace(",", "")
    if not s or s in {"-", "－", "…"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_html(url: str) -> str:
    res = requests.get(url, timeout=60)
    res.raise_for_status()
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding
    return res.text


def save_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def download_file(url: str, dst: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as res:
        res.raise_for_status()
        with dst.open("wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def extract_latest_icd_excel_link(html: str, base_url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a"):
        href = normalize_text(a.get("href"))
        text = normalize_text(a.get_text())
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        lower = abs_url.lower()
        if not (lower.endswith(".xls") or lower.endswith(".xlsx")):
            continue
        if "集計表" not in text:
            continue
        if "都道府県" in text:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        candidates.append((abs_url, text))

    if not candidates:
        raise RuntimeError("ICD source page did not include target 集計表 Excel links.")

    return candidates[0]


def excel_engine(path: Path) -> str | None:
    if path.suffix.lower() == ".xls":
        return "xlrd"
    return None


def parse_period_metadata(text: str) -> tuple[str, str, str]:
    normalized = (
        text.replace("〜", "-")
        .replace("～", "-")
        .replace("－", "-")
        .replace(" ", "")
    )

    release_match = re.search(r"【([^】]+)】", normalized)
    release_type = release_match.group(1) if release_match else ""

    m_quarter = re.search(r"(20\d{2})年([0-9]{1,2})-([0-9]{1,2})月期", normalized)
    if m_quarter:
        year = int(m_quarter.group(1))
        start_month = int(m_quarter.group(2))
        end_month = int(m_quarter.group(3))
        quarter = (start_month - 1) // 3 + 1
        period_label = f"{year}年{start_month}-{end_month}月期"
        period_key = f"{year}Q{quarter}"
        return period_label, period_key, release_type

    m_annual = re.search(r"(20\d{2})年年間", normalized)
    if m_annual:
        year = m_annual.group(1)
        period_label = f"{year}年年間"
        period_key = str(year)
        return period_label, period_key, release_type

    raise ValueError(f"Failed to parse period metadata from: {text}")


def detect_period_metadata_from_df(df: pd.DataFrame) -> tuple[str, str, str]:
    max_row = min(len(df), 15)
    max_col = min(df.shape[1], 8)
    for r in range(max_row):
        for c in range(max_col):
            text = normalize_text(df.iat[r, c])
            if "年" not in text:
                continue
            if "期" not in text and "年間" not in text:
                continue
            try:
                return parse_period_metadata(text)
            except ValueError:
                continue
    raise ValueError("Failed to detect ICD period metadata from workbook.")


def find_sheet_name(sheet_names: list[str], keyword: str) -> str | None:
    for name in sheet_names:
        if keyword in normalize_text(name):
            return name
    return None


def find_header_row(df: pd.DataFrame, marker: str = "調査項目") -> int:
    max_row = min(len(df), 30)
    max_col = min(df.shape[1], 8)
    for r in range(max_row):
        for c in range(max_col):
            if marker in normalize_text(df.iat[r, c]):
                return r
    raise ValueError(f"Header marker '{marker}' not found.")


def extract_nationality_pairs(
    df: pd.DataFrame,
    header_row: int,
    expected_left_label: str,
    expected_right_label: str | None = None,
) -> list[tuple[str, int, int]]:
    unit_row = header_row + 1
    pairs: list[tuple[str, int, int]] = []
    seen: set[str] = set()

    for c in range(df.shape[1] - 1):
        nationality = normalize_text(df.iat[header_row, c])
        if not nationality or "調査項目" in nationality or nationality in seen:
            continue

        left_label = normalize_text(df.iat[unit_row, c])
        right_label = normalize_text(df.iat[unit_row, c + 1])
        if expected_left_label not in left_label:
            continue
        if expected_right_label is not None and expected_right_label not in right_label:
            continue
        if not right_label:
            continue

        pairs.append((nationality, c, c + 1))
        seen.add(nationality)

    if not pairs:
        raise ValueError("Nationality columns were not detected.")

    return pairs


def parse_spend_sheet(
    df: pd.DataFrame,
    purpose: str,
    period_label: str,
    period_key: str,
    release_type: str,
) -> pd.DataFrame:
    header_row = find_header_row(df, marker="調査項目")
    pairs = extract_nationality_pairs(
        df,
        header_row=header_row,
        expected_left_label="消費単価",
        expected_right_label="構成比",
    )

    group_ignore = {"", "【A1】", "（単一回答）", "（複数回答）", "費目別支出"}
    current_group = ""
    records: list[dict] = []

    for r in range(header_row + 2, len(df)):
        col1 = normalize_text(df.iat[r, 1]) if df.shape[1] > 1 else ""
        col2 = normalize_text(df.iat[r, 2]) if df.shape[1] > 2 else ""
        col3 = normalize_text(df.iat[r, 3]) if df.shape[1] > 3 else ""

        if (
            col1
            and col1 not in group_ignore
            and "全体" not in col1
            and "注" not in col1
            and "調査項目" not in col1
        ):
            current_group = col1

        item = col3 or col2
        if not item or item in {"-", "－", "…"}:
            continue
        if "全体" in item or "注" in item:
            continue

        item_group = current_group or "その他"

        for nationality, spend_col, share_col in pairs:
            spend_yen = to_float(df.iat[r, spend_col])
            share_pct = to_float(df.iat[r, share_col])
            if spend_yen is None and share_pct is None:
                continue

            records.append(
                {
                    "period_label": period_label,
                    "period_key": period_key,
                    "release_type": release_type,
                    "purpose": purpose,
                    "nationality": nationality,
                    "item_group": item_group,
                    "item": item,
                    "spend_yen": spend_yen,
                    "share_pct": share_pct,
                }
            )

    return pd.DataFrame(records)


def parse_entry_metric_sheet(
    df: pd.DataFrame,
    purpose: str,
    metric_name: str,
    period_label: str,
    period_key: str,
    release_type: str,
) -> pd.DataFrame:
    header_row = find_header_row(df, marker="調査項目")
    pairs = extract_nationality_pairs(
        df,
        header_row=header_row,
        expected_left_label="回答数",
        expected_right_label=None,
    )

    records: list[dict] = []
    current_port_type: str | None = None
    skip_labels = {"【A1】", "（単一回答）", "（複数回答）"}

    for r in range(header_row + 2, len(df)):
        col1 = normalize_text(df.iat[r, 1]) if df.shape[1] > 1 else ""
        col2 = normalize_text(df.iat[r, 2]) if df.shape[1] > 2 else ""

        if "入国空港" in col1:
            current_port_type = "entry"
        if "出国空港" in col1:
            current_port_type = "exit"
        if "滞在日数" in col1:
            current_port_type = None

        port_labels: list[tuple[str, str]] = []
        if "全体" in col1 and "【A1】" in col1:
            # 全体行は入国/出国どちらの集計にも使えるため両方に展開する。
            port_labels = [("entry", "全体"), ("exit", "全体")]
        elif (
            current_port_type in {"entry", "exit"}
            and col2
            and col2 not in skip_labels
            and ("空港" in col2 or "港" in col2 or col2 == "その他")
        ):
            port_labels = [(str(current_port_type), col2)]

        if not port_labels:
            continue

        for port_type, entry_port in port_labels:
            for nationality, respondents_col, metric_col in pairs:
                respondents = to_float(df.iat[r, respondents_col])
                metric_value = to_float(df.iat[r, metric_col])
                if respondents is None and metric_value is None:
                    continue

                records.append(
                    {
                        "period_label": period_label,
                        "period_key": period_key,
                        "release_type": release_type,
                        "purpose": purpose,
                        "port_type": port_type,
                        "entry_port": entry_port,
                        "nationality": nationality,
                        "respondents": respondents,
                        metric_name: metric_value,
                    }
                )

    return pd.DataFrame(records)


def merge_entry_metrics(df_avg: pd.DataFrame, df_spend: pd.DataFrame) -> pd.DataFrame:
    key_cols = [
        "period_label",
        "period_key",
        "release_type",
        "purpose",
        "port_type",
        "entry_port",
        "nationality",
    ]

    if df_avg.empty and df_spend.empty:
        return pd.DataFrame(
            columns=key_cols
            + ["respondents", "spend_yen", "avg_nights", "spend_per_night_yen"]
        )

    merged = df_avg.merge(df_spend, on=key_cols, how="outer", suffixes=("_avg", "_spend"))
    merged["respondents"] = merged["respondents_avg"].combine_first(
        merged["respondents_spend"]
    )
    merged["avg_nights"] = merged["avg_nights"]
    merged["spend_yen"] = merged["spend_yen"]
    merged["spend_per_night_yen"] = merged.apply(
        lambda row: (
            row["spend_yen"] / row["avg_nights"]
            if pd.notna(row["spend_yen"])
            and pd.notna(row["avg_nights"])
            and float(row["avg_nights"]) > 0
            else None
        ),
        axis=1,
    )

    out_cols = key_cols + ["respondents", "spend_yen", "avg_nights", "spend_per_night_yen"]
    out = merged[out_cols].copy()
    return out.sort_values(key_cols).reset_index(drop=True)


def build_sqlite(spend_df: pd.DataFrame, entry_df: pd.DataFrame, sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(sqlite_path)) as conn:
        spend_df.to_sql(SPEND_TABLE_NAME, conn, if_exists="replace", index=False)
        entry_df.to_sql(ENTRY_TABLE_NAME, conn, if_exists="replace", index=False)

        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{SPEND_TABLE_NAME}_period "
            f"ON {SPEND_TABLE_NAME}(period_key, purpose)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{SPEND_TABLE_NAME}_nat "
            f"ON {SPEND_TABLE_NAME}(nationality, item)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{ENTRY_TABLE_NAME}_period "
            f"ON {ENTRY_TABLE_NAME}(period_key, purpose)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{ENTRY_TABLE_NAME}_port "
            f"ON {ENTRY_TABLE_NAME}(port_type, entry_port, nationality)"
        )


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    html = fetch_html(ICD_SOURCE_PAGE_URL)
    excel_url, excel_link_text = extract_latest_icd_excel_link(html, ICD_SOURCE_PAGE_URL)

    with tempfile.TemporaryDirectory() as td:
        filename = Path(urlparse(excel_url).path).name or "icd_source.xls"
        tmp_excel = Path(td) / filename
        download_file(excel_url, tmp_excel)
        source_sha256 = sha256_file(tmp_excel)
        old_meta = load_meta()
        if old_meta.get("source_excel_sha256") == source_sha256:
            print("No change: source Excel hash unchanged.")
            return 0

        period_label = ""
        period_key = ""
        release_type = ""

        spend_parts: list[pd.DataFrame] = []
        avg_parts: list[pd.DataFrame] = []
        spend_metric_parts: list[pd.DataFrame] = []
        used_sheets: dict[str, list[str]] = {"spend_items": [], "entry_metrics": []}

        with pd.ExcelFile(tmp_excel, engine=excel_engine(tmp_excel)) as book:
            for sheet_name, purpose in SPEND_SHEET_TARGETS:
                actual_sheet = find_sheet_name(book.sheet_names, sheet_name)
                if actual_sheet is None:
                    continue
                df_sheet = pd.read_excel(book, sheet_name=actual_sheet, header=None)
                if not period_label:
                    period_label, period_key, release_type = detect_period_metadata_from_df(
                        df_sheet
                    )
                spend_parts.append(
                    parse_spend_sheet(
                        df_sheet,
                        purpose=purpose,
                        period_label=period_label,
                        period_key=period_key,
                        release_type=release_type,
                    )
                )
                used_sheets["spend_items"].append(actual_sheet)

            for sheet_name, purpose, metric_name in ENTRY_METRIC_SHEET_TARGETS:
                actual_sheet = find_sheet_name(book.sheet_names, sheet_name)
                if actual_sheet is None:
                    continue
                df_sheet = pd.read_excel(book, sheet_name=actual_sheet, header=None)
                if not period_label:
                    period_label, period_key, release_type = detect_period_metadata_from_df(
                        df_sheet
                    )
                parsed = parse_entry_metric_sheet(
                    df_sheet,
                    purpose=purpose,
                    metric_name=metric_name,
                    period_label=period_label,
                    period_key=period_key,
                    release_type=release_type,
                )
                if metric_name == "avg_nights":
                    avg_parts.append(parsed)
                elif metric_name == "spend_yen":
                    spend_metric_parts.append(parsed)
                used_sheets["entry_metrics"].append(actual_sheet)

        if not period_label or not period_key:
            raise RuntimeError("ICD period metadata could not be detected.")

        spend_df = (
            pd.concat(spend_parts, ignore_index=True)
            if spend_parts
            else pd.DataFrame(
                columns=[
                    "period_label",
                    "period_key",
                    "release_type",
                    "purpose",
                    "nationality",
                    "item_group",
                    "item",
                    "spend_yen",
                    "share_pct",
                ]
            )
        )
        avg_df = pd.concat(avg_parts, ignore_index=True) if avg_parts else pd.DataFrame()
        spend_metric_df = (
            pd.concat(spend_metric_parts, ignore_index=True)
            if spend_metric_parts
            else pd.DataFrame()
        )
        entry_df = merge_entry_metrics(avg_df, spend_metric_df)

        if spend_df.empty:
            raise RuntimeError("ICD spend items could not be parsed from target sheets.")
        if entry_df.empty:
            raise RuntimeError("ICD entry port summary could not be parsed from target sheets.")

        build_sqlite(spend_df, entry_df, SQLITE_PATH)

        meta = {
            "source_page_url": ICD_SOURCE_PAGE_URL,
            "source_excel_url": excel_url,
            "source_excel_link_text": excel_link_text,
            "source_excel_filename": filename,
            "source_excel_sha256": source_sha256,
            "fetched_at_utc": now_utc_iso(),
            "period_label": period_label,
            "period_key": period_key,
            "release_type": release_type,
            "sheets_used": used_sheets,
            "row_counts": {
                SPEND_TABLE_NAME: int(len(spend_df)),
                ENTRY_TABLE_NAME: int(len(entry_df)),
            },
        }
        save_meta(meta)

        print(
            f"Updated ICD data: spend_rows={len(spend_df)} "
            f"entry_rows={len(entry_df)} period={period_key} release={release_type}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

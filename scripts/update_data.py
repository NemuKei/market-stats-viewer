from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

try:
    from .parse_ts_table import build_raw_from_three_sheets
except ImportError:  # pragma: no cover - fallback for direct script execution
    from parse_ts_table import build_raw_from_three_sheets

# 取得元（観光庁：宿泊旅行統計調査）
SOURCE_PAGE_URL = "https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html"

# 推移表Excel（リンクが固定名のケースに強くする）
PREFERRED_XLSX_NAME_HINT = "001912060.xlsx"

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
META_PATH = DATA_DIR / "meta.json"
SQLITE_PATH = DATA_DIR / "market_stats.sqlite"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_ts_table_xlsx_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        text = (a.get_text() or "").strip()
        abs_url = urljoin(base_url, href)
        if abs_url.lower().endswith(".xlsx"):
            links.append((abs_url, text))

    if not links:
        raise RuntimeError(
            "No .xlsx links found on source page (HTML structure may have changed)."
        )

    # 1) ファイル名ヒント一致
    for url, _ in links:
        if PREFERRED_XLSX_NAME_HINT in url:
            return url

    # 2) アンカーテキストに「推移表」っぽい語
    for url, text in links:
        if "推移表" in text:
            return url

    # 3) 最初のxlsx（最後の砦）
    return links[0][0]


def load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def save_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def download_file(url: str, dst: Path, timeout_sec: int = 60) -> None:
    with requests.get(url, stream=True, timeout=timeout_sec) as r:
        r.raise_for_status()
        with dst.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def build_sqlite(df: pd.DataFrame, sqlite_path: Path) -> None:
    import sqlite3

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(sqlite_path)) as conn:
        df.to_sql("market_stats", conn, if_exists="replace", index=False)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_stats_ym ON market_stats(ym)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_stats_pref ON market_stats(pref_code)"
        )


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    html = requests.get(SOURCE_PAGE_URL, timeout=60).text
    xlsx_url = find_ts_table_xlsx_url(html, SOURCE_PAGE_URL)

    with tempfile.TemporaryDirectory() as td:
        tmp_xlsx = Path(td) / "ts_table.xlsx"
        download_file(xlsx_url, tmp_xlsx)

        fetched_sha = sha256_file(tmp_xlsx)
        meta = load_meta()
        if meta.get("source_sha256") == fetched_sha:
            print("No change: source file hash unchanged.")
            return 0

        wb = load_workbook(tmp_xlsx, read_only=False, data_only=True)
        # 推移表の想定シート（今回MVPはこの3つに固定）
        ws_total = wb["1-2"]
        ws_jp = wb["2-2"]
        ws_foreign = wb["3-2"]

        df = build_raw_from_three_sheets(
            ws_total=ws_total,
            ws_jp=ws_jp,
            ws_foreign=ws_foreign,
            make_national_sum=True,
        )

        # 型整形
        df["ym"] = df["ym"].astype(str)
        df["pref_code"] = df["pref_code"].astype(str)
        df["pref_name"] = df["pref_name"].astype(str)

        build_sqlite(df, SQLITE_PATH)

        now = datetime.now(timezone.utc).isoformat()
        new_meta = {
            "source_page_url": SOURCE_PAGE_URL,
            "source_xlsx_url": xlsx_url,
            "source_sha256": fetched_sha,
            "fetched_at_utc": now,
            "rows": int(len(df)),
            "min_ym": str(df["ym"].min()),
            "max_ym": str(df["ym"].max()),
        }
        save_meta(new_meta)

        print(f"Updated: rows={len(df)} ym={new_meta['min_ym']}..{new_meta['max_ym']}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

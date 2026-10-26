from openpyxl import Workbook

import pandas as pd
import pytest

from scripts import update_data as updater

from scripts.update_data import find_monthly_sheet_name, find_ts_table_xlsx_url


def test_find_ts_table_xlsx_url_prefers_pushi_hyo_link() -> None:
    html = """
    <html>
      <body>
        <a href="/content/001992573.xlsx">2026年2月分（第1次速報値）集計結果</a>
        <a href="/content/001992670.xlsx">推移表［Excel:1.3MB］</a>
      </body>
    </html>
    """

    url = find_ts_table_xlsx_url(
        html,
        "https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html",
    )

    assert url == "https://www.mlit.go.jp/content/001992670.xlsx"


def test_find_monthly_sheet_name_ignores_old_sheets() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "1-1"
    wb.create_sheet("旧1-1")
    wb.create_sheet("旧1-2")
    wb.create_sheet("2-2")
    wb.create_sheet("4-1")

    assert find_monthly_sheet_name(wb, "1") == "1-1"
    assert find_monthly_sheet_name(wb, "1", legacy=True) == "旧1-2"
    assert find_monthly_sheet_name(wb, "2") == "2-2"
    assert find_monthly_sheet_name(wb, "4") == "4-1"


def test_second_table_failure_preserves_both_tables_and_metadata(tmp_path, monkeypatch):
    db = tmp_path / "market_stats.sqlite"
    meta = tmp_path / "meta.json"
    old_market = pd.DataFrame([{"ym": "2024-01", "pref_code": "00", "pref_name": "全国"}])
    old_facility = old_market.assign(facility_type="hotel", occupancy_rate=50.0)
    updater.build_sqlite(old_market, old_facility, db)
    meta.write_text('{"source_sha256":"old"}', encoding="utf-8")
    before = db.read_bytes(), meta.read_bytes()
    monkeypatch.setattr(updater, "DATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "SQLITE_PATH", db)
    monkeypatch.setattr(updater, "META_PATH", meta)
    monkeypatch.setattr(updater, "fetch_html_text", lambda *a, **k: '<a href="new.xlsx">推移表</a>')
    monkeypatch.setattr(updater, "download_file", lambda url, dst: dst.write_bytes(b"source"))
    monkeypatch.setattr(updater, "load_workbook", lambda *a, **k: Workbook())
    monkeypatch.setattr(updater, "build_market_stats_from_workbook", lambda wb: old_market.assign(ym="2025-01"))
    monkeypatch.setattr(updater, "build_facility_occupancy_from_workbook", lambda wb: old_facility.assign(ym="2025-01"))
    to_sql = pd.DataFrame.to_sql

    def fail_second_table(frame, name, *args, **kwargs):
        if name == updater.STAY_FACILITY_OCCUPANCY_TABLE_NAME:
            raise OSError("injected second table failure")
        return to_sql(frame, name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(pd.DataFrame, "to_sql", fail_second_table)
        with pytest.raises(OSError, match="injected second table"):
            updater.main()

    assert (db.read_bytes(), meta.read_bytes()) == before
    assert updater.main() == 0
    import sqlite3
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT ym FROM market_stats").fetchall() == [("2025-01",)]
        assert conn.execute("SELECT ym FROM stay_facility_occupancy").fetchall() == [("2025-01",)]

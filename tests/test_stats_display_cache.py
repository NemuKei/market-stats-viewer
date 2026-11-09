"""Statistics refresh without clearing an already-warmed Streamlit cache."""

import os
import sqlite3

import pandas as pd
import pytest
import streamlit as st

import app


LOADERS = [
    (app.load_data, "market_stats", "ym"),
    (app.load_stay_facility_occupancy_data, "stay_facility_occupancy", "ym"),
    (app.load_tcd_data, "tcd_stay_nights", "period_key"),
    (app.load_icd_spend_data, "icd_spend_items", "period_key"),
    (app.load_icd_entry_data, "icd_entry_port_summary", "period_key"),
    (app.load_ta_data, "ta_company_amounts", "period"),
    (app.load_airport_volume_data, "airport_arrivals_monthly", "period_key"),
]


@pytest.fixture(autouse=True)
def isolated_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def write_database(path, table, period_column, month):
    # Synthetic rows include the fields required by all seven loaders.
    row = {
        period_column: month,
        "pref_code": "01",
        "facility_type": "旅館",
        "occupancy_rate": 75.0,
        "company": "会社A",
        "segment": "total",
        "amount": 100.0,
    }
    with sqlite3.connect(path) as connection:
        pd.DataFrame([row]).to_sql(table, connection, index=False)


@pytest.mark.parametrize("loader,table,period_column", LOADERS)
def test_replaced_database_refreshes_warmed_cache(
    tmp_path, monkeypatch, loader, table, period_column
):
    database = tmp_path / "market_stats.sqlite"
    monkeypatch.setattr(app, "SQLITE_PATH", database)
    write_database(database, table, period_column, "2026-07")
    assert loader()[period_column].tolist() == ["2026-07"]

    replacement = tmp_path / "replacement.sqlite"
    write_database(replacement, table, period_column, "2026-08")
    original_stat = database.stat()
    # A deployment can preserve the size and modification time. Inode/ctime
    # must still distinguish the replacement from the cached generation.
    assert replacement.stat().st_size == original_stat.st_size
    os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    replacement.replace(database)

    assert loader()[period_column].tolist() == ["2026-08"]


@pytest.mark.parametrize("loader,table,period_column", LOADERS)
def test_missing_database_appears_after_empty_result_is_cached(
    tmp_path, monkeypatch, loader, table, period_column
):
    database = tmp_path / "market_stats.sqlite"
    monkeypatch.setattr(app, "SQLITE_PATH", database)
    assert loader().empty
    write_database(database, table, period_column, "2026-08")
    assert loader()[period_column].tolist() == ["2026-08"]


@pytest.mark.parametrize("loader,table,period_column", LOADERS)
def test_in_place_update_refreshes_but_unchanged_database_reuses_cache(
    tmp_path, monkeypatch, loader, table, period_column
):
    database = tmp_path / "market_stats.sqlite"
    monkeypatch.setattr(app, "SQLITE_PATH", database)
    write_database(database, table, period_column, "2026-07")
    read_query = pd.read_sql_query
    reads = []

    def record_query(*args, **kwargs):
        reads.append(args[0])
        return read_query(*args, **kwargs)

    monkeypatch.setattr(pd, "read_sql_query", record_query)
    assert loader()[period_column].tolist() == ["2026-07"]
    assert loader()[period_column].tolist() == ["2026-07"]
    assert len(reads) == 1
    old_stat = database.stat()
    with sqlite3.connect(database) as connection:
        connection.execute(f'UPDATE "{table}" SET "{period_column}" = ?', ("2026-08",))
    # Do not depend on wall-clock granularity to detect the in-place write.
    os.utime(database, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000_000))
    assert loader()[period_column].tolist() == ["2026-08"]
    assert len(reads) == 2

"""Consumer-visible regressions for TA totals and incomplete TCD periods."""

import json
import sqlite3

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import app


@pytest.fixture
def view_data(tmp_path, monkeypatch):
    database = tmp_path / "market_stats.sqlite"
    monkeypatch.setattr(app, "SQLITE_PATH", database)
    monkeypatch.setattr(app, "TA_META_PATH", tmp_path / "meta_ta.json")
    monkeypatch.setattr(app, "TCD_META_PATH", tmp_path / "meta_tcd.json")
    st.cache_data.clear()
    yield database
    st.cache_data.clear()


def test_ta_all_segments_counts_company_totals_once_and_hides_summary_rows(view_data):
    rows = []
    for company, amounts in [
        ("会社A", [10, 5, 15, 30]),
        ("JTB（6社計）", [20, 10, 30, 60]),
        ("合 計", [30, 15, 45, 90]),
    ]:
        for segment, amount in zip(
            ["domestic", "foreign", "overseas", "total"], amounts
        ):
            rows.append(
                {
                    "fiscal_year": "2025",
                    "period": "2026-03",
                    "company": company,
                    "segment": segment,
                    "amount": amount,
                }
            )
    with sqlite3.connect(view_data) as connection:
        pd.DataFrame(rows).to_sql("ta_company_amounts", connection, index=False)

    page = AppTest.from_string(
        "import app\napp.render_ta_view()", default_timeout=20
    ).run()

    assert not page.exception
    assert page.metric[0].value == "90"
    table = page.dataframe[0].value
    assert set(table["会社"]) == {"会社A", "JTB（6社計）"}
    assert len(table) == 8

    page.selectbox(key="ta_segment").select("国内旅行").run()
    assert not page.exception
    assert page.metric[0].value == "30"


def test_ta_missing_total_is_not_reported_as_zero(view_data):
    rows = pd.DataFrame(
        [
            {
                "fiscal_year": "2025",
                "period": "2026-03",
                "company": "会社A",
                "segment": "domestic",
                "amount": 10,
            }
        ]
    )
    with sqlite3.connect(view_data) as connection:
        rows.to_sql("ta_company_amounts", connection, index=False)
    page = AppTest.from_string(
        "import app\napp.render_ta_view()", default_timeout=20
    ).run()
    assert not page.exception
    assert page.metric[0].value == "—"
    assert len(page.info) > 0


def write_tcd_period(database, *, incomplete=False, unit="千泊"):
    rows = []
    bins = [
        ("1泊", 1),
        ("2泊", 2),
        ("3泊", 3),
        ("4泊", 4),
        ("5泊", 5),
        ("6泊", 6),
        ("7泊", 7),
        ("8泊以上", 8.5),
    ]
    for segment in ["domestic_total", "domestic_business"]:
        for label, nights in bins:
            if (
                incomplete
                and segment == "domestic_business"
                and label in {"6泊", "7泊"}
            ):
                continue
            rows.append(
                {
                    "period_type": "annual",
                    "period_key": "2025",
                    "period_label": "2025年",
                    "release_type": "確報",
                    "segment": segment,
                    "nights_bin": label,
                    "value": nights * 10,
                    "source_url": "https://example.test/annual.xlsx",
                    "source_title": "2025年確報",
                    "source_sha256": "a" * 64,
                }
            )
    with sqlite3.connect(database) as connection:
        pd.DataFrame(rows).to_sql("tcd_stay_nights", connection, index=False)
    app.TCD_META_PATH.write_text(
        json.dumps(
            {
                "processed_files": [
                    {
                        "url": "https://example.test/annual.xlsx",
                        "sha256": "a" * 64,
                        "source_unit": unit,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_incomplete_tcd_period_shows_values_but_holds_los_and_shares(view_data):
    write_tcd_period(view_data, incomplete=True)
    page = AppTest.from_string(
        "import app\napp.render_tcd_view()", default_timeout=20
    ).run()
    assert not page.exception
    assert not page.metric
    assert any("不足" in warning.value for warning in page.warning)
    assert len(page.dataframe) == 1
    table = page.dataframe[0].value.set_index("宿泊数区分")
    assert pd.isna(table.loc["6泊", "国内旅行（出張・業務）"])
    assert pd.isna(table.loc["7泊", "国内旅行（出張・業務）"])


@pytest.mark.parametrize("unit", ["千泊", "泊"])
def test_complete_tcd_period_displays_los_and_selected_source_unit(view_data, unit):
    write_tcd_period(view_data, unit=unit)
    page = AppTest.from_string(
        "import app\napp.render_tcd_view()", default_timeout=20
    ).run()
    assert not page.exception
    assert [metric.value for metric in page.metric] == ["4.56 泊", "4.56 泊"]
    assert any(f"単位：{unit}" in caption.value for caption in page.caption)


def test_unknown_tcd_unit_holds_indicators_and_keeps_raw_values_inspectable(view_data):
    write_tcd_period(view_data, unit=None)
    page = AppTest.from_string(
        "import app\napp.render_tcd_view()", default_timeout=20
    ).run()
    assert not page.exception
    assert not page.metric
    assert any("単位" in warning.value for warning in page.warning)
    assert len(page.dataframe) == 1


def test_duplicate_tcd_bin_is_inspectable_without_summing_or_comparison(view_data):
    write_tcd_period(view_data)
    with sqlite3.connect(view_data) as connection:
        connection.execute(
            "INSERT INTO tcd_stay_nights SELECT * FROM tcd_stay_nights LIMIT 1"
        )
    page = AppTest.from_string(
        "import app\napp.render_tcd_view()", default_timeout=20
    ).run()
    assert not page.exception
    assert not page.metric
    assert any("重複" in warning.value for warning in page.warning)
    assert len(page.dataframe[0].value) == 17
    assert not page.get("arrow_vega_lite_chart")


@pytest.mark.parametrize("unit", ["千泊", "泊"])
def test_tcd_chart_states_source_unit_on_axis_and_tooltip(unit):
    values = pd.DataFrame(
        [
            {
                "segment": "domestic_total",
                "nights_bin": "1泊",
                "value": 10,
            }
        ]
    )
    chart = app.build_tcd_chart(values, unit).to_dict()
    assert chart["encoding"]["y"]["title"] == f"延べ泊数（{unit}）"
    assert chart["encoding"]["tooltip"][-1]["title"] == f"延べ泊数（{unit}）"

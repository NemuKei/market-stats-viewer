import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.update_icd_data import detect_period_metadata_from_df, normalize_text, parse_period_metadata, parse_spend_sheet, to_float


def test_parse_period_metadata_accepts_calendar_year_label() -> None:
    period_label, period_key, release_type = parse_period_metadata(
        "2025年（令和7年） 暦年　【確報】"
    )

    assert period_label == "2025年年間"
    assert period_key == "2025"
    assert release_type == "確報"


def test_detect_period_metadata_from_df_accepts_calendar_year_cell() -> None:
    df = pd.DataFrame(
        [
            ["", ""],
            ["参考2", ""],
            ["", ""],
            ["", "2025年（令和7年） 暦年　【確報】"],
        ]
    )

    assert detect_period_metadata_from_df(df) == ("2025年年間", "2025", "確報")


def test_parse_period_metadata_accepts_quarter_label() -> None:
    period_label, period_key, release_type = parse_period_metadata(
        "2025年10-12月期【1次速報】"
    )

    assert period_label == "2025年10-12月期"
    assert period_key == "2025Q4"
    assert release_type == "1次速報"


def test_blank_spend_sheet_cells_do_not_become_nan_labels() -> None:
    assert normalize_text(float("nan")) == ""
    df = pd.DataFrame([
        ["調査項目", "", "", "", "全国籍", ""],
        ["", "", "", "", "消費単価", "構成比"],
        ["", "宿泊費", float("nan"), float("nan"), 20000, 20],
    ])
    rows = parse_spend_sheet(df, "all", "2026年1-3月期", "2026Q1", "確報")
    assert rows["item"].tolist() == ["宿泊費"]
    assert rows["item_group"].tolist() == ["宿泊費"]


def test_nan_spend_value_is_missing() -> None:
    assert to_float(float("nan")) is None


def test_spend_sheet_does_not_publish_table_heading_as_item() -> None:
    df = pd.DataFrame([
        ["調査項目", "", "", "", "全国籍", ""],
        ["", "", "", "", "消費単価", "構成比"],
        ["", "費目別支出", float("nan"), float("nan"), 100000, 100],
        ["", "宿泊費", float("nan"), float("nan"), 20000, 20],
    ])
    rows = parse_spend_sheet(df, "all", "2026年1-3月期", "2026Q1", "確報")
    assert rows["item"].tolist() == ["宿泊費"]

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.update_icd_data import detect_period_metadata_from_df, parse_period_metadata


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

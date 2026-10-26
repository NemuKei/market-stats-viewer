import pandas as pd
import pytest

from stats import ta


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        ("合計", True),
        (" 合 計 ", True),
        ("　小　計　", True),
        ("\t合\u00a0計\n", True),
        ("JTB（6社計）", False),
        ("ＪＴＢ（６社計）", False),
        ("合計トラベル株式会社", False),
        ("", False),
        (None, False),
        (pd.NA, False),
        (float("nan"), False),
        (123, False),
    ],
)
def test_summary_classification_matches_only_standalone_labels(
    company: object, expected: bool
) -> None:
    assert ta.is_ta_summary_company(company) is expected


@pytest.fixture
def company_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("JTB（6社計）", "domestic", 30),
            ("JTB（6社計）", "foreign", 20),
            ("JTB（6社計）", "overseas", 10),
            ("JTB（6社計）", "total", 60),
            ("会社B", "domestic", 7),
            ("会社B", "foreign", 2),
            ("会社B", "overseas", 1),
            ("会社B", "total", 10),
            ("合 計", "domestic", 37),
            ("合 計", "foreign", 22),
            ("合 計", "overseas", 11),
            ("合 計", "total", 70),
            ("　小　計　", "total", 60),
        ],
        columns=["company", "segment", "amount"],
    ).assign(fiscal_year="2024", period="total", source="fixture")


def test_company_filter_preserves_all_segment_rows_and_columns(
    company_rows: pd.DataFrame,
) -> None:
    actual = ta.filter_ta_company_rows(company_rows)

    pd.testing.assert_frame_equal(actual, company_rows.iloc[:8])


def test_company_filter_returns_an_independent_copy(company_rows: pd.DataFrame) -> None:
    original = company_rows.copy(deep=True)

    actual = ta.filter_ta_company_rows(company_rows)
    actual.loc[0, "amount"] = 999

    pd.testing.assert_frame_equal(company_rows, original)


@pytest.mark.parametrize(
    ("segment", "expected_segment", "expected_amounts"),
    [
        (None, "total", [60, 10]),
        ("total", "total", [60, 10]),
        ("domestic", "domestic", [30, 7]),
        ("foreign", "foreign", [20, 2]),
        ("overseas", "overseas", [10, 1]),
    ],
)
def test_amount_selection_uses_one_requested_segment(
    company_rows: pd.DataFrame,
    segment: str | None,
    expected_segment: str,
    expected_amounts: list[int],
) -> None:
    actual = ta.select_ta_amount_rows(company_rows, segment)

    assert actual["company"].tolist() == ["JTB（6社計）", "会社B"]
    assert actual["segment"].tolist() == [expected_segment, expected_segment]
    assert actual["amount"].tolist() == expected_amounts
    assert actual.columns.tolist() == company_rows.columns.tolist()


def test_amount_selection_does_not_add_breakdowns_when_total_is_missing(
    company_rows: pd.DataFrame,
) -> None:
    without_company_total = company_rows.drop(index=3)

    actual = ta.select_ta_amount_rows(without_company_total)

    assert actual["company"].tolist() == ["会社B"]
    assert actual["amount"].tolist() == [10]


def test_amount_selection_is_empty_when_only_breakdowns_exist(
    company_rows: pd.DataFrame,
) -> None:
    only_breakdowns = company_rows[company_rows["segment"] != "total"]

    actual = ta.select_ta_amount_rows(only_breakdowns)

    assert actual.empty
    assert actual.columns.tolist() == company_rows.columns.tolist()


def test_amount_selection_returns_an_independent_copy(
    company_rows: pd.DataFrame,
) -> None:
    original = company_rows.copy(deep=True)

    actual = ta.select_ta_amount_rows(company_rows)
    actual.loc[3, "amount"] = 999

    pd.testing.assert_frame_equal(company_rows, original)


def test_empty_frames_are_safe_to_filter_and_select() -> None:
    empty = pd.DataFrame()

    filtered = ta.filter_ta_company_rows(empty)
    selected = ta.select_ta_amount_rows(empty)

    pd.testing.assert_frame_equal(filtered, empty)
    pd.testing.assert_frame_equal(selected, empty)
    assert filtered is not empty
    assert selected is not empty

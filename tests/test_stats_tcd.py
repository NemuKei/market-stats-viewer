from copy import deepcopy

import pandas as pd
import pytest

from stats.tcd import (
    estimate_tcd_los_by_segment,
    is_complete_tcd_period,
    resolve_tcd_source_unit,
)


def complete_period() -> pd.DataFrame:
    bins = ["1泊", "2泊", "3泊", "4泊", "5泊", "6泊", "7泊", "8泊以上"]
    values = {
        "domestic_total": [80.0, 80.0, 60.0, 40.0, 50.0, 60.0, 70.0, 85.0],
        "domestic_business": [20.0, 20.0, 15.0, 20.0, 10.0, 12.0, 14.0, 17.0],
    }
    return pd.DataFrame(
        [
            {
                "period_type": "quarter",
                "period_key": "2025Q4",
                "period_label": "2025年10～12月期",
                "release_type": "確報",
                "segment": segment,
                "nights_bin": nights_bin,
                "value": value,
                "source_url": "https://example.test/tcd.xlsx",
                "source_title": "2025年10～12月期（確報）",
                "source_sha256": "a" * 64,
            }
            for segment, segment_values in values.items()
            for nights_bin, value in zip(bins, segment_values)
        ]
    )


def test_missing_business_six_and_seven_night_bins_holds_both_los_series() -> None:
    data = complete_period()
    incomplete = data.loc[
        ~(
            (data["segment"] == "domestic_business")
            & data["nights_bin"].isin(["6泊", "7泊"])
        )
    ]

    assert estimate_tcd_los_by_segment(incomplete).empty


def test_complete_period_preserves_los_and_share_calculations() -> None:
    result = estimate_tcd_los_by_segment(complete_period().iloc[::-1])

    assert list(result.columns) == [
        "segment",
        "total_nights",
        "estimated_stays",
        "one_night_stays",
        "two_plus_stays",
        "estimated_los",
        "one_night_share_pct",
        "two_plus_share_pct",
        "segment_label",
    ]
    assert result["segment"].tolist() == ["domestic_total", "domestic_business"]
    assert result["segment_label"].tolist() == [
        "国内旅行（合計）",
        "国内旅行（出張・業務）",
    ]
    # Hand-derived stays: 80+40+20+10+10+10+10+10=190;
    # business: 20+10+5+5+2+2+2+2=48.
    assert result.iloc[0, 1:8].tolist() == pytest.approx(
        [525.0, 190.0, 80.0, 110.0, 525 / 190, 8000 / 190, 11000 / 190]
    )
    assert result.iloc[1, 1:8].tolist() == pytest.approx(
        [128.0, 48.0, 20.0, 28.0, 128 / 48, 2000 / 48, 2800 / 48]
    )


@pytest.mark.parametrize("segment", ["domestic_total", "domestic_business"])
@pytest.mark.parametrize(
    "nights_bin", ["1泊", "2泊", "3泊", "4泊", "5泊", "6泊", "7泊", "8泊以上"]
)
def test_each_missing_bin_holds_entire_period(segment: str, nights_bin: str) -> None:
    data = complete_period()
    incomplete = data.loc[
        ~((data["segment"] == segment) & (data["nights_bin"] == nights_bin))
    ]

    assert not is_complete_tcd_period(incomplete)
    assert estimate_tcd_los_by_segment(incomplete).empty


def test_missing_whole_business_series_holds_total_los() -> None:
    data = complete_period()
    incomplete = data.loc[data["segment"] == "domestic_total"]

    assert not is_complete_tcd_period(incomplete)
    assert estimate_tcd_los_by_segment(incomplete).empty


@pytest.mark.parametrize("replace_row", [False, True])
def test_duplicate_grain_is_not_summed_or_counted_as_completeness(
    replace_row: bool,
) -> None:
    data = complete_period()
    if replace_row:
        data = data.iloc[1:]
    duplicate = pd.concat([data, data.iloc[[-1]]], ignore_index=True)

    assert not is_complete_tcd_period(duplicate)
    assert estimate_tcd_los_by_segment(duplicate).empty


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("segment", "overseas_total"),
        ("segment", None),
        ("nights_bin", "9泊"),
        ("nights_bin", None),
    ],
)
def test_unknown_or_missing_grain_labels_hold_entire_period(
    column: str, value: str | None
) -> None:
    data = complete_period()
    data.loc[0, column] = value

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


@pytest.mark.parametrize(
    "value", [None, pd.NA, float("nan"), float("inf"), float("-inf"), -1, "bad", ""]
)
def test_missing_invalid_or_negative_values_hold_entire_period(value: object) -> None:
    data = complete_period().astype({"value": object})
    data.loc[0, "value"] = value

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


def test_non_real_numeric_values_cannot_be_nonnegative_night_counts() -> None:
    data = complete_period().astype({"value": object})
    data.loc[0, "value"] = 1 + 2j

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


@pytest.mark.parametrize("column", ["segment", "nights_bin", "value"])
def test_missing_required_columns_hold_entire_period(column: str) -> None:
    data = complete_period().drop(columns=[column])

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


def test_empty_period_has_no_los() -> None:
    assert not is_complete_tcd_period(pd.DataFrame())
    assert estimate_tcd_los_by_segment(pd.DataFrame()).empty


@pytest.mark.parametrize(
    ("column", "other"),
    [("period_type", "annual"), ("period_key", "2025Q3"), ("release_type", "2次速報")],
)
def test_different_period_or_release_rows_cannot_fill_missing_bins(
    column: str, other: str
) -> None:
    data = complete_period()
    data.loc[0, column] = other

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


@pytest.mark.parametrize("column", ["period_type", "period_key", "release_type"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_missing_period_or_release_metadata_holds_entire_period(
    column: str, value: str | None
) -> None:
    data = complete_period()
    data[column] = value

    assert not is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


def test_completeness_accepts_frames_without_optional_period_metadata() -> None:
    data = complete_period()[["segment", "nights_bin", "value"]]

    assert is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data)["estimated_stays"].tolist() == [
        190.0,
        48.0,
    ]


def test_numeric_strings_use_numeric_sums() -> None:
    data = complete_period().astype({"value": str})

    assert is_complete_tcd_period(data)
    result = estimate_tcd_los_by_segment(data)
    assert result["total_nights"].tolist() == [525.0, 128.0]
    assert result["estimated_stays"].tolist() == [190.0, 48.0]


def test_complete_all_zero_period_is_valid_but_los_is_undefined() -> None:
    data = complete_period().assign(value=0.0)

    assert is_complete_tcd_period(data)
    assert estimate_tcd_los_by_segment(data).empty


def test_zero_series_does_not_create_a_divide_by_zero_los() -> None:
    data = complete_period()
    data.loc[data["segment"] == "domestic_business", "value"] = 0.0

    assert is_complete_tcd_period(data)
    result = estimate_tcd_los_by_segment(data)
    assert result["segment"].tolist() == ["domestic_total"]
    assert result["estimated_los"].item() == pytest.approx(525 / 190)


@pytest.mark.parametrize(
    "representative", [7.5, 0.0, -1.0, float("nan"), float("inf"), float("-inf")]
)
def test_open_bin_representative_must_be_finite_and_at_least_eight(
    representative: float,
) -> None:
    with pytest.raises(ValueError, match="finite.*at least 8"):
        estimate_tcd_los_by_segment(complete_period(), representative)


@pytest.mark.parametrize(
    ("representative", "expected_stays"),
    [(8.0, [190.625, 48.125]), (17.0, [185.0, 47.0])],
)
def test_open_bin_representative_controls_estimated_stays(
    representative: float, expected_stays: list[float]
) -> None:
    result = estimate_tcd_los_by_segment(complete_period(), representative)

    assert result["estimated_stays"].tolist() == expected_stays


def test_calculation_and_completeness_do_not_mutate_input() -> None:
    data = complete_period().astype({"value": str}).iloc[::-1]
    original = data.copy(deep=True)

    assert is_complete_tcd_period(data)
    estimate_tcd_los_by_segment(data, upper_open_bin_nights=8.0)

    pd.testing.assert_frame_equal(data, original)


def source_metadata(unit: str = "千泊") -> dict:
    return {
        "processed_files": [
            {
                "url": "https://example.test/tcd.xlsx",
                "sha256": "a" * 64,
                "title_a1": "2025年10～12月期（確報）",
                "source_unit": unit,
                "fetched_at": "2026-01-01T00:00:00Z",
            }
        ]
    }


@pytest.mark.parametrize("unit", ["千泊", "泊"])
def test_source_unit_requires_a_supported_unit_from_matching_url_and_digest(
    unit: str,
) -> None:
    assert resolve_tcd_source_unit(complete_period(), source_metadata(unit)) == unit


def test_source_unit_ignores_other_digests_at_the_same_url() -> None:
    meta = source_metadata()
    meta["processed_files"].insert(
        0, meta["processed_files"][0] | {"sha256": "b" * 64, "source_unit": "泊"}
    )

    assert resolve_tcd_source_unit(complete_period(), meta) == "千泊"


@pytest.mark.parametrize(
    ("column", "value"),
    [("url", "https://example.test/other.xlsx"), ("sha256", "b" * 64)],
)
def test_source_unit_cannot_use_url_only_or_digest_only_matches(
    column: str, value: str
) -> None:
    meta = source_metadata()
    meta["processed_files"][0][column] = value

    assert resolve_tcd_source_unit(complete_period(), meta) is None


@pytest.mark.parametrize("unit", ["千泊", "泊"])
def test_multiple_sources_must_each_resolve_to_the_same_unit(unit: str) -> None:
    data = complete_period()
    data.loc[0, ["source_url", "source_sha256"]] = [
        "https://example.test/other.xlsx",
        "b" * 64,
    ]
    meta = source_metadata(unit)
    meta["processed_files"].append(
        meta["processed_files"][0]
        | {"url": "https://example.test/other.xlsx", "sha256": "b" * 64}
    )

    assert resolve_tcd_source_unit(data, meta) == unit


def test_source_unit_is_unknown_if_any_selected_source_is_unmatched() -> None:
    data = complete_period()
    data.loc[0, "source_sha256"] = "b" * 64

    assert resolve_tcd_source_unit(data, source_metadata()) is None


def test_mixed_source_units_are_not_silently_combined_or_converted() -> None:
    data = complete_period()
    data.loc[0, "source_sha256"] = "b" * 64
    meta = source_metadata()
    meta["processed_files"].append(
        meta["processed_files"][0] | {"sha256": "b" * 64, "source_unit": "泊"}
    )

    assert resolve_tcd_source_unit(data, meta) is None


@pytest.mark.parametrize("other_unit", ["泊", None, "百万円"])
def test_conflicting_or_unconfirmed_metadata_for_one_digest_holds_unit(
    other_unit: str | None,
) -> None:
    meta = source_metadata()
    meta["processed_files"].append(
        meta["processed_files"][0] | {"source_unit": other_unit}
    )

    assert resolve_tcd_source_unit(complete_period(), meta) is None


@pytest.mark.parametrize("unit", [None, "", "百万円", "千人泊", "（千泊）"])
def test_unknown_source_units_are_not_guessed(unit: str | None) -> None:
    meta = source_metadata()
    meta["processed_files"][0]["source_unit"] = unit

    assert resolve_tcd_source_unit(complete_period(), meta) is None


@pytest.mark.parametrize("column", ["source_url", "source_sha256"])
def test_source_unit_requires_both_source_columns(column: str) -> None:
    data = complete_period().drop(columns=[column])

    assert resolve_tcd_source_unit(data, source_metadata()) is None


@pytest.mark.parametrize("column", ["source_url", "source_sha256"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_source_unit_is_unconfirmed_when_any_row_lacks_provenance(
    column: str, value: str | None
) -> None:
    data = complete_period()
    data.loc[0, column] = value

    assert resolve_tcd_source_unit(data, source_metadata()) is None


@pytest.mark.parametrize("processed_files", [[], None, {}, [None]])
def test_source_unit_requires_processed_file_metadata(processed_files: object) -> None:
    assert (
        resolve_tcd_source_unit(complete_period(), {"processed_files": processed_files})
        is None
    )


def test_source_unit_does_not_fall_back_to_global_or_missing_metadata() -> None:
    data = complete_period()
    meta = source_metadata()
    del meta["processed_files"][0]["source_unit"]
    meta["source_unit"] = "千泊"

    assert resolve_tcd_source_unit(data, meta) is None
    assert resolve_tcd_source_unit(data, {}) is None


def test_empty_selection_has_no_confirmed_unit() -> None:
    assert (
        resolve_tcd_source_unit(complete_period().iloc[:0], source_metadata()) is None
    )


def test_unit_resolution_does_not_mutate_rows_or_metadata() -> None:
    data = complete_period()
    meta = source_metadata()
    original_data = data.copy(deep=True)
    original_meta = deepcopy(meta)

    assert resolve_tcd_source_unit(data, meta) == "千泊"

    pd.testing.assert_frame_equal(data, original_data)
    assert meta == original_meta

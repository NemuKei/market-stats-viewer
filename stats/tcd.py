"""Pure calculations for travel and tourism consumption survey statistics."""

from __future__ import annotations

from math import isfinite

import pandas as pd


TCD_SEGMENT_LABELS = {
    "domestic_total": "国内旅行（合計）",
    "domestic_business": "国内旅行（出張・業務）",
}
TCD_NIGHTS_BIN_ORDER = [
    "1泊",
    "2泊",
    "3泊",
    "4泊",
    "5泊",
    "6泊",
    "7泊",
    "8泊以上",
]


def is_complete_tcd_period(df_period: pd.DataFrame) -> bool:
    """Require one finite, nonnegative observation for every segment and bin.

    Period and release columns are optional for calculation-only callers. When
    present, each must identify one nonmissing period or release throughout.
    """
    required_columns = {"segment", "nights_bin", "value"}
    if (
        not df_period.columns.is_unique
        or not required_columns.issubset(df_period.columns)
        or len(df_period) != len(TCD_SEGMENT_LABELS) * len(TCD_NIGHTS_BIN_ORDER)
    ):
        return False
    if (
        not df_period["segment"].isin(TCD_SEGMENT_LABELS).all()
        or not df_period["nights_bin"].isin(TCD_NIGHTS_BIN_ORDER).all()
        or df_period.duplicated(["segment", "nights_bin"]).any()
    ):
        return False

    for column in ("period_type", "period_key", "release_type"):
        if column in df_period.columns:
            metadata = df_period[column]
            if (
                metadata.isna().any()
                or metadata.astype(str).str.strip().eq("").any()
                or metadata.nunique() != 1
            ):
                return False

    values = pd.to_numeric(df_period["value"], errors="coerce")
    if pd.api.types.is_complex_dtype(values.dtype):
        return False
    return bool(
        values.notna().all() and values.map(isfinite).all() and values.ge(0).all()
    )


def estimate_tcd_los_by_segment(
    df_period: pd.DataFrame, upper_open_bin_nights: float = 8.5
) -> pd.DataFrame:
    """Approximate LOS and stay shares only when the whole period is complete.

    ``value`` remains in its source unit. A common scale factor cancels from LOS
    and shares. The representative value for the open bin must be finite and
    at least eight nights; otherwise this raises ``ValueError``.
    """
    if not is_complete_tcd_period(df_period):
        return pd.DataFrame()

    upper_open_bin_nights = float(upper_open_bin_nights)
    if not isfinite(upper_open_bin_nights) or upper_open_bin_nights < 8.0:
        raise ValueError("upper_open_bin_nights must be finite and at least 8")

    representative_nights = {
        "1泊": 1.0,
        "2泊": 2.0,
        "3泊": 3.0,
        "4泊": 4.0,
        "5泊": 5.0,
        "6泊": 6.0,
        "7泊": 7.0,
        "8泊以上": upper_open_bin_nights,
    }
    work = df_period[["segment", "nights_bin", "value"]].copy()
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work["rep_nights"] = work["nights_bin"].map(representative_nights)
    work["estimated_stays"] = work["value"] / work["rep_nights"]
    summary = work.groupby("segment", as_index=False).agg(
        total_nights=("value", "sum"), estimated_stays=("estimated_stays", "sum")
    )
    summary = summary[summary["estimated_stays"] > 0].copy()
    if summary.empty:
        return pd.DataFrame()

    one_night = work[work["nights_bin"] == "1泊"][
        ["segment", "estimated_stays"]
    ].rename(columns={"estimated_stays": "one_night_stays"})
    summary = summary.merge(one_night, on="segment", how="left")
    summary["one_night_stays"] = summary["one_night_stays"].fillna(0.0)
    summary["two_plus_stays"] = (
        summary["estimated_stays"] - summary["one_night_stays"]
    ).clip(lower=0.0)
    summary["estimated_los"] = summary["total_nights"] / summary["estimated_stays"]
    summary["one_night_share_pct"] = (
        summary["one_night_stays"] / summary["estimated_stays"] * 100.0
    )
    summary["two_plus_share_pct"] = (
        summary["two_plus_stays"] / summary["estimated_stays"] * 100.0
    )
    summary["segment_label"] = summary["segment"].map(TCD_SEGMENT_LABELS)
    summary["segment_order"] = summary["segment"].map(
        {segment: index for index, segment in enumerate(TCD_SEGMENT_LABELS)}
    )
    return (
        summary.sort_values("segment_order")
        .drop(columns=["segment_order"])
        .reset_index(drop=True)
    )


def resolve_tcd_source_unit(df_period: pd.DataFrame, meta: dict) -> str | None:
    """Resolve one common unit from exact source URL and digest matches.

    Missing provenance, stale metadata, unsupported units, and conflicting or
    mixed units leave the unit unconfirmed. Raw values are never converted.
    """
    source_columns = ["source_url", "source_sha256"]
    if (
        df_period.empty
        or not df_period.columns.is_unique
        or not set(source_columns).issubset(df_period.columns)
        or not isinstance(meta, dict)
    ):
        return None
    processed_files = meta.get("processed_files")
    if not isinstance(processed_files, list):
        return None

    units: set[str] = set()
    sources = df_period[source_columns].drop_duplicates()
    for source_url, source_sha256 in sources.itertuples(index=False, name=None):
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (source_url, source_sha256)
        ):
            return None
        matches = [
            entry
            for entry in processed_files
            if isinstance(entry, dict)
            and entry.get("url") == source_url
            and entry.get("sha256") == source_sha256
        ]
        if not matches:
            return None
        for entry in matches:
            unit = entry.get("source_unit")
            if unit not in ("千泊", "泊"):
                return None
            units.add(unit)
        if len(units) != 1:
            return None
    return next(iter(units), None)

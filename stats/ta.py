"""Pure row selection for travel agency transaction amounts."""

from __future__ import annotations

import unicodedata

import pandas as pd


def is_ta_summary_company(value: object) -> bool:
    """Recognize standalone totals without excluding named company groups."""
    if not isinstance(value, str):
        return False
    compact = "".join(unicodedata.normalize("NFKC", value).split())
    return compact in {"合計", "小計"}


def filter_ta_company_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Copy company rows, preserving their segments and source columns."""
    if df.empty:
        return df.copy()
    return df.loc[~df["company"].map(is_ta_summary_company)].copy()


def select_ta_amount_rows(df: pd.DataFrame, segment: str | None = None) -> pd.DataFrame:
    """Select one segment of company amounts; unspecified means total."""
    rows = filter_ta_company_rows(df)
    if rows.empty:
        return rows
    selected_segment = "total" if segment is None else segment
    return rows.loc[rows["segment"].eq(selected_segment)].copy()

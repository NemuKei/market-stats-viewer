from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path
from typing import cast

import altair as alt
import pandas as pd
import streamlit as st
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.layout import Layout, ManualLayout

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
SQLITE_PATH = DATA_DIR / "market_stats.sqlite"
META_PATH = DATA_DIR / "meta.json"

REGION_PREF_CODES = {
    "北海道": ["01"],
    "東北": ["02", "03", "04", "05", "06", "07"],
    "関東": ["08", "09", "10", "11", "12", "13", "14"],
    "中部": ["15", "16", "17", "18", "19", "20", "21", "22", "23"],
    "近畿（関西）": ["24", "25", "26", "27", "28", "29", "30"],
    "中国": ["31", "32", "33", "34", "35"],
    "四国": ["36", "37", "38", "39"],
    "九州・沖縄": ["40", "41", "42", "43", "44", "45", "46", "47"],
}
TIME_SERIES_METRICS = {
    "国内+海外（積み上げ）": "stacked",
    "全体": "total",
    "国内": "jp",
    "海外": "foreign",
}
ANNUAL_METRICS = {"全体": "total", "国内": "jp", "海外": "foreign"}
CHART_VALUE_MODES = {
    "月次": "monthly",
    "年計推移（表記月起点・直近12か月ローリング）": "rolling12",
}


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    if not SQLITE_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(SQLITE_PATH)) as conn:
            df = pd.read_sql_query("SELECT * FROM market_stats", conn)
        df["pref_code"] = df["pref_code"].astype(str).str.zfill(2)
        df["ym"] = df["ym"].astype(str)
        return df
    except Exception:
        return pd.DataFrame()


def load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def add_year_month_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["year"] = out["ym"].str.slice(0, 4).astype(int)
    out["month"] = out["ym"].str.slice(5, 7).astype(int)
    out["month_label"] = out["month"].map(lambda m: f"{m:02d}")
    return out


@st.cache_data(show_spinner=False)
def get_scope_dataframe(
    df: pd.DataFrame, scope_type: str, scope_id: str
) -> pd.DataFrame:
    if scope_type == "pref":
        out = df[df["pref_code"] == scope_id].copy()
        return out.sort_values("ym").reset_index(drop=True)

    pref_codes = REGION_PREF_CODES.get(scope_id, [])
    work = df[df["pref_code"].isin(pref_codes)].copy()
    if work.empty:
        return pd.DataFrame(columns=df.columns)

    grouped = (
        work.groupby("ym", as_index=False)[["total", "jp", "foreign"]]
        .sum()
        .sort_values("ym")
    )
    grouped["pref_code"] = scope_id
    grouped["pref_name"] = scope_id
    grouped = grouped[["ym", "pref_code", "pref_name", "foreign", "jp", "total"]]
    return grouped.reset_index(drop=True)


def ym_to_int(ym: str) -> int:
    return int(ym[:4]) * 100 + int(ym[5:7])


def build_ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def clamp_ym_to_available_range(ym: str, min_ym: str, max_ym: str) -> tuple[str, bool]:
    if ym < min_ym:
        return min_ym, True
    if ym > max_ym:
        return max_ym, True
    return ym, False


def sanitize_for_filename(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip()).strip("_")
    if safe:
        return safe
    suffix = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"scope_{suffix}"


def normalize_selected_years(
    selected_years: list[int] | tuple[int, ...], available_years: list[int]
) -> list[int]:
    if not available_years:
        return []
    normalized = sorted({int(y) for y in selected_years if int(y) in available_years})
    if normalized:
        return normalized
    return available_years[-4:] if len(available_years) > 4 else available_years


def apply_rolling_12m(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    work = df.sort_values("ym").copy()
    target_cols = ["total", "jp", "foreign"]
    for col in target_cols:
        work[col] = work[col].rolling(window=12, min_periods=12).sum()
    work = work.dropna(subset=target_cols).copy()
    for col in target_cols:
        work[col] = work[col].round().astype("int64")
    return work.reset_index(drop=True)


def get_chart_source_dataframes(
    df_scope_all: pd.DataFrame, ym_from: str, ym_to: str, chart_value_mode_label: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mode = CHART_VALUE_MODES.get(chart_value_mode_label, "monthly")
    if mode == "rolling12":
        chart_all = apply_rolling_12m(df_scope_all)
    else:
        chart_all = df_scope_all.sort_values("ym").reset_index(drop=True)

    chart_filtered = chart_all[(chart_all["ym"] >= ym_from) & (chart_all["ym"] <= ym_to)]
    return chart_filtered.reset_index(drop=True), chart_all


def write_helper_table(
    ws, df: pd.DataFrame, start_row: int, start_col: int = 1
) -> tuple[int, int]:
    headers = df.columns.tolist()
    for j, header in enumerate(headers, start=start_col):
        ws.cell(row=start_row, column=j, value=header)
    for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, value in enumerate(row, start=start_col):
            ws.cell(row=i, column=j, value=value)
    end_row = start_row if df.empty else start_row + len(df)
    end_col = start_col + len(headers) - 1
    return end_row, end_col


def try_set_attr(obj, attr_name: str, value) -> None:
    try:
        setattr(obj, attr_name, value)
    except Exception:
        pass


def assign_axis_ids(chart, x_id: int, y_id: int) -> None:
    chart.axId = [x_id, y_id]
    chart.x_axis.axId = x_id
    chart.y_axis.axId = y_id
    chart.x_axis.crossAx = y_id
    chart.y_axis.crossAx = x_id


def build_excel_report_bytes(
    df_table: pd.DataFrame,
    df_chart_filtered: pd.DataFrame,
    df_chart_all: pd.DataFrame,
    selection_state: dict,
) -> bytes:
    time_series_label = selection_state["time_series_label"]
    annual_metric_label = selection_state["annual_metric_label"]
    annual_years = selection_state["annual_years"]
    chart_value_mode_label = selection_state["chart_value_mode_label"]
    is_rolling = CHART_VALUE_MODES.get(chart_value_mode_label) == "rolling12"
    rolling_suffix = "・12か月ローリング" if is_rolling else ""

    data_sheet_df = df_table[
        ["ym", "pref_code", "pref_name", "total", "jp", "foreign"]
    ].copy()
    data_sheet_df = data_sheet_df.rename(
        columns={
            "ym": "年月",
            "pref_code": "地域コード",
            "pref_name": "地域名",
            "total": "全体",
            "jp": "国内",
            "foreign": "海外",
        }
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data_sheet_df.to_excel(writer, sheet_name="data", index=False)
        workbook = writer.book
        charts_ws = workbook.create_sheet("charts")

        charts_ws["A1"] = "Exported charts"
        helper_col = 30  # AD列付近に補助表を置き、見た目への干渉を避ける

        # Time-series helper and chart
        ts_base = add_year_month_columns(
            df_chart_filtered[["ym", "total", "jp", "foreign"]]
        ).sort_values("ym")
        ts_mode = TIME_SERIES_METRICS.get(time_series_label, "stacked")
        if ts_mode == "stacked":
            ts_helper = ts_base[["ym", "jp", "foreign"]].rename(
                columns={"ym": "年月", "jp": "国内", "foreign": "海外"}
            )
            ts_title = f"時系列（積み上げ{rolling_suffix}）"
            ts_grouping = "stacked"
        else:
            ts_helper = ts_base[["ym", ts_mode]].rename(
                columns={"ym": "年月", ts_mode: time_series_label}
            )
            ts_title = f"時系列（{time_series_label}{rolling_suffix}）"
            ts_grouping = "clustered"

        ts_start_row = 2
        ts_end_row, ts_end_col = write_helper_table(
            charts_ws, ts_helper, ts_start_row, start_col=helper_col
        )
        if not ts_helper.empty:
            ts_chart = BarChart()
            ts_chart.type = "col"
            ts_chart.grouping = ts_grouping
            assign_axis_ids(ts_chart, 10, 100)
            if ts_grouping == "stacked":
                ts_chart.overlap = 100
            ts_chart.title = ts_title
            ts_chart.y_axis.title = "延べ宿泊者数"
            ts_chart.x_axis.title = None
            ts_chart.legend.position = "r"
            ts_chart.legend.overlay = False
            ts_chart.layout = Layout(
                manualLayout=ManualLayout(x=0.04, y=0.08, w=0.78, h=0.78)
            )
            ts_data = Reference(
                charts_ws,
                min_col=helper_col + 1,
                max_col=ts_end_col,
                min_row=ts_start_row,
                max_row=ts_end_row,
            )
            ts_categories = Reference(
                charts_ws,
                min_col=helper_col,
                min_row=ts_start_row + 1,
                max_row=ts_end_row,
            )
            ts_chart.add_data(ts_data, titles_from_data=True)
            ts_chart.set_categories(ts_categories)
            ts_chart.x_axis.delete = False
            ts_chart.y_axis.delete = False
            ts_chart.x_axis.tickLblPos = "low"
            ts_chart.x_axis.tickLblSkip = 3
            try_set_attr(ts_chart.x_axis, "tickMarkSkip", 3)
            ts_chart.x_axis.majorTickMark = "out"
            ts_chart.y_axis.majorTickMark = "out"
            try_set_attr(ts_chart.y_axis, "numFmt", "#,##0")
            ts_chart.y_axis.majorGridlines = ChartLines()
            ts_chart.width = 26
            ts_chart.height = 11
            charts_ws.add_chart(ts_chart, "A2")
        else:
            charts_ws["A2"] = "時系列グラフ: データなし"

        # Annual comparison helper and chart
        annual_base = add_year_month_columns(
            df_chart_all[["ym", "total", "jp", "foreign"]]
        )
        available_years = sorted(annual_base["year"].unique().tolist())
        years_for_chart = normalize_selected_years(annual_years, available_years)
        annual_col = ANNUAL_METRICS.get(annual_metric_label, "total")

        annual_pivot = (
            annual_base[annual_base["year"].isin(years_for_chart)]
            .pivot_table(index="month", columns="year", values=annual_col, aggfunc="sum")
            .reindex(range(1, 13))
        )
        for y in years_for_chart:
            if y not in annual_pivot.columns:
                annual_pivot[y] = float("nan")
        annual_pivot = (
            annual_pivot[years_for_chart] if years_for_chart else annual_pivot
        )
        if not is_rolling:
            annual_pivot = annual_pivot.fillna(0)
        annual_pivot.index = [f"{m:02d}" for m in annual_pivot.index]
        annual_helper = annual_pivot.reset_index().rename(
            columns={"index": "月", "month": "月"}
        )
        annual_helper.columns = ["月"] + [str(y) for y in years_for_chart]

        annual_start_row = max(30, ts_end_row + 3)
        annual_end_row, annual_end_col = write_helper_table(
            charts_ws, annual_helper, annual_start_row, start_col=helper_col
        )

        # Guard: overlap regression detector for time-series category column.
        ts_category_values = [
            charts_ws.cell(row=r, column=helper_col).value
            for r in range(ts_start_row + 1, ts_end_row + 1)
        ]
        if any(v == "月" for v in ts_category_values):
            raise RuntimeError(
                "Helper table overlap detected: time-series categories contain annual header."
            )

        if years_for_chart:
            annual_chart = BarChart()
            annual_chart.type = "col"
            annual_chart.grouping = "clustered"
            assign_axis_ids(annual_chart, 20, 200)
            annual_chart.title = f"年別同月比較（{annual_metric_label}{rolling_suffix}）"
            annual_chart.y_axis.title = "延べ宿泊者数"
            annual_chart.x_axis.title = None
            annual_chart.legend.position = "r"
            annual_chart.legend.overlay = False
            annual_chart.layout = Layout(
                manualLayout=ManualLayout(x=0.04, y=0.08, w=0.78, h=0.78)
            )
            annual_data = Reference(
                charts_ws,
                min_col=helper_col + 1,
                max_col=annual_end_col,
                min_row=annual_start_row,
                max_row=annual_end_row,
            )
            annual_categories = Reference(
                charts_ws,
                min_col=helper_col,
                min_row=annual_start_row + 1,
                max_row=annual_end_row,
            )
            annual_chart.add_data(annual_data, titles_from_data=True)
            annual_chart.set_categories(annual_categories)
            annual_chart.x_axis.delete = False
            annual_chart.y_axis.delete = False
            annual_chart.x_axis.tickLblPos = "low"
            annual_chart.x_axis.tickLblSkip = 1
            try_set_attr(annual_chart.x_axis, "tickMarkSkip", 1)
            annual_chart.x_axis.majorTickMark = "out"
            annual_chart.y_axis.majorTickMark = "out"
            try_set_attr(annual_chart.y_axis, "numFmt", "#,##0")
            annual_chart.y_axis.majorGridlines = ChartLines()
            annual_chart.width = 26
            annual_chart.height = 12
            charts_ws.add_chart(annual_chart, "A30")
        else:
            charts_ws["A30"] = "年別同月比較グラフ: データなし"

    buffer.seek(0)
    return buffer.getvalue()


def build_time_series_chart(
    df_filtered: pd.DataFrame, metric_mode: str
) -> alt.Chart | alt.LayerChart:
    work = add_year_month_columns(df_filtered[["ym", "total", "jp", "foreign"]])
    ym_sort = sorted(work["ym"].unique().tolist())

    if TIME_SERIES_METRICS[metric_mode] == "stacked":
        work["total"] = work["jp"] + work["foreign"]
        long_df = work.melt(
            id_vars=["ym", "year", "month", "total"],
            value_vars=["jp", "foreign"],
            var_name="metric_key",
            value_name="value",
        )
        metric_labels = {"jp": "国内", "foreign": "海外"}
        long_df["metric"] = long_df["metric_key"].map(metric_labels)
        long_df["stack_order"] = long_df["metric_key"].map({"foreign": 0, "jp": 1})
        long_df["share_label"] = long_df.apply(
            lambda r: f"{int(round((r['value'] / r['total']) * 100))}%"
            if r["total"] > 0
            else "",
            axis=1,
        )

        label_base = work[["ym", "year", "month", "total", "jp", "foreign"]].copy()
        jp_label_df = label_base.copy()
        jp_label_df["metric"] = metric_labels["jp"]
        jp_label_df["y_center"] = jp_label_df["foreign"] + (jp_label_df["jp"] / 2)
        jp_label_df["share_label"] = jp_label_df.apply(
            lambda r: f"{int(round((r['jp'] / r['total']) * 100))}%"
            if r["total"] > 0
            else "",
            axis=1,
        )
        foreign_label_df = label_base.copy()
        foreign_label_df["metric"] = metric_labels["foreign"]
        foreign_label_df["y_center"] = foreign_label_df["foreign"] / 2
        foreign_label_df["share_label"] = foreign_label_df.apply(
            lambda r: f"{int(round((r['foreign'] / r['total']) * 100))}%"
            if r["total"] > 0
            else "",
            axis=1,
        )
        share_df = pd.concat([jp_label_df, foreign_label_df], ignore_index=True)

        bars = (
            alt.Chart(long_df)
            .mark_bar()
            .encode(
                x=alt.X("ym:N", title="年月", sort=ym_sort),
                y=alt.Y("value:Q", title="延べ宿泊者数"),
                color=alt.Color(
                    "metric:N",
                    title="区分",
                    sort=["国内", "海外"],
                    scale=alt.Scale(domain=["国内", "海外"]),
                ),
                order=alt.Order("stack_order:Q", sort="ascending"),
                tooltip=[
                    alt.Tooltip("ym:N", title="年月"),
                    alt.Tooltip("year:Q", title="年"),
                    alt.Tooltip("month:Q", title="月"),
                    alt.Tooltip("metric:N", title="区分"),
                    alt.Tooltip("value:Q", title="値", format=",.0f"),
                    alt.Tooltip("share_label:N", title="シェア"),
                ],
            )
        )

        share_text = (
            alt.Chart(share_df)
            .mark_text(color="white", fontSize=10)
            .encode(
                x=alt.X("ym:N", sort=ym_sort),
                y=alt.Y("y_center:Q"),
                text=alt.Text("share_label:N"),
                detail=alt.Detail("metric:N"),
            )
        )

        return bars + share_text

    metric_col = TIME_SERIES_METRICS[metric_mode]
    single_df = work[["ym", "year", "month", metric_col]].copy()
    single_df = single_df.rename(columns={metric_col: "value"})
    single_df["metric"] = metric_mode

    return (
        alt.Chart(single_df)
        .mark_bar()
        .encode(
            x=alt.X("ym:N", title="年月", sort=ym_sort),
            y=alt.Y("value:Q", title="延べ宿泊者数"),
            color=alt.value("#4C78A8"),
            tooltip=[
                alt.Tooltip("ym:N", title="年月"),
                alt.Tooltip("year:Q", title="年"),
                alt.Tooltip("month:Q", title="月"),
                alt.Tooltip("metric:N", title="区分"),
                alt.Tooltip("value:Q", title="値", format=",.0f"),
            ],
        )
    )


def build_yearly_month_compare_chart(
    df_scope_all: pd.DataFrame, metric_col: str, selected_years: list[int]
) -> alt.Chart:
    month_sort = [f"{m:02d}" for m in range(1, 13)]
    work = add_year_month_columns(df_scope_all[["ym", "total", "jp", "foreign"]])
    work = work[work["year"].isin(selected_years)].copy()

    return (
        alt.Chart(work)
        .mark_bar()
        .encode(
            x=alt.X("month_label:N", title="月", sort=month_sort),
            xOffset=alt.XOffset("year:N", sort=selected_years),
            y=alt.Y(f"{metric_col}:Q", title="延べ宿泊者数"),
            color=alt.Color("year:N", title="年", sort=selected_years),
            tooltip=[
                alt.Tooltip("ym:N", title="年月"),
                alt.Tooltip("year:Q", title="年"),
                alt.Tooltip("month:Q", title="月"),
                alt.Tooltip(f"{metric_col}:Q", title="値", format=",.0f"),
            ],
        )
    )


def render_stay_stats_view() -> None:
    st.title("宿泊旅行統計調査：延べ宿泊者数（全体 / 国内 / 海外）")

    meta = load_meta()
    if meta:
        st.caption(
            f"最終取得（UTC）: {meta.get('fetched_at_utc')} / "
            f"範囲: {meta.get('min_ym')}〜{meta.get('max_ym')} / "
            f"rows: {meta.get('rows')}"
        )

    df = load_data()
    if df.empty:
        st.error(
            "データがありません。先に python -m scripts.update_data を実行して data/ を生成してください。"
        )
        return

    # フィルタ
    col1, col2, col3, col4 = st.columns([2, 3, 4, 3])
    with col1:
        scope_label = st.radio("地域区分", ["都道府県", "地方"], horizontal=True)
    with col2:
        if scope_label == "都道府県":
            prefs = (
                df[["pref_code", "pref_name"]]
                .drop_duplicates()
                .sort_values("pref_code")
            )
            pref_label = prefs.apply(
                lambda r: f"{r['pref_code']} {r['pref_name']}", axis=1
            ).tolist()
            pref_map = dict(zip(pref_label, prefs["pref_code"].tolist()))
            pref_sel = st.selectbox("地域（全国/都道府県）", pref_label, index=0)
            scope_type = "pref"
            scope_id = pref_map[pref_sel]
        else:
            region_name = st.selectbox("地方", list(REGION_PREF_CODES.keys()), index=0)
            st.caption(
                f"対象都道府県コード: {', '.join(REGION_PREF_CODES[region_name])}"
            )
            scope_type = "region"
            scope_id = region_name

    d_scope_all = get_scope_dataframe(df, scope_type, scope_id)
    if d_scope_all.empty:
        st.error("選択した地域区分/地域に対応するデータがありません。")
        return

    ym_list = sorted(d_scope_all["ym"].unique().tolist())
    min_ym = ym_list[0]
    max_ym = ym_list[-1]
    default_ym_from = ym_list[max(0, len(ym_list) - 36)]
    default_ym_to = ym_list[-1]

    default_from_year = int(default_ym_from[:4])
    default_from_month = int(default_ym_from[5:7])
    default_to_year = int(default_ym_to[:4])
    default_to_month = int(default_ym_to[5:7])

    year_options = sorted(
        d_scope_all["ym"].str.slice(0, 4).astype(int).unique().tolist()
    )
    month_options = list(range(1, 13))

    def format_month(m: int) -> str:
        return f"{m:02d}"

    with col3:
        start_col, end_col = st.columns(2)
        with start_col:
            st.caption("開始")
            start_year = st.selectbox(
                "開始（年）",
                year_options,
                index=year_options.index(default_from_year),
            )
            start_month = st.selectbox(
                "開始（月）",
                month_options,
                index=month_options.index(default_from_month),
                format_func=format_month,
            )
        with end_col:
            st.caption("終了")
            end_year = st.selectbox(
                "終了（年）",
                year_options,
                index=year_options.index(default_to_year),
            )
            end_month = st.selectbox(
                "終了（月）",
                month_options,
                index=month_options.index(default_to_month),
                format_func=format_month,
            )

    with col4:
        show_mode = st.radio(
            "表示", ["表＋グラフ", "表のみ", "グラフのみ"], horizontal=True
        )

    ym_from = build_ym(start_year, start_month)
    ym_to = build_ym(end_year, end_month)

    ym_from, from_clamped = clamp_ym_to_available_range(ym_from, min_ym, max_ym)
    ym_to, to_clamped = clamp_ym_to_available_range(ym_to, min_ym, max_ym)
    if from_clamped:
        st.warning(f"開始年月をデータ範囲に合わせて {ym_from} に補正しました。")
    if to_clamped:
        st.warning(f"終了年月をデータ範囲に合わせて {ym_to} に補正しました。")

    if ym_to_int(ym_from) > ym_to_int(ym_to):
        ym_from, ym_to = ym_to, ym_from
        st.warning(
            f"開始年月と終了年月が逆だったため、{ym_from} ～ {ym_to} に入れ替えました。"
        )

    d = d_scope_all[
        (d_scope_all["ym"] >= ym_from) & (d_scope_all["ym"] <= ym_to)
    ].copy()
    d = d.sort_values("ym")

    # 表（年月縦）
    table = d[["ym", "total", "jp", "foreign"]].copy()
    table = table.rename(
        columns={"ym": "年月", "total": "全体", "jp": "国内", "foreign": "海外"}
    )
    scope_file_id = sanitize_for_filename(f"{scope_type}_{scope_id}")
    export_file_stem = f"market_stats_{scope_file_id}_{ym_from}_{ym_to}"
    chart_mode_options = [
        "時系列（積み上げ縦棒：国内＋海外）",
        "年別（同月比較：全体/国内/海外）",
    ]
    chart_value_mode_options = list(CHART_VALUE_MODES.keys())
    chart_mode = st.session_state.get("chart_mode_export", chart_mode_options[0])
    if chart_mode not in chart_mode_options:
        chart_mode = chart_mode_options[0]
    chart_value_mode_label = st.session_state.get(
        "chart_value_mode_export", chart_value_mode_options[0]
    )
    if chart_value_mode_label not in CHART_VALUE_MODES:
        chart_value_mode_label = chart_value_mode_options[0]
    ts_metric_label = st.session_state.get("ts_metric_export", "国内+海外（積み上げ）")
    if ts_metric_label not in TIME_SERIES_METRICS:
        ts_metric_label = "国内+海外（積み上げ）"
    annual_metric_label = st.session_state.get("annual_metric_export", "全体")
    if annual_metric_label not in ANNUAL_METRICS:
        annual_metric_label = "全体"
    chart_filtered, chart_scope_all = get_chart_source_dataframes(
        d_scope_all, ym_from, ym_to, chart_value_mode_label
    )
    chart_year_options = (
        sorted(chart_scope_all["ym"].str.slice(0, 4).astype(int).unique().tolist())
        if not chart_scope_all.empty
        else []
    )
    default_chart_years = (
        chart_year_options[-4:] if len(chart_year_options) > 4 else chart_year_options
    )
    selected_years_for_export = normalize_selected_years(
        st.session_state.get("annual_years_export", default_chart_years),
        chart_year_options,
    )

    chart_height = 520
    if show_mode in ["表＋グラフ", "グラフのみ"]:
        st.subheader("グラフ")
        chart_mode = st.radio(
            "チャートモード",
            chart_mode_options,
            key="chart_mode_export",
        )
        chart_value_mode_label = st.radio(
            "値の種類",
            chart_value_mode_options,
            horizontal=True,
            key="chart_value_mode_export",
        )
        chart_filtered, chart_scope_all = get_chart_source_dataframes(
            d_scope_all, ym_from, ym_to, chart_value_mode_label
        )
        chart_year_options = (
            sorted(chart_scope_all["ym"].str.slice(0, 4).astype(int).unique().tolist())
            if not chart_scope_all.empty
            else []
        )
        default_chart_years = (
            chart_year_options[-4:] if len(chart_year_options) > 4 else chart_year_options
        )
        selected_years_for_export = normalize_selected_years(
            st.session_state.get("annual_years_export", default_chart_years),
            chart_year_options,
        )

        if chart_mode == "時系列（積み上げ縦棒：国内＋海外）":
            ts_metric_label = st.radio(
                "時系列の表示内容",
                list(TIME_SERIES_METRICS.keys()),
                horizontal=True,
                key="ts_metric_export",
            )
            if chart_filtered.empty:
                if CHART_VALUE_MODES.get(chart_value_mode_label) == "rolling12":
                    st.info(
                        "指定した期間にデータがありません。年計推移では各月で直近12か月分が必要です。"
                    )
                else:
                    st.info("指定した期間にデータがありません。")
            else:
                monthly_chart = build_time_series_chart(
                    chart_filtered, ts_metric_label
                ).properties(height=chart_height)
                st.altair_chart(
                    cast(alt.Chart, monthly_chart), use_container_width=True
                )
        else:
            annual_metric_label = st.radio(
                "指標",
                list(ANNUAL_METRICS.keys()),
                horizontal=True,
                key="annual_metric_export",
            )
            selected_years_ui: list[int] = []
            if not chart_year_options:
                st.info("選択中の値の種類では、年別同月比較に使えるデータがありません。")
            else:
                selected_years_ui = st.multiselect(
                    "年（同月比較に使う年）",
                    options=chart_year_options,
                    default=selected_years_for_export,
                    key="annual_years_export",
                )
                selected_years_for_export = normalize_selected_years(
                    selected_years_ui, chart_year_options
                )

            if not chart_year_options:
                pass
            elif not selected_years_ui:
                st.info("年を1つ以上選択してください。")
            else:
                yearly_chart = build_yearly_month_compare_chart(
                    chart_scope_all,
                    ANNUAL_METRICS[annual_metric_label],
                    selected_years_for_export,
                ).properties(height=chart_height)
                st.altair_chart(yearly_chart, use_container_width=True)

    if show_mode == "表＋グラフ":
        st.markdown("")

    if show_mode in ["表＋グラフ", "表のみ"]:
        st.subheader("表")
        st.dataframe(table, use_container_width=True, hide_index=True, height=560)
        excel_report_bytes = build_excel_report_bytes(
            d,
            chart_filtered,
            chart_scope_all,
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "ym_from": ym_from,
                "ym_to": ym_to,
                "time_series_label": ts_metric_label,
                "annual_metric_label": annual_metric_label,
                "annual_years": selected_years_for_export,
                "chart_value_mode_label": chart_value_mode_label,
            },
        )
        st.download_button(
            "Excelダウンロード（データ＋グラフ）",
            data=excel_report_bytes,
            file_name=f"{export_file_stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()
    st.caption("出典：観光庁『宿泊旅行統計調査』（推移表Excelを取得して整形）")
    st.caption(
        "データは毎週自動更新です。取得元サイトの構造変更等により更新が遅れる場合があります。"
    )




TCD_META_PATH = DATA_DIR / "meta_tcd.json"
TCD_TABLE_NAME = "tcd_stay_nights"

RELEASE_FINAL = "確報"
RELEASE_SECOND_PRELIM = "2次速報"

TCD_SEGMENT_LABELS = {
    "domestic_total": "\u56fd\u5185\u65c5\u884c\uff08\u5408\u8a08\uff09",
    "domestic_business": "\u56fd\u5185\u65c5\u884c\uff08\u51fa\u5f35\u30fb\u696d\u52d9\uff09",
}
TCD_PERIOD_TYPE_LABELS = {
    "annual": "\u5e74\u6b21",
    "quarter": "\u56db\u534a\u671f",
}
TCD_PERIOD_TYPE_KEYS = {v: k for k, v in TCD_PERIOD_TYPE_LABELS.items()}
TCD_RELEASE_FILTERS = {
    "\u6700\u65b0\uff08\u78ba\u5831\u512a\u5148\uff09": "latest",
    "\u78ba\u5831": RELEASE_FINAL,
    "2\u6b21\u901f\u5831": RELEASE_SECOND_PRELIM,
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


def load_tcd_meta() -> dict:
    if not TCD_META_PATH.exists():
        return {}
    return json.loads(TCD_META_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_tcd_data() -> pd.DataFrame:
    if not SQLITE_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(SQLITE_PATH)) as conn:
            df = pd.read_sql_query(f"SELECT * FROM {TCD_TABLE_NAME}", conn)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    str_cols = [
        "period_type",
        "period_key",
        "period_label",
        "release_type",
        "segment",
        "nights_bin",
        "source_url",
        "source_title",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)

    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return df


def parse_tcd_period_sort_key(period_key: str) -> tuple[int, int]:
    m_quarter = re.fullmatch(r"(\d{4})Q([1-4])", str(period_key))
    if m_quarter:
        return int(m_quarter.group(1)), int(m_quarter.group(2))

    m_annual = re.fullmatch(r"(\d{4})", str(period_key))
    if m_annual:
        return int(m_annual.group(1)), 0

    return 0, 0


def get_tcd_period_label_map(df: pd.DataFrame) -> dict[str, str]:
    if df.empty:
        return {}

    label_map: dict[str, str] = {}
    for _, row in df[["period_key", "period_label"]].drop_duplicates().iterrows():
        key = str(row["period_key"])
        label = str(row["period_label"]) if pd.notna(row["period_label"]) else key
        label_map[key] = label
    return label_map


def resolve_tcd_latest_period_rows(
    df_for_period_type: pd.DataFrame,
) -> tuple[pd.DataFrame, str | None, str | None]:
    if df_for_period_type.empty:
        return pd.DataFrame(), None, None

    period_keys = sorted(
        df_for_period_type["period_key"].dropna().astype(str).unique().tolist(),
        key=parse_tcd_period_sort_key,
    )
    if not period_keys:
        return pd.DataFrame(), None, None

    latest_period_key = period_keys[-1]
    latest_rows = df_for_period_type[
        df_for_period_type["period_key"] == latest_period_key
    ].copy()

    if latest_rows.empty:
        return pd.DataFrame(), None, None

    if (latest_rows["release_type"] == RELEASE_FINAL).any():
        return (
            latest_rows[latest_rows["release_type"] == RELEASE_FINAL].copy(),
            latest_period_key,
            RELEASE_FINAL,
        )

    if (latest_rows["release_type"] == RELEASE_SECOND_PRELIM).any():
        return (
            latest_rows[latest_rows["release_type"] == RELEASE_SECOND_PRELIM].copy(),
            latest_period_key,
            RELEASE_SECOND_PRELIM,
        )

    release_type = str(latest_rows["release_type"].iloc[0])
    return latest_rows, latest_period_key, release_type


def estimate_tcd_los_by_segment(
    df_period: pd.DataFrame, upper_open_bin_nights: float = 8.5
) -> pd.DataFrame:
    """
    Approximate LOS (average length of stay) from nights-bin total nights.
    8泊以上 is treated as `upper_open_bin_nights`.
    """
    representative_nights = {
        "1\u6cca": 1.0,
        "2\u6cca": 2.0,
        "3\u6cca": 3.0,
        "4\u6cca": 4.0,
        "5\u6cca": 5.0,
        "6\u6cca": 6.0,
        "7\u6cca": 7.0,
        "8\u6cca\u4ee5\u4e0a": float(upper_open_bin_nights),
    }

    work = (
        df_period.groupby(["segment", "nights_bin"], as_index=False)["value"]
        .sum()
        .copy()
    )
    work["rep_nights"] = work["nights_bin"].map(representative_nights)
    work = work.dropna(subset=["rep_nights"]).copy()
    if work.empty:
        return pd.DataFrame()

    work["estimated_stays"] = work["value"] / work["rep_nights"]
    summary = (
        work.groupby("segment", as_index=False)
        .agg(total_nights=("value", "sum"), estimated_stays=("estimated_stays", "sum"))
        .copy()
    )
    summary = summary[summary["estimated_stays"] > 0].copy()
    if summary.empty:
        return pd.DataFrame()

    one_night = (
        work[work["nights_bin"] == "1\u6cca"]
        .groupby("segment", as_index=False)["estimated_stays"]
        .sum()
        .rename(columns={"estimated_stays": "one_night_stays"})
    )
    summary = summary.merge(one_night, on="segment", how="left")
    summary["one_night_stays"] = summary["one_night_stays"].fillna(0.0)
    summary["two_plus_stays"] = (summary["estimated_stays"] - summary["one_night_stays"]).clip(
        lower=0.0
    )

    summary["estimated_los"] = summary["total_nights"] / summary["estimated_stays"]
    summary["one_night_share_pct"] = (
        summary["one_night_stays"] / summary["estimated_stays"] * 100.0
    )
    summary["two_plus_share_pct"] = (
        summary["two_plus_stays"] / summary["estimated_stays"] * 100.0
    )
    summary["segment_label"] = summary["segment"].map(TCD_SEGMENT_LABELS)

    segment_order = list(TCD_SEGMENT_LABELS.keys())
    summary["segment_order"] = summary["segment"].map(
        {segment: idx for idx, segment in enumerate(segment_order)}
    )
    summary = summary.sort_values("segment_order").drop(columns=["segment_order"])
    return summary.reset_index(drop=True)


def build_tcd_chart(df_period: pd.DataFrame) -> alt.Chart:
    chart_df = (
        df_period.groupby(["nights_bin", "segment"], as_index=False)["value"]
        .sum()
        .copy()
    )
    chart_df["segment_label"] = chart_df["segment"].map(TCD_SEGMENT_LABELS)

    available_bins = [
        b for b in TCD_NIGHTS_BIN_ORDER if b in chart_df["nights_bin"].astype(str).tolist()
    ]

    return (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "nights_bin:N",
                title="\u5bbf\u6cca\u6570\u533a\u5206",
                sort=available_bins,
            ),
            xOffset=alt.XOffset(
                "segment_label:N", sort=list(TCD_SEGMENT_LABELS.values())
            ),
            y=alt.Y("value:Q", title="\u5ef6\u3079\u6cca\u6570"),
            color=alt.Color(
                "segment_label:N",
                title="\u7cfb\u5217",
                sort=list(TCD_SEGMENT_LABELS.values()),
            ),
            tooltip=[
                alt.Tooltip("nights_bin:N", title="\u5bbf\u6cca\u6570\u533a\u5206"),
                alt.Tooltip("segment_label:N", title="\u7cfb\u5217"),
                alt.Tooltip("value:Q", title="\u5ef6\u3079\u6cca\u6570", format=",.0f"),
            ],
        )
    )


def render_tcd_view() -> None:
    st.title(
        "\u65c5\u884c\u30fb\u89b3\u5149\u6d88\u8cbb\u52d5\u5411\u8abf\u67fb\uff1a"
        "\u5bbf\u6cca\u6570(8\u533a\u5206)\u5225 \u5ef6\u3079\u6cca\u6570\uff08\u5168\u56fd\uff09"
    )

    meta = load_tcd_meta()
    if meta:
        st.caption(
            f"\u6700\u7d42\u78ba\u8a8d\uff08UTC\uff09: {meta.get('last_checked_at')} / "
            f"\u51e6\u7406\u6e08\u307f\u30d5\u30a1\u30a4\u30eb\u6570: {len(meta.get('processed_files', []))}"
        )

    df = load_tcd_data()
    if df.empty:
        st.error(
            "TCD\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002"
            "\u5148\u306b `python -m scripts.update_tcd_data` \u3092\u5b9f\u884c\u3057\u3066"
            " data/ \u3092\u751f\u6210\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
        )
        return

    work = df[df["segment"].isin(TCD_SEGMENT_LABELS.keys())].copy()
    if work.empty:
        st.error(
            "\u8868\u793a\u306b\u5fc5\u8981\u306a\u7cfb\u5217"
            "\uFF08domestic_total / domestic_business\uFF09\u304C\u898B\u3064\u304B\u308A\u307E\u305B\u3093\u3002"
        )
        return

    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        period_type_label = st.radio(
            "\u671f\u9593\u7a2e\u5225",
            list(TCD_PERIOD_TYPE_KEYS.keys()),
            horizontal=True,
            key="tcd_period_type",
        )
    period_type = TCD_PERIOD_TYPE_KEYS[period_type_label]
    work = work[work["period_type"] == period_type].copy()

    if work.empty:
        st.warning("\u9078\u629e\u3057\u305f\u671f\u9593\u7a2e\u5225\u306e\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
        return

    with col2:
        release_filter_label = st.radio(
            "\u30ea\u30ea\u30fc\u30b9\u7a2e\u5225",
            list(TCD_RELEASE_FILTERS.keys()),
            key="tcd_release_filter",
        )
    release_filter = TCD_RELEASE_FILTERS[release_filter_label]

    selected_period_key: str | None = None
    selected_release_type: str | None = None

    if release_filter == "latest":
        filtered, selected_period_key, selected_release_type = resolve_tcd_latest_period_rows(
            work
        )
    else:
        filtered_by_release = work[work["release_type"] == release_filter].copy()
        if filtered_by_release.empty:
            st.warning("\u9078\u629e\u3057\u305f\u30ea\u30ea\u30fc\u30b9\u7a2e\u5225\u306e\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002")
            return

        period_options = sorted(
            filtered_by_release["period_key"].dropna().astype(str).unique().tolist(),
            key=parse_tcd_period_sort_key,
            reverse=True,
        )
        period_label_map = get_tcd_period_label_map(filtered_by_release)

        with col3:
            selected_period_key = st.selectbox(
                "\u8868\u793a\u671f\u9593",
                period_options,
                format_func=lambda k: f"{period_label_map.get(k, k)} ({k})",
                key=f"tcd_period_key_{period_type}_{release_filter}",
            )

        filtered = filtered_by_release[
            filtered_by_release["period_key"] == selected_period_key
        ].copy()
        selected_release_type = release_filter

    if filtered.empty or selected_period_key is None or selected_release_type is None:
        st.warning("\u8868\u793a\u5bfe\u8c61\u306e\u30c7\u30fc\u30bf\u304C\u898B\u3064\u304B\u308A\u307E\u305B\u3093\u3002")
        return

    period_label_map = get_tcd_period_label_map(filtered)
    period_label = period_label_map.get(selected_period_key, selected_period_key)
    st.caption(f"\u8868\u793a\u4e2d: {period_label} / {selected_release_type}")

    los_open_bin = st.number_input(
        "LOS\u6982\u7b97: 8\u6cca\u4ee5\u4e0a\u306e\u4ee3\u8868\u5024\uff08\u6cca\uff09",
        min_value=8.0,
        max_value=15.0,
        value=8.5,
        step=0.5,
        key="tcd_los_open_bin",
    )
    los_summary = estimate_tcd_los_by_segment(filtered, upper_open_bin_nights=los_open_bin)
    if not los_summary.empty:
        st.subheader("LOS\uff08\u5e73\u5747\u6cca\u6570\uff09\u6982\u7b97")
        metric_cols = st.columns(len(los_summary))
        for col, row in zip(metric_cols, los_summary.itertuples(index=False)):
            col.metric(row.segment_label, f"{row.estimated_los:.2f} \u6cca")
        st.caption(
            "\u8a08\u7b97\u5f0f: LOS \u2248 \u03a3(\u5ef6\u3079\u6cca\u6570) / "
            "\u03a3(\u5404\u533a\u5206\u306e\u5ef6\u3079\u6cca\u6570 / \u533a\u5206\u4ee3\u8868\u5024)"
        )

        share_display = (
            los_summary[["segment_label", "one_night_share_pct", "two_plus_share_pct"]]
            .rename(
                columns={
                    "segment_label": "\u7cfb\u5217",
                    "one_night_share_pct": "1\u6cca\u30b7\u30a7\u30a2",
                    "two_plus_share_pct": "2\u6cca\u4ee5\u4e0a\u30b7\u30a7\u30a2",
                }
            )
            .copy()
        )
        share_display["1\u6cca\u30b7\u30a7\u30a2"] = share_display["1\u6cca\u30b7\u30a7\u30a2"].map(
            lambda v: f"{v:.1f}%"
        )
        share_display[
            "2\u6cca\u4ee5\u4e0a\u30b7\u30a7\u30a2"
        ] = share_display["2\u6cca\u4ee5\u4e0a\u30b7\u30a7\u30a2"].map(
            lambda v: f"{v:.1f}%"
        )
        st.subheader("\u5bbf\u6cca\u65e5\u6570\u30b7\u30a7\u30a2\uff08\u63a8\u5b9a\u4ef6\u6570\u30d9\u30fc\u30b9\uff09")
        st.dataframe(share_display, use_container_width=True, hide_index=True)
        st.caption(
            "\u8a08\u7b97\u5f0f: \u30b7\u30a7\u30a2 \u2248 "
            "\u03a3(\u533a\u5206\u306e\u5ef6\u3079\u6cca\u6570 / \u533a\u5206\u4ee3\u8868\u5024) / "
            "\u03a3(\u5168\u533a\u5206\u306e\u5ef6\u3079\u6cca\u6570 / \u533a\u5206\u4ee3\u8868\u5024)"
        )

    chart = build_tcd_chart(filtered).properties(height=500)
    st.altair_chart(chart, use_container_width=True)

    table_df = (
        filtered.groupby(["nights_bin", "segment"], as_index=False)["value"]
        .sum()
        .copy()
    )
    table_df["segment_label"] = table_df["segment"].map(TCD_SEGMENT_LABELS)
    table_pivot = (
        table_df.pivot(index="nights_bin", columns="segment_label", values="value")
        .reindex(TCD_NIGHTS_BIN_ORDER)
        .reset_index()
    )
    table_pivot = table_pivot.rename(
        columns={"nights_bin": "\u5bbf\u6cca\u6570\u533a\u5206"}
    )

    st.subheader("\u8868")
    st.dataframe(table_pivot, use_container_width=True, hide_index=True)
    st.caption(
        "\u30c7\u30fc\u30bf\u306f\u6bce\u9031\u81ea\u52d5\u66f4\u65b0\u3067\u3059\u3002"
        "\u53d6\u5f97\u5143\u30b5\u30a4\u30c8\u306e\u69cb\u9020\u5909\u66f4\u7b49\u306b\u3088\u308a"
        "\u66f4\u65b0\u304c\u9045\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u307e\u3059\u3002"
    )


def main() -> None:
    st.set_page_config(
        page_title="\u5e02\u5834\u7d71\u8a08\u30d3\u30e5\u30fc\u30a2",
        page_icon="assets/logo_header.svg",
        layout="wide",
    )

    lp_url = "https://deltahelmlab.com/?utm_source=market_stats_viewer&utm_medium=app&utm_campaign=cross_link"
    with st.sidebar:
        st.markdown("### \u904b\u55b6\u5143")
        st.link_button(
            "DeltaHelm Lab\uff08\u516c\u5f0f\u30b5\u30a4\u30c8\uff09",
            lp_url,
            use_container_width=True,
        )
        st.caption(
            "\u30b5\u30fc\u30d3\u30b9\u8a73\u7d30\u30fb\u304a\u554f\u3044\u5408\u308f\u305b\u306f\u3053\u3061\u3089"
        )
        dataset_type = st.radio(
            "\u7d71\u8a08\u306e\u7a2e\u985e",
            [
                "\u5bbf\u6cca\u65c5\u884c\u7d71\u8a08\u8abf\u67fb",
                "\u65c5\u884c\u30fb\u89b3\u5149\u6d88\u8cbb\u52d5\u5411\u8abf\u67fb",
            ],
            key="dataset_selector",
        )

    if dataset_type == "\u5bbf\u6cca\u65c5\u884c\u7d71\u8a08\u8abf\u67fb":
        render_stay_stats_view()
        return

    render_tcd_view()

if __name__ == "__main__":
    main()

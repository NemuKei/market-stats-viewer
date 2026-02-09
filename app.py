from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

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
def get_scope_dataframe(df: pd.DataFrame, scope_type: str, scope_id: str) -> pd.DataFrame:
    if scope_type == "pref":
        out = df[df["pref_code"] == scope_id].copy()
        return out.sort_values("ym").reset_index(drop=True)

    pref_codes = REGION_PREF_CODES.get(scope_id, [])
    work = df[df["pref_code"].isin(pref_codes)].copy()
    if work.empty:
        return pd.DataFrame(columns=df.columns)

    grouped = (
        work.groupby("ym", as_index=False)[["total", "jp", "foreign"]].sum().sort_values("ym")
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


def build_time_series_chart(df_filtered: pd.DataFrame, metric_mode: str) -> alt.Chart:
    work = add_year_month_columns(df_filtered[["ym", "total", "jp", "foreign"]])
    ym_sort = sorted(work["ym"].unique().tolist())

    if TIME_SERIES_METRICS[metric_mode] == "stacked":
        long_df = work.melt(
            id_vars=["ym", "year", "month"],
            value_vars=["jp", "foreign"],
            var_name="metric",
            value_name="value",
        )
        long_df["metric"] = long_df["metric"].map({"jp": "国内", "foreign": "海外"})
        return (
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
                tooltip=[
                    alt.Tooltip("ym:N", title="年月"),
                    alt.Tooltip("year:Q", title="年"),
                    alt.Tooltip("month:Q", title="月"),
                    alt.Tooltip("metric:N", title="区分"),
                    alt.Tooltip("value:Q", title="値", format=",.0f"),
                ],
            )
        )

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


def main() -> None:
    st.set_page_config(page_title="宿泊旅行統計（延べ宿泊者数）", layout="wide")

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
                df[["pref_code", "pref_name"]].drop_duplicates().sort_values("pref_code")
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
            st.caption(f"対象都道府県コード: {', '.join(REGION_PREF_CODES[region_name])}")
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

    year_options = sorted(d_scope_all["ym"].str.slice(0, 4).astype(int).unique().tolist())
    month_options = list(range(1, 13))
    month_formatter = lambda m: f"{m:02d}"

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
                format_func=month_formatter,
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
                format_func=month_formatter,
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
        st.warning(f"開始年月と終了年月が逆だったため、{ym_from} ～ {ym_to} に入れ替えました。")

    d = d_scope_all[(d_scope_all["ym"] >= ym_from) & (d_scope_all["ym"] <= ym_to)].copy()
    d = d.sort_values("ym")

    # 表（年月縦）
    table = d[["ym", "total", "jp", "foreign"]].copy()
    table = table.rename(
        columns={"ym": "年月", "total": "全体", "jp": "国内", "foreign": "海外"}
    )

    chart_height = 520
    if show_mode in ["表＋グラフ", "グラフのみ"]:
        st.subheader("グラフ")
        chart_mode = st.radio(
            "チャートモード",
            [
                "時系列（積み上げ縦棒：国内＋海外）",
                "年別（同月比較：全体/国内/海外）",
            ],
        )

        if chart_mode == "時系列（積み上げ縦棒：国内＋海外）":
            ts_metric_label = st.radio(
                "時系列の表示内容",
                list(TIME_SERIES_METRICS.keys()),
                horizontal=True,
            )
            if d.empty:
                st.info("指定した期間にデータがありません。")
            else:
                monthly_chart = build_time_series_chart(d, ts_metric_label).properties(
                    height=chart_height
                )
                st.altair_chart(monthly_chart, use_container_width=True)
        else:
            metric_label = st.radio("指標", list(ANNUAL_METRICS.keys()), horizontal=True)
            chart_year_options = sorted(
                d_scope_all["ym"].str.slice(0, 4).astype(int).unique().tolist()
            )
            default_years = (
                chart_year_options[-4:]
                if len(chart_year_options) > 4
                else chart_year_options
            )
            selected_years = st.multiselect(
                "年（同月比較に使う年）",
                options=chart_year_options,
                default=default_years,
            )

            if not selected_years:
                st.info("年を1つ以上選択してください。")
            else:
                yearly_chart = build_yearly_month_compare_chart(
                    d_scope_all, ANNUAL_METRICS[metric_label], sorted(selected_years)
                ).properties(height=chart_height)
                st.altair_chart(yearly_chart, use_container_width=True)

    if show_mode == "表＋グラフ":
        st.markdown("")

    if show_mode in ["表＋グラフ", "表のみ"]:
        st.subheader("表")
        st.dataframe(table, use_container_width=True, hide_index=True, height=560)

    st.divider()
    st.caption("出典：観光庁『宿泊旅行統計調査』（推移表Excelを取得して整形）")


if __name__ == "__main__":
    main()

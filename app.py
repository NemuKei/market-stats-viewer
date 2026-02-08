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


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    if not SQLITE_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(SQLITE_PATH)) as conn:
            df = pd.read_sql_query("SELECT * FROM market_stats", conn)
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


def build_monthly_stacked_chart(df_filtered: pd.DataFrame) -> alt.Chart:
    work = add_year_month_columns(df_filtered[["ym", "jp", "foreign"]])
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
            x=alt.X("ym:N", title="年月", sort=sorted(work["ym"].unique().tolist())),
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


def build_yearly_month_compare_chart(
    df_pref_all: pd.DataFrame, metric_col: str, selected_years: list[int]
) -> alt.Chart:
    month_sort = [f"{m:02d}" for m in range(1, 13)]
    work = add_year_month_columns(df_pref_all[["ym", "total", "jp", "foreign"]])
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
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        prefs = (
            df[["pref_code", "pref_name"]].drop_duplicates().sort_values("pref_code")
        )
        pref_label = prefs.apply(
            lambda r: f"{r['pref_code']} {r['pref_name']}", axis=1
        ).tolist()
        pref_map = dict(zip(pref_label, prefs["pref_code"].tolist()))
        pref_sel = st.selectbox("地域（全国/都道府県）", pref_label, index=0)

    with col2:
        ym_list = sorted(df["ym"].unique().tolist())
        ym_from = st.selectbox("開始年月", ym_list, index=max(0, len(ym_list) - 36))
        ym_to = st.selectbox("終了年月", ym_list, index=len(ym_list) - 1)

    with col3:
        show_mode = st.radio(
            "表示", ["表＋グラフ", "表のみ", "グラフのみ"], horizontal=True
        )

    pref_code = pref_map[pref_sel]
    d = df[
        (df["pref_code"] == pref_code) & (df["ym"] >= ym_from) & (df["ym"] <= ym_to)
    ].copy()
    d = d.sort_values("ym")
    d_pref_all = df[df["pref_code"] == pref_code].copy().sort_values("ym")

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
            if d.empty:
                st.info("指定した期間にデータがありません。")
            else:
                monthly_chart = build_monthly_stacked_chart(d).properties(
                    height=chart_height
                )
                st.altair_chart(monthly_chart, use_container_width=True)
        else:
            metric_map = {"全体": "total", "国内": "jp", "海外": "foreign"}
            metric_label = st.radio("指標", list(metric_map.keys()), horizontal=True)
            year_options = sorted(
                d_pref_all["ym"].str.slice(0, 4).astype(int).unique().tolist()
            )
            default_years = year_options[-4:] if len(year_options) > 4 else year_options
            selected_years = st.multiselect(
                "年（同月比較に使う年）",
                options=year_options,
                default=default_years,
            )

            if not selected_years:
                st.info("年を1つ以上選択してください。")
            else:
                yearly_chart = build_yearly_month_compare_chart(
                    d_pref_all, metric_map[metric_label], sorted(selected_years)
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

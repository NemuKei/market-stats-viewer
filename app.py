from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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

    # 表（年月縦）
    table = d[["ym", "total", "jp", "foreign"]].copy()
    table = table.rename(
        columns={"ym": "年月", "total": "全体", "jp": "国内", "foreign": "海外"}
    )

    # グラフ（簡易：st.line_chart）
    chart_df = table.set_index("年月")

    left, right = st.columns([1, 1])
    if show_mode in ["表＋グラフ", "表のみ"]:
        with left:
            st.subheader("表")
            st.dataframe(table, use_container_width=True, hide_index=True)

    if show_mode in ["表＋グラフ", "グラフのみ"]:
        with right:
            st.subheader("グラフ")
            st.line_chart(chart_df)

    st.divider()
    st.caption("出典：観光庁『宿泊旅行統計調査』（推移表Excelを取得して整形）")


if __name__ == "__main__":
    main()

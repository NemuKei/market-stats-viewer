"""Manual browser regression: real menu with slow, data-free route rendering.

Run from the repo root with PYTHONPATH=. python -m streamlit run
tests/fixtures/menu_browser_app.py --server.address 127.0.0.1 --server.port 8765.
"""

import json
import time

import streamlit as st

import app


def slow_route(label):
    def render():
        st.header(label)
        st.code(
            json.dumps(
                {key: st.session_state.get(key) for key in (
                    "_active_dataset", "_stats_sel", "_ref_sel"
                )},
                ensure_ascii=False,
            ),
            language="json",
        )
        st.caption("描画中")
        time.sleep(3)
        st.success(f"描画完了: {label}")

    return render


for label, name in (
    (app.DATASET_LABEL_STAY, "render_stay_stats_view"),
    (app.DATASET_LABEL_TCD, "render_tcd_view"),
    (app.DATASET_LABEL_ICD, "render_icd_view"),
    (app.DATASET_LABEL_AIRPORT_VOLUME, "render_airport_volume_view"),
    (app.DATASET_LABEL_TA, "render_ta_view"),
    (app.DATASET_LABEL_EVENTS_OFFICIAL, "render_events_view"),
    (app.DATASET_LABEL_EVENTS_SIGNALS, "render_event_signals_view"),
):
    setattr(app, name, slow_route(label))

app.main()

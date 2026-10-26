"""Cross-menu events use real Streamlit widgets, callbacks and SessionState."""

import pytest
import streamlit as st
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

import app


ROUTES = {
    "宿泊旅行統計調査": "render_stay_stats_view",
    "旅行・観光消費動向調査": "render_tcd_view",
    "インバウンド消費動向調査": "render_icd_view",
    "空港別入国者数": "render_airport_volume_view",
    "旅行業者取扱額": "render_ta_view",
    "全国イベント情報（会場公式）": "render_events_view",
    "全国イベント速報（ニュース）": "render_event_signals_view",
}


@pytest.fixture
def page(monkeypatch):
    # Keep the real menu and routing, replacing only data rendering with a
    # visible marker so navigation tests neither read nor regenerate data.
    for name in ROUTES.values():
        monkeypatch.setattr(app, name, lambda name=name: st.caption(name))
    return AppTest.from_string("import app\napp.main()")


def assert_selected(page, selected):
    assert not page.exception, [item.message for item in page.exception]
    assert page.session_state["_active_dataset"] == selected
    assert [
        item.value for item in page.caption if item.value in ROUTES.values()
    ] == [ROUTES[selected]]
    assert sum(widget.value is not None for widget in page.radio) == 1


@pytest.mark.parametrize(
    "stats_choice,ref_choice",
    [
        ("空港別入国者数", "全国イベント情報（会場公式）"),
        ("旅行業者取扱額", "全国イベント速報（ニュース）"),
    ],
)
@pytest.mark.parametrize("initial_ref", [False, True])
@pytest.mark.parametrize("reverse_order", [False, True])
def test_coalesced_menu_events_keep_last_callback_selection(
    page, stats_choice, ref_choice, initial_ref, reverse_order
):
    if initial_ref:
        page.session_state["_active_dataset"] = (
            "全国イベント速報（ニュース）"
            if ref_choice == "全国イベント情報（会場公式）"
            else "全国イベント情報（会場公式）"
        )
    page.run()
    assert not page.exception
    # Two user changes arrive before the next rerun, as with rapid clicks or
    # delayed transport. AppTest normally sends widget states in DOM order.
    page.radio(key="_stats_sel").set_value(stats_choice)
    page.radio(key="_ref_sel").set_value(ref_choice)
    if reverse_order:
        # The pinned Streamlit runner consumes this same protobuf transport.
        # Reverse only its order; keep callback execution and state real.
        incoming = page._tree.get_widget_states()
        page._run(WidgetStates(widgets=list(reversed(incoming.widgets))))
    else:
        page.run()
    selected = stats_choice if reverse_order else ref_choice
    assert_selected(page, selected)
    page.run()
    assert_selected(page, selected)


@pytest.mark.parametrize("reverse_route_order", [False, True])
def test_sequential_navigation_visits_all_routes_and_preserves_selection(
    page, reverse_route_order
):
    page.run()
    routes = list(ROUTES)
    if reverse_route_order:
        routes.reverse()
    for selected in [*routes, "宿泊旅行統計調査"]:
        key = "_ref_sel" if selected.startswith("全国イベント") else "_stats_sel"
        page.radio(key=key).set_value(selected).run()
        assert_selected(page, selected)


@pytest.mark.parametrize("select_reference", [False, True])
def test_cross_menu_change_explicitly_clears_the_browser_selection(
    page, select_reference
):
    if not select_reference:
        page.session_state["_active_dataset"] = "全国イベント速報（ニュース）"
    page.run()
    selected = (
        "全国イベント情報（会場公式）"
        if select_reference
        else "インバウンド消費動向調査"
    )
    active_key = "_ref_sel" if select_reference else "_stats_sel"
    inactive_key = "_stats_sel" if select_reference else "_ref_sel"
    page.radio(key=active_key).set_value(selected).run()
    assert_selected(page, selected)
    # Server-side None alone leaves an existing browser mark intact. The real
    # radio delta must explicitly request a reset with no selected value.
    inactive = page.radio(key=inactive_key)
    assert inactive.proto.set_value
    assert not inactive.proto.HasField("value")
    page.run()
    assert_selected(page, selected)

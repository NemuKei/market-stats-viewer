"""Navigation uses real Streamlit widget transport and SessionState."""

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
    assert len(page.radio) == 1
    assert page.radio(key="_active_dataset").value == selected


@pytest.mark.parametrize(
    "choices",
    [
        ("全国イベント情報（会場公式）", "インバウンド消費動向調査"),
        ("インバウンド消費動向調査", "全国イベント情報（会場公式）"),
        ("全国イベント速報（ニュース）", "旅行業者取扱額"),
        ("旅行業者取扱額", "全国イベント速報（ニュース）"),
        tuple(ROUTES),
        tuple(reversed(ROUTES)),
    ],
)
@pytest.mark.parametrize("initial_ref", [False, True])
def test_pending_menu_changes_transport_only_the_last_selection(page, choices, initial_ref):
    if initial_ref:
        page.session_state["_active_dataset"] = "全国イベント速報（ニュース）"
    page.run()
    assert len(page.radio) == 1
    for selected in choices:
        page.radio(key="_active_dataset").set_value(selected)
    incoming = page._tree.get_widget_states()
    # Native radios share one group; pending changes cannot include a second
    # group reset (None) that later overwrites the user's selection.
    assert len(incoming.widgets) == 1
    page._run(WidgetStates(widgets=incoming.widgets))
    assert_selected(page, choices[-1])
    # Re-delivery and ordinary reruns keep the same choice and visible route.
    page._run(WidgetStates(widgets=incoming.widgets))
    page.run()
    assert_selected(page, choices[-1])


@pytest.mark.parametrize("reverse_route_order", [False, True])
def test_sequential_navigation_visits_all_routes_and_preserves_selection(
    page, reverse_route_order
):
    page.run()
    routes = list(ROUTES)
    if reverse_route_order:
        routes.reverse()
    widget_id = page.radio(key="_active_dataset").proto.id
    for selected in [*routes, "宿泊旅行統計調査"]:
        page.radio(key="_active_dataset").set_value(selected).run()
        assert_selected(page, selected)
        # A stable identity keeps in-flight input attached to the same widget.
        assert page.radio(key="_active_dataset").proto.id == widget_id


@pytest.mark.parametrize("previous", [None, "obsolete", "全国イベント情報（会場公式）"])
def test_existing_session_keeps_a_valid_choice_and_recovers_an_invalid_one(page, previous):
    page.session_state["_active_dataset"] = previous
    # Old browser sessions may still contain keys from the two-group menu.
    page.session_state["_stats_sel"] = None
    page.session_state["_ref_sel"] = "全国イベント速報（ニュース）"
    page.run()
    assert_selected(page, previous if previous in ROUTES else "宿泊旅行統計調査")
    assert page.radio(key="_active_dataset").options == list(ROUTES)

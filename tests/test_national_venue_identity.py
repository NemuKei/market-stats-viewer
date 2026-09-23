"""Guard the historical Ajinomoto ID without re-keying stored performances."""

import csv
import json
from pathlib import Path
import sqlite3

from scripts.audit_national_event_coverage import read_inputs
from scripts.signals.entity_aliases import (
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
)


DATA = Path(__file__).resolve().parents[1] / "data"


def test_renamed_hall_and_toki_punctuation_keep_existing_identity():
    keep, compact = load_venue_lookup_maps()
    for name in ("クロコくんホール", "クロコくんホール（旧日本ガイシホール）"):
        assert normalize_venue_with_lookup(name, keep, compact)[0] == "日本ガイシホール"
    assert (
        normalize_venue_with_lookup("クロコくんアリーナ", keep, compact)[0]
        != "日本ガイシホール"
    )
    assert (
        normalize_venue_with_lookup(
            "朱鷺メッセ・新潟コンベンションセンター", keep, compact
        )[0]
        == "朱鷺メッセ 新潟コンベンションセンター"
    )


def test_operator_reviewed_venues_keep_arena_and_stadium_distinct():
    with (DATA / "venue_registry.csv").open() as handle:
        registry = {r["venue_id"]: r for r in csv.DictReader(handle)}
    assert registry["sundome_fukui"]["capacity"] == "9000"
    assert registry["hiroshima_green_arena"]["capacity"] == "10000"
    assert registry["ecopa_stadium"]["capacity"] == "50889"
    for key in ("sundome_fukui", "hiroshima_green_arena", "ecopa_stadium"):
        assert registry[key]["is_enabled"] == "0"
    keep, compact = load_venue_lookup_maps()
    assert (
        normalize_venue_with_lookup("静岡エコパアリーナ", keep, compact)[0]
        == "エコパアリーナ"
    )
    assert (
        normalize_venue_with_lookup("静岡スタジアム", keep, compact)[0]
        == "エコパスタジアム"
    )
    assert (
        normalize_venue_with_lookup("広島県立総合体育館 大アリーナ", keep, compact)[0]
        == "広島グリーンアリーナ"
    )
    # A hall with unknown concert capacity remains separately resolvable.
    assert "portmesse_nagoya" in registry
    assert registry["portmesse_nagoya_hall1"]["capacity"] == ""
    assert (
        normalize_venue_with_lookup("名古屋市国際展示場 第1展示館", keep, compact)[0]
        == "ポートメッセなごや 第1展示館"
    )
    assert (
        normalize_venue_with_lookup("ポートメッセなごや", keep, compact)[0]
        != "ポートメッセなごや 第1展示館"
    )
    assert (
        normalize_venue_with_lookup("ハピネスアリーナ", keep, compact)[0]
        == "HAPPINESS ARENA"
    )
    assert (
        normalize_venue_with_lookup("PEACE STADIUM", keep, compact)[0]
        != "HAPPINESS ARENA"
    )


def test_national_watch_uses_national_id_and_keeps_ajinomoto_ticket_page():
    config = json.loads((DATA / "venue_web_discovery_config.json").read_text())
    watches = {r["venue_id"]: r for r in config["watch_venues"]}
    assert "国立競技場" in watches["national_stadium"]["aliases"]
    with (DATA / "ticketjam_venue_pages.csv").open() as handle:
        tickets = {r["venue_id"]: r for r in csv.DictReader(handle)}
    assert tickets["mufg_stadium"]["venue_name"] == "味の素スタジアム"
    assert (
        tickets["mufg_stadium"]["ticketjam_venue_url"]
        == "https://ticketjam.jp/venues/6816"
    )
    assert (
        tickets["national_stadium"]["ticketjam_venue_url"]
        == "https://ticketjam.jp/venues/6834"
    )
    report = read_inputs(
        DATA / "venue_registry.csv",
        DATA / "venue_web_discovery_config.json",
        DATA / "ticketjam_venue_pages.csv",
    )
    assert not report["identity_conflicts"]
    assert not report["name_reviews"]


def test_legacy_id_and_source_strategy_stay_bound_to_ajinomoto():
    with (DATA / "venue_registry.csv").open() as handle:
        registry = {r["venue_id"]: r for r in csv.DictReader(handle)}
    assert registry["mufg_stadium"]["venue_name"] == "味の素スタジアム"
    assert (
        json.loads(registry["mufg_stadium"]["config_json"])["strategy"]
        == "mufg_stadium_schedule"
    )
    keep, compact = load_venue_lookup_maps()
    assert (
        normalize_venue_with_lookup("MUFGスタジアム", keep, compact)[0] == "国立競技場"
    )
    assert normalize_venue_with_lookup("味スタ", keep, compact)[0] == "味の素スタジアム"
    with sqlite3.connect(
        (DATA / "events.sqlite").as_uri() + "?mode=ro", uri=True
    ) as conn:
        rows = conn.execute(
            "SELECT source_url FROM events WHERE venue_id = ?", ("mufg_stadium",)
        ).fetchall()
    assert rows
    assert all(url.startswith("https://www.ajinomotostadium.com/") for (url,) in rows)

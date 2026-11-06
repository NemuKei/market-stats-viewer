import argparse
import csv

import pytest
import requests

from scripts import build_artist_registry_wikidata as builder


def payload(qid="Q1", name="Artist", aliases="Alias"):
    return {
        "results": {
            "bindings": [
                {
                    "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
                    "itemLabel": {"value": name},
                    "aliases": {"value": aliases},
                }
            ]
        }
    }


def mock_japan_payload(params):
    if "ids" in params:
        return {
            "entities": {
                q: {
                    "id": q,
                    "labels": {"en": {"value": "Artist" if q == "Q1" else "Group"}},
                    "aliases": {"en": [{"value": "Alias"}]},
                }
                for q in params["ids"].split("|")
            }
        }
    if "?occupation WHERE" in params["query"]:
        return {
            "results": {
                "bindings": [
                    {"occupation": {"value": "http://www.wikidata.org/entity/Q177220"}}
                ]
            }
        }
    return payload("Q1") if "wdt:P106" in params["query"] else payload("Q2", "Group")


def test_japan_fetches_ids_before_attributes_and_deduplicates(monkeypatch):
    calls = []

    def fetch(endpoint, params, request_timeout, *args, **kwargs):
        calls.append(params)
        return mock_japan_payload(params)

    monkeypatch.setattr(builder, "_fetch_json_with_retry", fetch)
    rows = builder.fetch_seed_rows(["jp"], 90)
    assert len(calls) == 4
    assert "?occupation WHERE" in calls[0]["query"]
    assert all(
        "itemLabel" not in p["query"] and "GROUP BY" not in p["query"]
        for p in calls[:3]
    )
    assert calls[3]["ids"] == "Q1|Q2"
    assert [r["artist_id"] for r in rows] == ["wd:Q1", "wd:Q2"]


@pytest.mark.parametrize("countries", [[], ["kr"]])
def test_non_japanese_queries_remain_single_request(monkeypatch, countries):
    calls = []

    def fetch(endpoint, query, request_timeout, **kwargs):
        calls.append(query)
        return payload()

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
    assert builder.fetch_seed_rows(countries, 60)
    assert calls == [builder.build_country_filtered_query(countries)]


@pytest.fixture
def cli_paths(tmp_path, monkeypatch):
    output = tmp_path / "seed.csv"
    manual = tmp_path / "manual.csv"
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    monkeypatch.setattr(builder, "MANUAL_PATH", manual)
    monkeypatch.setattr(
        builder,
        "parse_args",
        lambda: argparse.Namespace(
            countries="jp", output=str(output), request_timeout=60
        ),
    )
    return output, manual


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
@pytest.mark.parametrize("failure", ["timeout", "malformed"])
def test_incomplete_fetch_preserves_seed_and_manual(
    cli_paths, monkeypatch, fail_at, failure
):
    output, manual = cli_paths
    output.write_text("existing seed", encoding="utf-8")
    manual.write_text("existing manual", encoding="utf-8")
    calls = 0

    def fetch(endpoint, params, request_timeout, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            if failure == "timeout":
                raise RuntimeError("Wikidata fetch failed after 5 attempts")
            return {}
        return mock_japan_payload(params)

    monkeypatch.setattr(builder, "_fetch_json_with_retry", fetch)
    with pytest.raises(RuntimeError):
        builder.main()
    assert output.read_text(encoding="utf-8") == "existing seed"
    assert manual.read_text(encoding="utf-8") == "existing manual"


def test_success_writes_both_kinds_and_preserves_watch_settings(cli_paths, monkeypatch):
    output, _ = cli_paths
    old = builder.build_seed_rows(payload())[0]
    old.update(
        updated_at="2026-01-01",
        ticketjam_watch=1,
        ticketjam_benchmark_tier="A",
        ticketjam_watch_reason="reviewed",
    )
    builder.write_seed_csv_noop([old], output)
    monkeypatch.setattr(
        builder,
        "_fetch_json_with_retry",
        lambda endpoint, params, *a, **k: mock_japan_payload(params),
    )
    builder.main()
    with output.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["artist_id"] for r in rows] == ["wd:Q1", "wd:Q2"]
    assert rows[0]["updated_at"] == "2026-01-01"
    assert rows[0]["ticketjam_watch"] == "1"
    assert rows[0]["ticketjam_benchmark_tier"] == "A"
    assert rows[0]["ticketjam_watch_reason"] == "reviewed"


def test_timeout_retries_then_success(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise requests.ReadTimeout("test timeout")

        class Response:
            status_code = 200

            def json(self):
                return payload()

        return Response()

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)
    assert (
        builder.fetch_sparql_with_retry(
            "https://example.test", "query", request_timeout=90
        )
        == payload()
    )
    assert calls == [90, 90]


def test_timeout_exhaustion(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        raise requests.ReadTimeout("test timeout")

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="after 5 attempts"):
        builder.fetch_sparql_with_retry("https://example.test", "query")
    assert len(calls) == 5


@pytest.mark.parametrize("reason", ["deadline", "name"])
def test_late_validation_failure_keeps_seed_and_manual(cli_paths, monkeypatch, reason):
    output, manual = cli_paths
    builder.write_seed_csv_noop(builder.build_seed_rows(payload()), output)
    manual.write_bytes(b"unchanged manual\n")
    seed_before = output.read_bytes()
    clock = [0.0]
    monkeypatch.setattr(builder.time, "monotonic", lambda: clock[0])

    def fetch(endpoint, params, *args, **kwargs):
        result = mock_japan_payload(params)
        if "ids" in params:
            if reason == "deadline":
                clock[0] = builder.MAX_FETCH_SECONDS + 1
            else:
                result["entities"]["Q1"]["labels"] = {}
        return result

    monkeypatch.setattr(builder, "_fetch_json_with_retry", fetch)
    with pytest.raises(RuntimeError, match="deadline|name.*guard"):
        builder.main()
    assert output.read_bytes() == seed_before
    assert manual.read_bytes() == b"unchanged manual\n"

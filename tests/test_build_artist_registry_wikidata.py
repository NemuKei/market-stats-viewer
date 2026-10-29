import argparse
import csv
import json

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


def test_japan_queries_split_person_and_group_and_merge_aliases(monkeypatch):
    calls = []

    def fetch(endpoint, query, request_timeout):
        calls.append((endpoint, query, request_timeout))
        return payload(aliases="One") if len(calls) == 1 else payload(aliases="Two")

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
    rows = builder.fetch_seed_rows(["jp"], 90)
    assert len(calls) == 2
    assert all(
        "UNION" not in query and "wd:Q17" in query and timeout == 90
        for _, query, timeout in calls
    )
    assert "wdt:P106/wdt:P279* wd:Q639669" in calls[0][1]
    assert "wdt:P495 ?country" not in calls[0][1]
    assert "wdt:P495 ?country" in calls[1][1]
    assert "wdt:P106" not in calls[1][1]
    assert len(rows) == 1
    assert json.loads(rows[0]["aliases_json"]) == ["One", "Two"]


@pytest.mark.parametrize("countries", [[], ["kr"]])
def test_non_japanese_queries_remain_single_request(monkeypatch, countries):
    calls = []

    def fetch(endpoint, query, request_timeout):
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


@pytest.mark.parametrize("fail_at", [1, 2])
@pytest.mark.parametrize("failure", ["timeout", "empty", "malformed"])
def test_incomplete_fetch_preserves_seed_and_manual(
    cli_paths, monkeypatch, fail_at, failure
):
    output, manual = cli_paths
    output.write_text("existing seed", encoding="utf-8")
    manual.write_text("existing manual", encoding="utf-8")
    calls = 0

    def fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            if failure == "timeout":
                raise RuntimeError("Wikidata fetch failed after 5 attempts")
            return {} if failure == "malformed" else {"results": {"bindings": []}}
        return payload()

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
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
    replies = iter([payload(), payload("Q2", "Group")])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
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

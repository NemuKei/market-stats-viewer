"""Fetch boundaries: incomplete or partial Wikidata data must not replace a seed."""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from scripts import build_artist_registry_wikidata as b


def ids(*qids, key="item"):
    return {
        "results": {
            "bindings": [
                {key: {"value": f"http://www.wikidata.org/entity/{q}"}} for q in qids
            ]
        }
    }


class Response:
    def __init__(self, body=None, status=200, headers=None, text=""):
        self.body, self.status_code = body, status
        self.headers, self.text = headers or {}, text

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_occupation_batches_cover_boundaries_once():
    qids = ["Q639669", "Q177220"] + [f"Q{i}" for i in range(1, 102)]
    batches = b.occupation_batches(qids + ["Q1"])
    assert batches[:2] == [["Q639669"], ["Q177220"]]
    assert [len(x) for x in batches] == [1, 1, 50, 50, 1]
    flat = [q for batch in batches for q in batch]
    assert len(flat) == len(set(flat)) == 103
    assert set(flat) == set(qids)


def test_ids_split_timeouts_keep_empty_batches_and_deduplicate(monkeypatch):
    queries = []

    def fetch(endpoint, query, **kwargs):
        queries.append(query)
        if "wd:Q100 wd:Q200" in query:
            raise b.WikidataQueryTimeout("timeout")
        if "wd:Q100" in query:
            return ids("Q1", "Q1")
        return ids()

    monkeypatch.setattr(b, "fetch_sparql_with_retry", fetch)
    assert b.fetch_artist_ids(["jp"], "person", ["Q100", "Q200"], 60) == {"Q1"}
    assert len(queries) == 3
    assert all(
        "itemLabel" not in q and "GROUP BY" not in q and "altLabel" not in q
        for q in queries
    )
    assert all("wdt:P31 wd:Q5" in q for q in queries)


def test_single_occupation_timeout_covers_qid_prefix_and_exact_boundary(monkeypatch):
    # Q1 itself must survive subdivision of Q1*, alongside Q10 and Q19.
    def fetch(endpoint, query, **kwargs):
        if "STRSTARTS" not in query and "VALUES ?item" not in query:
            raise b.WikidataQueryTimeout("timeout")
        if 'entity/Q1"' in query:
            raise b.WikidataQueryTimeout("timeout")
        if "VALUES ?item { wd:Q1 }" in query:
            return ids("Q1")
        if 'entity/Q10"' in query:
            return ids("Q10")
        if 'entity/Q19"' in query:
            return ids("Q19")
        return ids()

    monkeypatch.setattr(b, "fetch_sparql_with_retry", fetch)
    assert b.fetch_artist_ids(["jp"], "person", ["Q177220"], 60) == {"Q1", "Q10", "Q19"}


def test_non_timeout_does_not_split_and_hide_failure(monkeypatch):
    def fail(*a, **k):
        raise RuntimeError("invalid response")

    monkeypatch.setattr(b, "fetch_sparql_with_retry", fail)
    with pytest.raises(RuntimeError, match="invalid response"):
        b.fetch_artist_ids(["jp"], "person", ["Q1", "Q2"], 60)


def test_entity_requests_at_most_50_and_language_fallback(monkeypatch):
    batches = []

    def get(url, params, headers, timeout):
        batch = params["ids"].split("|")
        batches.append(batch)
        assert params["maxlag"] == 5 and params["languages"] == "ja|en|ko|mul"
        assert headers["User-Agent"] == b.USER_AGENT
        return Response(
            {
                "entities": {
                    q: {
                        "id": q,
                        "labels": {"en": {"value": "Name " + q}},
                        "aliases": {"ja": [{"value": "別名"}]},
                    }
                    for q in batch
                }
            }
        )

    monkeypatch.setattr(b.requests, "get", get)
    monkeypatch.setattr(b.time, "sleep", lambda _: None)
    rows = b.fetch_entity_rows({f"Q{i}" for i in range(1, 52)}, 60)
    assert [len(x) for x in batches] == [50, 1]
    assert len(rows) == 51 and len({r["artist_id"] for r in rows}) == 51
    assert rows[0]["canonical_name"].startswith("Name Q")
    assert json.loads(rows[0]["aliases_json"]) == ["別名"]


@pytest.mark.parametrize(
    "body",
    [
        {"entities": {}},
        {"entities": {"Q1": {"missing": ""}}},
        {"entities": {"Q1": {"labels": [], "aliases": {}}}},
    ],
)
def test_missing_or_malformed_entity_fails_closed(monkeypatch, body):
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: Response(body))
    monkeypatch.setattr(b.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError):
        b.fetch_entity_rows({"Q1"}, 60)


@pytest.mark.parametrize(
    "bad",
    [
        Response(ValueError("broken JSON")),
        Response({}, text="java.util.concurrent.TimeoutException"),
        Response({"results": {"bindings": "broken"}}),
    ],
)
def test_http200_invalid_sparql_is_failure(monkeypatch, bad):
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: bad)
    monkeypatch.setattr(b.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError):
        b.fetch_sparql_with_retry("https://example.test", "query", max_attempts=1)


@pytest.mark.parametrize(
    "retry_after",
    [
        "12",
        format_datetime(
            datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True
        ),
    ],
)
def test_429_retry_after_is_respected(monkeypatch, retry_after):
    replies = iter(
        [
            Response(status=429, headers={"Retry-After": retry_after}),
            Response(ids("Q1")),
        ]
    )
    waits = []
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: next(replies))
    monkeypatch.setattr(b.time, "sleep", waits.append)
    assert b.fetch_sparql_with_retry("https://example.test", "query") == ids("Q1")
    assert max(waits) >= 12


def test_api_maxlag_200_retries(monkeypatch):
    replies = iter(
        [
            Response(
                {"error": {"code": "maxlag", "lag": 9}}, headers={"Retry-After": "11"}
            ),
            Response({"entities": {"Q1": {"id": "Q1", "labels": {}, "aliases": {}}}}),
        ]
    )
    waits = []
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: next(replies))
    monkeypatch.setattr(b.time, "sleep", waits.append)
    assert b.fetch_entity_rows({"Q1"}, 60)[0]["canonical_name"] == "Q1"
    assert max(waits) >= 11


def seed_rows(qids):
    return [
        {"artist_id": f"wd:{q}", "canonical_name": q, "aliases_json": "[]"}
        for q in qids
    ]


def test_id_loss_guard_cannot_be_offset_by_new_ids(tmp_path):
    path = tmp_path / "seed.csv"
    b.write_seed_csv_noop(seed_rows([f"Q{i}" for i in range(1, 11)]), path)
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="guard"):
        b.validate_seed_size(seed_rows([f"Q{i}" for i in range(3, 13)]), path)
    assert path.read_bytes() == before
    b.validate_seed_size(seed_rows([f"Q{i}" for i in range(2, 11)]), path)


def test_watched_id_loss_fails_even_within_ten_percent(tmp_path):
    path = tmp_path / "seed.csv"
    rows = seed_rows([f"Q{i}" for i in range(1, 11)])
    rows[0]["ticketjam_watch"] = 1
    b.write_seed_csv_noop(rows, path)
    with pytest.raises(RuntimeError, match="watch"):
        b.validate_seed_size(rows[1:], path)


def test_id_query_retries_rate_limit_before_subdivision(monkeypatch):
    replies = iter(
        [Response(status=429, headers={"Retry-After": "13"}), Response(ids("Q1"))]
    )
    waits = []
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: next(replies))
    monkeypatch.setattr(b.time, "sleep", waits.append)
    assert b.fetch_artist_ids(["jp"], "person", ["Q177220"], 60) == {"Q1"}
    assert max(waits) >= 13


def test_later_attribute_batch_failure_preserves_files(tmp_path, monkeypatch):
    import argparse

    output, manual = tmp_path / "seed.csv", tmp_path / "manual.csv"
    output.write_bytes(b"existing seed\n")
    manual.write_bytes(b"existing manual\n")
    monkeypatch.setattr(b, "DATA_DIR", tmp_path)
    monkeypatch.setattr(b, "MANUAL_PATH", manual)
    monkeypatch.setattr(
        b,
        "parse_args",
        lambda: argparse.Namespace(
            countries="jp", output=str(output), request_timeout=60
        ),
    )
    monkeypatch.setattr(b.time, "sleep", lambda _: None)

    def get(url, params, **kwargs):
        if "query" in params:
            if "?occupation WHERE" in params["query"]:
                return Response(ids("Q177220", key="occupation"))
            return Response(ids(*[f"Q{i}" for i in range(1, 52)]))
        if params["ids"] == "Q51":
            raise requests.ReadTimeout("later API batch")
        return Response(
            {
                "entities": {
                    q: {"labels": {}, "aliases": {}} for q in params["ids"].split("|")
                }
            }
        )

    monkeypatch.setattr(b.requests, "get", get)
    with pytest.raises(RuntimeError):
        b.main()
    assert output.read_bytes() == b"existing seed\n"
    assert manual.read_bytes() == b"existing manual\n"


@pytest.mark.parametrize("language", ["ja", "en", "ko", "mul"])
def test_label_priority_includes_mul_but_alias_languages_stay_unchanged(
    monkeypatch, language
):
    order = ["ja", "en", "ko", "mul"]
    start = order.index(language)

    def get(url, params, **kwargs):
        assert "mul" in params["languages"].split("|")
        return Response(
            {
                "entities": {
                    "Q1": {
                        "labels": {
                            lang: {"value": lang + " name"} for lang in order[start:]
                        },
                        "aliases": {
                            lang: [{"value": lang + " alias"}] for lang in order
                        },
                    }
                }
            }
        )

    monkeypatch.setattr(b.requests, "get", get)
    monkeypatch.setattr(b.time, "sleep", lambda _: None)
    row = b.fetch_entity_rows({"Q1"}, 60)[0]
    assert row["canonical_name"] == language + " name"
    aliases = json.loads(row["aliases_json"])
    assert set(["ja alias", "en alias", "ko alias"]) <= set(aliases)
    assert "mul alias" not in aliases
    assert "mul name" not in aliases


def test_existing_named_id_cannot_degrade_to_qid(tmp_path):
    path = tmp_path / "seed.csv"
    b.write_seed_csv_noop(
        [{"artist_id": "wd:Q1", "canonical_name": "Named artist"}], path
    )
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="name.*guard"):
        b.validate_seed_size(seed_rows(["Q1"]), path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "retry_after",
    [
        "301",
        "21601",
        format_datetime(datetime(2099, 1, 1, tzinfo=timezone.utc), usegmt=True),
    ],
)
def test_excessive_retry_after_stops_without_sleep_or_second_request(
    monkeypatch, retry_after
):
    waits = []
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        return Response(status=429, headers={"Retry-After": retry_after})

    monkeypatch.setattr(b.requests, "get", get)
    monkeypatch.setattr(b.time, "sleep", waits.append)
    with pytest.raises(RuntimeError, match="wait.*limit"):
        b.fetch_sparql_with_retry("https://example.test", "query")
    assert calls == [1]
    assert waits == [5]


def test_request_deadline_stops_before_retry(monkeypatch):
    now = [0.0]
    waits = []
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        now[0] = 100.0
        return Response(status=429, headers={"Retry-After": "12"})

    monkeypatch.setattr(b.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(b.time, "sleep", waits.append)
    monkeypatch.setattr(b.requests, "get", get)
    with pytest.raises(RuntimeError, match="deadline"):
        b._fetch_json_with_retry("https://example.test", {}, 60, deadline=100.0)
    assert calls == [1] and waits == [5]


def test_expired_budget_stops_before_subdivision(monkeypatch):
    now = [0.0]
    calls = []

    def fetch(*args, **kwargs):
        calls.append(1)
        now[0] = 101.0
        raise b.WikidataQueryTimeout("timeout")

    monkeypatch.setattr(b.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(b, "fetch_sparql_with_retry", fetch)
    with pytest.raises(RuntimeError, match="deadline"):
        b.fetch_artist_ids(["jp"], "person", ["Q100", "Q200"], 60, deadline=100.0)
    assert calls == [1]


def test_partition_reserves_request_time_from_original_deadline(monkeypatch):
    monkeypatch.setattr(b.time, "monotonic", lambda: 80.0)
    monkeypatch.setattr(b.time, "sleep", lambda _: None)

    def unexpected_request(*args, **kwargs):
        raise AssertionError("not enough acquisition time to start a request")

    monkeypatch.setattr(b.requests, "get", unexpected_request)
    with pytest.raises(RuntimeError, match="deadline"):
        b.fetch_artist_ids(["jp"], "person", ["Q177220"], 60, deadline=100.0)

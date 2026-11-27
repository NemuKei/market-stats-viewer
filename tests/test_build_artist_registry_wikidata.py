import argparse
import csv
import json
from email.utils import formatdate
from io import BytesIO

import pytest
import requests

from scripts import build_artist_registry_wikidata as builder
from scripts.build_events_artist_inferred import infer_event_artist
from scripts.signals import artist_registry


def payload(qid="Q1", name="Artist", aliases="Alias"):
    return {
        "head": {"vars": ["item", "itemLabel", "aliases"]},
        "results": {
            "bindings": [
                {
                    "item": {
                        "type": "uri",
                        "value": f"http://www.wikidata.org/entity/{qid}",
                    },
                    "itemLabel": {"type": "literal", "value": name},
                    "aliases": {"type": "literal", "value": aliases},
                }
            ]
        },
    }


def test_japan_queries_split_person_and_group_and_merge_aliases(monkeypatch):
    calls = []

    def fetch(endpoint, query, request_timeout, **kwargs):
        calls.append((endpoint, query, request_timeout))
        return payload(aliases="One") if len(calls) == 1 else payload(aliases="Two")

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
    rows = builder.fetch_seed_rows(["jp"], 90)
    assert len(calls) == 2
    assert all(url == "https://query-next.wikidata.org/sparql" for url, _, _ in calls)
    assert all('wikibase:language "ja,en,ko,mul"' in query for _, query, _ in calls)
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
        calls.append((endpoint, query))
        return payload()

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
    assert builder.fetch_seed_rows(countries, 60)
    assert calls == [
        (
            "https://query.wikidata.org/sparql",
            builder.build_country_filtered_query(countries),
        )
    ]
    assert "[AUTO_LANGUAGE]" in calls[0][1]


@pytest.fixture
def cli_paths(tmp_path, monkeypatch):
    output = tmp_path / "seed.csv"
    manual = tmp_path / "manual.csv"
    monkeypatch.setattr(artist_registry, "SEED_PATH", tmp_path / "korea.csv")
    monkeypatch.setattr(artist_registry, "JP_SEED_PATH", output)
    monkeypatch.setattr(artist_registry, "MANUAL_PATH", manual)
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
            return (
                {}
                if failure == "malformed"
                else {"head": payload()["head"], "results": {"bindings": []}}
            )
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


def seed_row(qid, name, aliases="", **fields):
    row = builder.build_seed_rows(payload(qid, name, aliases))[0]
    return dict(row, updated_at="2026-01-01", **fields)


def replies_for(*groups):
    return iter(
        {
            "head": payload()["head"],
            "results": {
                "bindings": [
                    payload(*row)["results"]["bindings"][0]
                    if len(row) == 3
                    else payload(*row, aliases="")["results"]["bindings"][0]
                    for row in group
                ]
            },
        }
        for group in groups
    )


def read_rows(path):
    with path.open(encoding="utf-8") as handle:
        return {row["artist_id"]: row for row in csv.DictReader(handle)}


def test_japan_keeps_ids_old_names_alias_order_and_dates(cli_paths, monkeypatch):
    output, _ = cli_paths
    prior = [
        seed_row("Q65234099", "おこさまぷれ〜と。"),
        seed_row("Q972792", "KinKi Kids", "Z old|DOMOTO|KANZAI BOYA"),
        seed_row("Q30930490", "緑黄色社会", "リョクシャカ|RyokuShaka"),
        seed_row("Q61989561", "milet", "ミレイ|Milet"),
        seed_row("Q10864039", "Original Love", "オリジナル・ラブ|オリジナルラブ"),
        seed_row("Q777", "Existing name", "Existing alias"),
        seed_row("Q8", "Other eight"),
        seed_row("Q9", "Other nine"),
        seed_row("Q10", "Other ten"),
        seed_row("Q11", "Other eleven"),
    ]
    builder.write_seed_csv_noop(prior, output)
    original = read_rows(output)
    people = [
        ("Q61989561", "milet", "Milet|ミレイ"),
        ("Q777", "Q777"),
        ("Q8", "Other eight"),
        ("Q9", "Other nine"),
    ]
    groups = [
        ("Q972792", "DOMOTO", "Z new|KANZAI BOYA|A new"),
        ("Q30930490", "緑黄色社会", "RyokuShaka"),
        ("Q10864039", "Original Love"),
        ("Q10", "Other ten"),
        ("Q11", "Other eleven"),
        ("Q12", "New group", "Z alias|A alias"),
    ]
    replies = replies_for(people, groups, people, groups)
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
    )
    builder.main()
    rows = read_rows(output)
    for qid in ("Q65234099", "Q30930490", "Q61989561", "Q10864039", "Q777"):
        assert rows[f"wd:{qid}"] == original[f"wd:{qid}"]
    renamed = rows["wd:Q972792"]
    assert renamed["canonical_name"] == "DOMOTO"
    assert json.loads(renamed["aliases_json"]) == [
        "Z old",
        "KANZAI BOYA",
        "A new",
        "KinKi Kids",
        "Z new",
    ]
    assert renamed["updated_at"] != original["wd:Q972792"]["updated_at"]
    assert json.loads(rows["wd:Q12"]["aliases_json"]) == ["A alias", "Z alias"]
    index = artist_registry.build_artist_index(artist_registry.load_registry())
    cases = [
        (
            "おこさまぷれ〜と。10th Anniversary Year 東阪 Zepp Tour『いただきます♾️』",
            "おこさまぷれ〜と。",
        ),
        ("リョクシャカ LIVE", "緑黄色社会"),
        ("ミレイ LIVE", "milet"),
        ("オリジナル・ラブ コンサート", "Original Love"),
        ("KinKi Kids", "DOMOTO"),
    ]
    for title, expected in cases:
        result = infer_event_artist(title, "", index)
        assert result is not None and result[0] == expected, title
    first_write = output.read_bytes()
    builder.main()
    assert output.read_bytes() == first_write


def test_retained_redirect_sources_and_targets_resolve_by_name(cli_paths, monkeypatch):
    output, _ = cli_paths
    redirects = [
        ("Q16263866", "Q12605170", "あるるかん", "あるるかん"),
        ("Q24869422", "Q24343977", "I HATE MONDAYS", "I HATE MONDAYS"),
        ("Q83215390", "Q55730540", "Vivid undress", "Vivid undress"),
        ("Q110688501", "Q11562218", "Miwako Watanabe", "渡辺實和子"),
    ]
    unaffected = [(f"Q{i}", f"Artist {i}") for i in range(1, 37)]
    prior = [seed_row(source, old_name) for source, _, old_name, _ in redirects]
    prior.extend(seed_row(*entry) for entry in unaffected)
    builder.write_seed_csv_noop(prior, output)
    people = [
        *unaffected[:18],
        *((target, name) for _, target, _, name in redirects[:1] + redirects[3:]),
    ]
    groups = [
        *unaffected[18:],
        *((target, name) for _, target, _, name in redirects[1:3]),
    ]
    replies = replies_for(people, groups)
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
    )
    builder.main()
    entries = {entry.artist_id: entry for entry in artist_registry.load_registry()}
    index = artist_registry.build_artist_index(list(entries.values()))
    for source, target, old_name, new_name in redirects:
        assert entries[f"wd:{source}"].canonical_name == old_name
        assert entries[f"wd:{target}"].canonical_name == new_name
        for name in (old_name, new_name):
            result = infer_event_artist(f"{name} LIVE", "", index)
            assert result is not None and result[0] == name


@pytest.mark.parametrize("new_ids", [[], ["Q101", "Q102", "Q103"]])
def test_low_japan_coverage_cannot_be_hidden_by_merging_or_new_ids(
    cli_paths, monkeypatch, new_ids
):
    output, _ = cli_paths
    builder.write_seed_csv_noop(
        [seed_row(f"Q{i}", f"Artist {i}") for i in range(1, 11)], output
    )
    original = output.read_bytes()
    retained = [(f"Q{i}", f"Artist {i}") for i in range(1, 9)]
    replies = replies_for(retained[:4], retained[4:] + [(qid, qid) for qid in new_ids])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
    )
    with pytest.raises(RuntimeError, match="coverage"):
        builder.main()
    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("setting", "value"),
    [("ticketjam_watch", 1), ("ticketjam_benchmark_tier", "reference")],
)
def test_japan_update_cannot_hide_a_monitored_korean_entry(
    cli_paths, monkeypatch, setting, value
):
    output, _ = cli_paths
    korea = artist_registry.SEED_PATH
    builder.write_seed_csv_noop([seed_row("Q1", "Watched", **{setting: value})], korea)
    builder.write_seed_csv_noop([seed_row("Q2", "Existing JP")], output)
    original = output.read_bytes()
    original_korea = korea.read_bytes()
    replies = replies_for([("Q1", "Watched")], [("Q2", "Existing JP")])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
    )
    with pytest.raises(RuntimeError, match="monitoring.*wd:Q1"):
        builder.main()
    assert output.read_bytes() == original
    assert korea.read_bytes() == original_korea


@pytest.mark.parametrize(
    ("status", "retry_after", "expected_wait"),
    [
        (429, "17", 17),
        (503, formatdate(1_800_000_030, usegmt=True), 30),
        (429, None, 60),
        pytest.param(429, "9" * 310, 60, id="float-overflow"),
        pytest.param(429, "9" * 5000, 60, id="integer-digit-limit"),
    ],
)
def test_japan_v2_respects_retry_after_and_identifies_the_client(
    monkeypatch, status, retry_after, expected_wait
):
    responses = [requests.Response(), requests.Response()]
    responses[0].status_code = status
    if retry_after is not None:
        responses[0].headers["Retry-After"] = retry_after
    responses[1].status_code = 200
    responses[1]._content = json.dumps(payload()).encode()
    responses[0].raw = BytesIO()
    responses[1].raw = BytesIO(responses[1]._content)
    calls = []
    waits = []

    def get(endpoint, **kwargs):
        calls.append((endpoint, kwargs["headers"]))
        return responses.pop(0)

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "sleep", waits.append)
    monkeypatch.setattr(builder.time, "time", lambda: 1_800_000_000)
    monkeypatch.setattr(builder.random, "uniform", lambda *a: 0)
    endpoint = "https://query-next.wikidata.org/sparql"
    assert builder.fetch_sparql_with_retry(endpoint, "query") == payload()
    assert waits == [expected_wait]
    assert len(calls) == 2
    assert all(
        url == endpoint
        and headers["User-Agent"] == builder.USER_AGENT
        and headers["Accept"] == "application/sparql-results+json"
        for url, headers in calls
    )


def test_mixed_country_mode_keeps_legacy_endpoint_and_both_countries(monkeypatch):
    calls = []

    def fetch(endpoint, query, request_timeout):
        calls.append((endpoint, query))
        return payload()

    monkeypatch.setattr(builder, "fetch_sparql_with_retry", fetch)
    assert builder.fetch_seed_rows(["jp", "kr"], 60)
    assert len(calls) == 2
    for endpoint, query in calls:
        assert endpoint == "https://query.wikidata.org/sparql"
        assert "wd:Q17 wd:Q884" in query and "[AUTO_LANGUAGE]" in query


def test_japan_cli_defaults_to_japan_seed_without_replacing_korean_seed(
    tmp_path, monkeypatch
):
    korean = tmp_path / "artist_registry.seed.csv"
    japan = tmp_path / "artist_registry.jp.seed.csv"
    builder.write_seed_csv_noop([seed_row("Q1", "Korean")], korean)
    original_korean = korean.read_bytes()
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    monkeypatch.setattr(builder, "SEED_PATH", korean)
    monkeypatch.setattr(builder, "JP_SEED_PATH", japan)
    monkeypatch.setattr(builder, "MANUAL_PATH", tmp_path / "manual.csv")
    monkeypatch.setattr(artist_registry, "SEED_PATH", korean)
    monkeypatch.setattr(artist_registry, "JP_SEED_PATH", japan)
    monkeypatch.setattr(artist_registry, "MANUAL_PATH", builder.MANUAL_PATH)
    monkeypatch.setattr("sys.argv", ["artist-registry", "--countries", "jp"])
    replies = replies_for([("Q2", "Japanese")], [("Q3", "Japanese group")])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *a, **k: next(replies)
    )
    builder.main()
    assert korean.read_bytes() == original_korean
    assert set(read_rows(japan)) == {"wd:Q2", "wd:Q3"}


def http_response(status=200, body=None, **headers):
    response = requests.Response()
    response.status_code = status
    response._content = body if body is not None else json.dumps(payload()).encode()
    response.raw = BytesIO(response._content)
    response.headers.update(headers)
    return response


@pytest.mark.parametrize("retry_after", ["121", "301", "3600"])
def test_japan_v2_excessive_wait_stops_without_retry(
    cli_paths, monkeypatch, retry_after
):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    calls = []
    waits = []

    def get(*args, **kwargs):
        calls.append(1)
        return http_response(429, **{"Retry-After": retry_after})

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "sleep", waits.append)
    with pytest.raises(RuntimeError, match="wait limit"):
        builder.main()
    assert len(calls) == 1
    assert waits == []
    assert output.read_bytes() == original


def test_japan_v2_budget_is_shared_by_both_queries(cli_paths, monkeypatch):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    monkeypatch.setattr(
        builder,
        "parse_args",
        lambda: argparse.Namespace(
            countries="jp", output=str(output), request_timeout=280
        ),
    )
    now = 0
    timeouts = []
    waits = []

    def get(*args, **kwargs):
        nonlocal now
        timeouts.append(kwargs["timeout"])
        if len(timeouts) == 1:
            now += 250
            return http_response()
        return http_response(429, **{"Retry-After": "60"})

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "monotonic", lambda: now)
    monkeypatch.setattr(builder.time, "sleep", waits.append)
    with pytest.raises(RuntimeError, match="time budget"):
        builder.main()
    assert timeouts == [280, 50]
    assert waits == []
    assert output.read_bytes() == original


def test_japan_v2_rejects_redirect_before_reading_body(cli_paths, monkeypatch):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    redirect = http_response(302, Location="https://example.invalid/query")
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        hook = kwargs.get("hooks", {}).get("response")
        if hook:
            hook(redirect)
        return redirect

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="redirect"):
        builder.main()
    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False
    assert redirect.raw.closed
    assert output.read_bytes() == original


def test_japan_v2_checks_budget_during_stream(cli_paths, monkeypatch):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    now = 0
    answer = http_response()
    calls = []

    class SlowBody(BytesIO):
        def read1(self, size):
            nonlocal now
            now = 301
            return super().read1(size)

    answer.raw = SlowBody(answer._content)

    def get(*args, **kwargs):
        calls.append(1)
        return answer

    monkeypatch.setattr(builder.requests, "get", get)
    monkeypatch.setattr(builder.time, "monotonic", lambda: now)
    with pytest.raises(RuntimeError, match="time budget"):
        builder.main()
    assert calls == [1]
    assert answer.raw.closed
    assert output.read_bytes() == original


@pytest.mark.parametrize("declared_size", [False, True])
def test_japan_v2_stops_at_body_size_limit(cli_paths, monkeypatch, declared_size):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    valid_json = json.dumps(payload()).encode()
    limit = len(valid_json) + 1
    body = valid_json + b" " * 40
    answer = http_response(body=body)
    if declared_size:
        answer.headers["Content-Length"] = str(len(body))
    consumed = []

    class TracedBody(BytesIO):
        def read1(self, size):
            data = super().read1(size)
            consumed.append(len(data))
            return data

    answer.raw = TracedBody(body)
    monkeypatch.setattr(builder, "JP_MAX_RESPONSE_BYTES", limit, raising=False)
    monkeypatch.setattr(builder.requests, "get", lambda *a, **kw: answer)
    with pytest.raises(RuntimeError, match="body size"):
        builder.main()
    assert sum(consumed) == (0 if declared_size else limit + 1)
    assert answer.raw.closed
    assert output.read_bytes() == original


def test_promoting_a_qid_name_does_not_add_it_as_an_alias(cli_paths, monkeypatch):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Q1", "Saved alias")], output)
    replies = replies_for([("Q1", "Proper name", "New alias")], [("Q2", "Group")])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *args, **kwargs: next(replies)
    )
    builder.main()
    promoted = read_rows(output)["wd:Q1"]
    assert promoted["canonical_name"] == "Proper name"
    assert json.loads(promoted["aliases_json"]) == ["Saved alias", "New alias"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head", {"vars": ["item", "aliases"]}),
        ("results", None),
        ("bindings", {}),
        ("row", ["invalid"]),
        ("item", {"type": "literal", "value": "http://www.wikidata.org/entity/Q1"}),
        ("item", {"type": "uri", "value": "http://example.invalid/entity/Q1"}),
        ("item", {"type": "uri", "value": "https://www.wikidata.org/entity/Q01"}),
        ("item", {"type": "uri", "value": "https://www.wikidata.org/entity/Q1٢"}),
        ("item", {"type": "uri", "value": "https://www.wikidata.org/entity/Q1?a=1"}),
        ("item", {"type": "uri", "value": "https://www.wikidata.org/entity/Q1\n"}),
        ("itemLabel", {"type": "literal", "value": 123}),
        ("itemLabel", {"type": "literal", "value": "Name\nNew line"}),
        ("itemLabel", {"type": "literal", "value": " "}),
        ("aliases", {"type": "literal", "value": "Alias\tTab"}),
        ("aliases", {"type": "literal", "value": "Alias\u2028Break"}),
        ("aliases", {"type": "literal", "value": ["Alias"]}),
    ],
)
def test_japan_v2_rejects_invalid_binding_before_writing(
    cli_paths, monkeypatch, field, value
):
    output, _ = cli_paths
    builder.write_seed_csv_noop([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    invalid = payload()
    if field in {"head", "results"}:
        invalid[field] = value
    elif field == "bindings":
        invalid["results"][field] = value
    elif field == "row":
        invalid["results"]["bindings"].append(value)
    else:
        invalid["results"]["bindings"].append(
            dict(invalid["results"]["bindings"][0], **{field: value})
        )
    replies = iter([payload(), invalid])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *args, **kwargs: next(replies)
    )
    with pytest.raises(RuntimeError, match="Invalid Wikidata v2"):
        builder.main()
    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("old_text", "damaged_text"),
    [
        ("canonical_name", "invalid_column"),
        ("wd:Q2", "wd:Q9"),
        ("Group name", "Other name"),
        ("wd:Q2,Group name,[],wikidata,", "wd:Q2,Group name,[],wikidata,EXTRA,"),
    ],
)
def test_candidate_csv_must_round_trip_before_replacing_seed(
    cli_paths, monkeypatch, old_text, damaged_text
):
    output, _ = cli_paths
    writer = builder.write_seed_csv_noop
    writer([seed_row("Q1", "Existing")], output)
    original = output.read_bytes()
    replies = replies_for([("Q1", "Existing")], [("Q2", "Group name")])
    monkeypatch.setattr(
        builder, "fetch_sparql_with_retry", lambda *args, **kwargs: next(replies)
    )

    def damage(rows, path):
        writer(rows, path)
        content = path.read_text(encoding="utf-8")
        assert old_text in content
        path.write_text(content.replace(old_text, damaged_text, 1), encoding="utf-8")
        return True

    monkeypatch.setattr(builder, "write_seed_csv_noop", damage)
    with pytest.raises(RuntimeError, match="candidate CSV"):
        builder.main()
    assert output.read_bytes() == original

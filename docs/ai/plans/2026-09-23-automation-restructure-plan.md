# 収集automation再構成 Implementation Plan

> **For agentic workers:** Opus orchestrates; each task is dispatched to Sol via `codex exec -m gpt-6-sol -s workspace-write -C <repo>`. Opus reviews the diff, runs the verify commands, and commits. Steps use checkbox (`- [ ]`) syntax.

**Goal:** ticketjamを撤去し、LLM automationの出力を判断ファイル1つに縮め、反映・公開・取込をGitHub Actionsへ寄せる。

**Architecture:** MSVはautomationが`data/venue_discovery_inbox.json`をpushし、既存venue discovery workflowがinboxをconfigへ冪等適用してから既存のsignals→LP→manifest→Release連鎖を回す。RTRはautomationが`exports/public_rm_articles.json`をpushし、SideBizのActionsが読み取り専用PATでそれを取り込む。両repoに判断ファイルの鮮度監視workflowを置く。

**Tech Stack:** Python 3.11/3.12、uv（MSV）、venv（RTR）、unittest/pytest、GitHub Actions、SQLite

**Spec:** `docs/ai/plans/2026-09-23-automation-restructure-design.md`

## Global Constraints

- Git: 各repoの`main`でlinear commit。pushはTask 11で利用者確認後にだけ行う。
- 3repoとも、利用者の無関係な未commit変更（SideBiz `01_SNS_X/**`）に触れない。
- 依存の追加・更新をしない。DB schemaを変更しない。
- `data/venue_web_discovery_config.json`の既存`confirmed_events`951行の内容を変えない（Task 5の追記だけ許可）。
- CSVの`ticketjam_watch`、`ticketjam_benchmark_tier`、`ticketjam_watch_reason`列は読み書き互換のため残す。
- ticketjam.jp URLを公開不可とする`validate_external_events`の検査は残す。
- RTR公開exportの記事は7項目だけ: `public_category`, `public_category_label`, `title_ja`, `summary_ja`, `source_name`, `published_date`, `url`。上限: `title_ja` 80字、`summary_ja` 160字。
- inboxの1回あたりcandidates上限: 30件。鮮度上限: MSV inbox 3日、RTR export 7日。
- automation model: MSV `gpt-6-sol`/medium、RTR `gpt-6-luna`/medium。

## Review Focus

1. **ticketjam撤去後にLP掲載集合が変わる** — 撤去前後で`lp_events.json`の`event_key`集合と`event_count`が一致すること（Task 1で基準を保存、Task 2/4で比較）。
2. **inboxの同じ候補が2回pushされる** — 2回目の適用でconfigが変わらないこと（Task 5のidempotent test）。
3. **inboxに公式外sourceや二次流通URLが入る** — `source_class`がaccepted外、`evidence_url`がrejected_domainsやticketjam.jp、httpでないとき、その行が却下されconfigに入らないこと（Task 5のrejection tests）。
4. **inboxファイルが壊れている／存在しない** — schema不正はexit 1でworkflowが失敗し、configを書き換えないこと。鮮度監視はfile不在で失敗すること（Task 5/6 tests）。
5. **RTR export移行でSideBizの公開内容が変わる** — 初期exportから`refresh_overseas_rm_articles.py --input-json`で生成したJSONの`articles`が現行と一致すること（Task 8/10）。

---

## File Structure

MSV:
- Create `scripts/publication_filter.py` — 公開前のrecord選別（baseline source限定、venue discovery根拠必須、都道府県hold）。`ticketjam_discovery.build_discovery_bundle`から非ticketjam部分だけを移す。
- Create `scripts/apply_venue_discovery_inbox.py` — inbox検証とconfigへの冪等追記。
- Create `scripts/check_automation_freshness.py` — JSON内`run_at_utc`の鮮度検査。
- Create `data/venue_discovery_inbox.json` — 初期値（候補0件）。
- Create `.github/workflows/watch_automation_freshness.yml`
- Create tests: `tests/test_publication_filter.py`, `tests/test_apply_venue_discovery_inbox.py`, `tests/test_check_automation_freshness.py`
- Modify `scripts/build_lp_events.py`, `scripts/validate_external_events.py`, `scripts/update_event_signals_data.py`, shared modules, workflows, docs
- Delete ticketjam scripts/tests/data/docs（spec §4.1）

RTR:
- Create `src/rm_trend_radar/public_export_validation.py`, `exports/public_rm_articles.json`, `.github/workflows/validate_public_export.yml`, `.github/workflows/watch_export_freshness.yml`, `tests/test_public_export_validation.py`
- Modify `src/rm_trend_radar/__main__.py`, docs

SideBiz:
- Create `.github/workflows/sync_overseas_rm_articles.yml`
- Modify `02_Service/web_lp/scripts/refresh_market_portal_data.py`, `02_Service/web_lp/tests/test_event_source_policy.py`, docs

---

### Task 1: MSV 撤去前の基準を保存

**Files:** なし（scratchpadに出力）

- [ ] **Step 1: 現行LPをbuildして基準を保存**

```bash
cd /Users/nakamurakeiichi/Developer/market-stats-viewer
BASE=/private/tmp/claude-501/-Users-nakamurakeiichi-Developer-market-stats-viewer/9c4a81c6-1e86-4c5f-b5df-b958a50e391a/scratchpad/baseline
mkdir -p $BASE
cp data/lp_events.json data/event_signals.sqlite data/ticketjam_review_state.json $BASE/
uv run python -m scripts.build_lp_events --output $BASE/lp_events.rebuilt.json
uv run python - <<'EOF'
import json,os
b=os.environ.get('BASE') or '/private/tmp/claude-501/-Users-nakamurakeiichi-Developer-market-stats-viewer/9c4a81c6-1e86-4c5f-b5df-b958a50e391a/scratchpad/baseline'
p=json.load(open(f'{b}/lp_events.rebuilt.json'))
json.dump({'event_count':p['summary']['event_count'],'keys':sorted(e['event_key'] for e in p['events']),
  'held':p.get('ticketjam_promoted_held_records',[]),'location_held':len(p.get('location_held_records',[]))},
  open(f'{b}/baseline.json','w'),ensure_ascii=False)
print(p['summary']['event_count'], len(p.get('ticketjam_promoted_held_records',[])))
EOF
git checkout -- data/ticketjam_review_queue.json 2>/dev/null || true
```

Expected: event_countが表示され、heldが0。LPは当日JST基準の期間で生成されるため、Task 2〜4の比較は基準を作った日と同じJST日付に行う。日付が変わった場合はTask 3完了前のcommitでbaselineを作り直す。heldが0でない場合は停止し、該当`discovery_event_key`のconfig行を`enabled: false`にする追加stepをTask 4に入れる。

---

### Task 2: MSV 公開選別をticketjamから切り離す

**Files:**
- Create: `scripts/publication_filter.py`
- Create: `tests/test_publication_filter.py`
- Modify: `scripts/build_lp_events.py`（SOURCE_PRIORITY/SIGNAL_SOURCE_IDS/source_priority listからticketjam除去、`main()`のticketjam引数と分岐除去）
- Modify: `scripts/validate_external_events.py:25-30`
- Modify: `tests/test_build_lp_events.py`, `tests/test_validate_external_events.py`

**Interfaces:**
- Produces: `select_publishable_records(records: list[dict], *, venue_prefectures: dict[str, str]) -> tuple[list[dict], list[dict]]` — `(trusted, location_held)`を返す。
- Produces: `build_lp_events.main()`は`--ticketjam-policy`/`--review-output`/`--review-state`を持たず、常に`select_publishable_records`を通して`assemble_lp_payload`する。payloadに`location_held_records`と`summary.location_held_record_count`を含める。

- [ ] **Step 1: failing testを書く**

`tests/test_publication_filter.py`:

```python
import unittest

from scripts.publication_filter import select_publishable_records


def rec(source_id, record_id, **kw):
    row = {"source_id": source_id, "record_id": record_id, "venue_name": "東京ドーム",
           "pref_name": "東京都", "source_class": "venue_official",
           "evidence_url": "https://example.jp/e", "evidence_snippet": "2026年11月3日"}
    row.update(kw)
    return row


class PublicationFilterTest(unittest.TestCase):
    def test_drops_non_baseline_sources(self):
        trusted, held = select_publishable_records(
            [rec("official_events", "a"), rec("ticketjam_events", "b")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual([r["record_id"] for r in trusted], ["a"])
        self.assertEqual(held, [])

    def test_unverified_venue_discovery_raises(self):
        with self.assertRaises(ValueError):
            select_publishable_records(
                [rec("venue_web_discovery", "a", evidence_snippet="")],
                venue_prefectures={})

    def test_prefecture_conflict_is_held(self):
        trusted, held = select_publishable_records(
            [rec("official_events", "a", pref_name="大阪府")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual(trusted, [])
        self.assertEqual(held[0]["reason"], "venue_prefecture_conflict")

    def test_missing_prefecture_is_filled_from_registry(self):
        trusted, _ = select_publishable_records(
            [rec("starto_concert", "a", pref_name="")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual(trusted[0]["pref_name"], "東京都")

    def test_unresolved_prefecture_is_held(self):
        trusted, held = select_publishable_records(
            [rec("kstyle_music", "a", pref_name="", venue_name="Unknown Hall")],
            venue_prefectures={})
        self.assertEqual(held[0]["reason"], "unresolved_domestic_location")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 失敗を確認** — `uv run python -m pytest tests/test_publication_filter.py -q` → ModuleNotFoundError

- [ ] **Step 3: 実装**

`scripts/publication_filter.py`:

```python
"""Select records that may enter LP publication grouping."""

from __future__ import annotations

from typing import Any

from .events.types import JAPAN_PREFECTURES
from .signals.sources.venue_web_discovery import ACCEPTED_SOURCE_CLASSES

PUBLISHABLE_SOURCE_IDS = frozenset(
    {"official_events", "venue_web_discovery", "starto_concert", "kstyle_music"}
)


def select_publishable_records(
    records: list[dict[str, Any]], *, venue_prefectures: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trusted: list[dict[str, Any]] = []
    location_held: list[dict[str, Any]] = []
    for row in records:
        if row["source_id"] not in PUBLISHABLE_SOURCE_IDS:
            continue
        if row["source_id"] == "venue_web_discovery" and (
            row.get("source_class") not in ACCEPTED_SOURCE_CLASSES
            or not row.get("evidence_url")
            or not row.get("evidence_snippet")
        ):
            raise ValueError("unverified venue_web_discovery record cannot be published")
        row = dict(row)
        known_pref = venue_prefectures.get(row["venue_name"])
        if known_pref and row.get("pref_name") and row["pref_name"] != known_pref:
            location_held.append({"source_id": row["source_id"], "record_id": row["record_id"],
                                  "reason": "venue_prefecture_conflict"})
            continue
        row["pref_name"] = row.get("pref_name") or known_pref
        if row["pref_name"] not in JAPAN_PREFECTURES:
            location_held.append({"source_id": row["source_id"], "record_id": row["record_id"],
                                  "reason": "unresolved_domestic_location"})
            continue
        trusted.append(row)
    return trusted, location_held
```

`PUBLISHABLE_SOURCE_IDS`は`ticketjam_discovery.BASELINE_SOURCES`と同じ4 source（2026-09-23確認）。

`scripts/build_lp_events.py`:
- `SOURCE_PRIORITY`から`"ticketjam_events": 40`を、`SIGNAL_SOURCE_IDS`から`"ticketjam_events"`を、`assemble_lp_payload`の`source_priority` listから`"ticketjam_events"`を削除する。
- `build_lp_events()`を次に置き換える:

```python
def build_lp_events(
    *, events_db_path: Path = DEFAULT_EVENTS_DB_PATH,
    event_signals_db_path: Path = DEFAULT_EVENT_SIGNALS_DB_PATH,
    include_past: bool = False, past_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    from .publication_filter import select_publishable_records
    from .signals.entity_aliases import load_venue_prefecture_map

    reference_date = as_of_date or today_jst()
    records = load_lp_records(events_db_path=events_db_path,
        event_signals_db_path=event_signals_db_path, include_past=include_past,
        past_days=past_days, as_of_date=reference_date)
    trusted, location_held = select_publishable_records(
        records, venue_prefectures=load_venue_prefecture_map())
    payload = assemble_lp_payload(trusted, as_of_date=reference_date,
        include_past=include_past, past_days=past_days)
    payload["location_held_records"] = location_held
    payload["summary"]["location_held_record_count"] = len(location_held)
    return payload
```

- `main()`から`--ticketjam-policy`、`--review-output`、`--review-state`とその分岐を削除し、`payload = build_lp_events(events_db_path=..., event_signals_db_path=..., include_past=..., past_days=...)`→`write_lp_events(payload, args.output)`だけにする。

`scripts/validate_external_events.py`の冒頭検査を次にする:

```python
    if payload.get("schema_version") != 1:
        raise ValueError("publication must use schema v1")
    if "ticketjam_events" in payload.get("source_priority", []):
        raise ValueError("ticketjam must not be a publication source")
```

`tests/test_build_lp_events.py`と`tests/test_validate_external_events.py`: ticketjam policy/queue/`ticketjam_policy` fieldを前提にしたassertとfixtureを削除し、`ticketjam_events`がsource_priorityにあるpayloadは`validate_payload`が`ValueError`になるtestを1つ追加する。

- [ ] **Step 4: 通過確認**

```bash
uv run python -m pytest tests/test_publication_filter.py tests/test_build_lp_events.py tests/test_validate_external_events.py -q
```

Expected: PASS

- [ ] **Step 5: 掲載集合の比較**

```bash
uv run python -m scripts.build_lp_events --output $BASE/lp_events.after_task2.json
uv run python - <<'EOF'
import json
b='/private/tmp/claude-501/-Users-nakamurakeiichi-Developer-market-stats-viewer/9c4a81c6-1e86-4c5f-b5df-b958a50e391a/scratchpad/baseline'
base=json.load(open(f'{b}/baseline.json')); p=json.load(open(f'{b}/lp_events.after_task2.json'))
keys=sorted(e['event_key'] for e in p['events'])
print(base['event_count'], p['summary']['event_count'], keys==base['keys'], p['summary']['location_held_record_count'], base['location_held'])
assert keys==base['keys'] and p['summary']['location_held_record_count']==base['location_held']
EOF
```

Expected: `True`。`supporting_sources`からticketjam行が消えるのは想定内（表示fieldは不変）。

- [ ] **Step 6: Commit** — `git add scripts/publication_filter.py scripts/build_lp_events.py scripts/validate_external_events.py tests/test_publication_filter.py tests/test_build_lp_events.py tests/test_validate_external_events.py && git commit -m "refactor: decouple LP publication filter from ticketjam"`

---

### Task 3: MSV ticketjam取得・確認コードの撤去

**Files:**
- Delete: `.github/workflows/update_signals_ticketjam.yml`, `scripts/signals/sources/ticketjam.py`, `scripts/ticketjam_discovery.py`, `scripts/ticketjam_official_checks.py`, `scripts/ticketjam_review_state.py`, `scripts/prepare_ticketjam_review.py`, `scripts/build_ticketjam_supplement_report.py`, `tests/test_ticketjam_context_conflict.py`, `tests/test_ticketjam_discovery.py`, `tests/test_ticketjam_official_checks.py`, `tests/test_ticketjam_prefecture_month.py`, `tests/test_ticketjam_publication.py`, `tests/test_ticketjam_review_state.py`, `tests/test_prepare_ticketjam_review.py`, `tests/test_build_ticketjam_supplement_report.py`
- Modify: `scripts/update_event_signals_data.py`（import、source定義`ticketjam_events`、registry map、runtime override/selection/prune関数と呼出、`--ticketjam-*`引数、`domain_intervals`の`ticketjam.jp`、SQLの`IN ('ticketjam_events', 'venue_web_discovery')`は`= 'venue_web_discovery'`へ）
- Modify: `.github/workflows/update_events_official.yml`, `.github/workflows/update_signals.yml`（supplement report step削除）
- Modify: `.github/workflows/update_signals_venue_web_discovery.yml`（pytest対象からticketjam testsを削除、`git add`から`data/ticketjam_review_queue.json`を削除）
- Modify: `.github/workflows/publish_external_events_assets.yml`（workflow_runから`Update event signals data (Ticketjam)`削除）
- Modify: `tests/test_publish_external_events_workflow.py`（上記の期待値）
- Modify: `scripts/signals/artist_registry.py`, `scripts/build_artist_registry_wikidata.py`, `scripts/events/registry.py`, `scripts/events/types.py`, `scripts/audit_event_normalization_candidates.py`, `.agents/skills/dictionary-maintenance/scripts/audit_alias_candidates.py`, `app.py`, `tests/test_event_text_quality.py` — ticketjam専用の分岐・表示を除去。CSV列名の読み書きは残す

- [ ] **Step 1: 削除とimport除去を実施**

- [ ] **Step 2: 残存参照の確認**

```bash
git grep -n -i ticketjam -- scripts tests app.py .github .agents ':!scripts/validate_external_events.py' ':!tests/test_validate_external_events.py' ':!tests/test_publication_filter.py' | grep -viE "ticketjam_watch|ticketjam_benchmark_tier|ticketjam_watch_reason"
```

Expected: 出力なし。除外した3fileは、ticketjamを公開sourceとして拒否する検査（Task 2）とそのtestなので残す。CSV列名も残す

- [ ] **Step 3: 全test**

```bash
uv run python -m pytest tests -q
uv run python -m scripts.update_event_signals_data --help >/dev/null
uv run python -m scripts.build_lp_events --output $BASE/lp_events.after_task3.json
```

Expected: 全PASS、event_key集合がbaselineと一致（Task 2 Step 5の比較scriptを`after_task3`で再実行）

- [ ] **Step 4: Commit** — `git add -A scripts tests app.py .github .agents && git commit -m "refactor: remove ticketjam collection and review pipeline"`

---

### Task 4: MSV ticketjam dataの撤去

**Files:**
- Modify: `data/event_signals.sqlite`
- Delete: `data/ticketjam_review_queue.json`, `data/ticketjam_review_state.json`, `data/ticketjam_supplement_report.json`, `data/ticketjam_supplement_report.md`, `data/ticketjam_venue_pages.csv`
- Regenerate: `data/lp_events.json`, `data/manifest.json`

- [ ] **Step 1: DBから行を削除**

```bash
uv run python - <<'EOF'
import sqlite3
c=sqlite3.connect('data/event_signals.sqlite')
before=dict(c.execute("select source_id,count(*) from signals group by 1").fetchall())
print('before',before)
c.execute("delete from signals where source_id='ticketjam_events'")
c.execute("delete from signal_sources where source_id='ticketjam_events'")
c.commit()
after=dict(c.execute("select source_id,count(*) from signals group by 1").fetchall())
print('after',after)
assert 'ticketjam_events' not in after
assert all(after[k]==v for k,v in before.items() if k!='ticketjam_events')
c.execute("vacuum"); c.close()
EOF
```

Expected: ticketjam以外の件数不変

- [ ] **Step 2: 生成物更新と検証**

```bash
git rm -q data/ticketjam_review_queue.json data/ticketjam_review_state.json data/ticketjam_supplement_report.json data/ticketjam_supplement_report.md data/ticketjam_venue_pages.csv
uv run python -m scripts.build_lp_events
uv run python -m scripts.build_external_events_manifest --release-tag external-events-latest
uv run python -m scripts.validate_external_events --expected-as-of-date "$(TZ=Asia/Tokyo date +%F)"
```

Expected: validate成功。`data/lp_events.json`のevent_key集合がbaselineと一致（比較script再実行）

- [ ] **Step 3: Commit** — `git add data/event_signals.sqlite data/lp_events.json data/manifest.json && git commit -m "data: remove ticketjam signals and review state"`

---

### Task 5: MSV venue discovery inboxの適用

**Files:**
- Create: `scripts/apply_venue_discovery_inbox.py`, `tests/test_apply_venue_discovery_inbox.py`, `data/venue_discovery_inbox.json`
- Modify: `.github/workflows/update_signals_venue_web_discovery.yml`

**Interfaces:**
- Produces: `apply_inbox(inbox: dict, config: dict, *, venue_maps: tuple[dict,dict], artist_maps: tuple[dict,dict]) -> ApplyResult`（`ApplyResult`は`applied: list[dict]`, `duplicates: list[dict]`, `rejected: list[dict]`を持つdataclass）。`config`は変更せず新dictを`ApplyResult.config`に返す。
- Produces: CLI `python -m scripts.apply_venue_discovery_inbox [--inbox PATH] [--config PATH]`。schema不正でexit 1、それ以外exit 0。`GITHUB_STEP_SUMMARY`があれば件数を追記。

- [ ] **Step 1: failing tests**

`tests/test_apply_venue_discovery_inbox.py`:

```python
import copy
import unittest

from scripts.apply_venue_discovery_inbox import InboxSchemaError, apply_inbox

from scripts.signals.entity_aliases import _build_lookup_maps

VENUE_MAPS = _build_lookup_maps([("東京ドーム", ("東京ドーム", "Tokyo Dome"))])
ARTIST_MAPS = ({}, {})
CONFIG = {
    "accepted_source_classes": ["venue_official", "artist_official", "promoter_official", "ticket_official"],
    "rejected_domains": ["ticketjam.jp"],
    "watch_venues": [{"venue_id": "tokyo_dome", "venue_name": "東京ドーム", "aliases": ["東京ドーム", "Tokyo Dome"]}],
    "confirmed_events": [],
}


def cand(**kw):
    row = {"event_start_date": "2026-11-03", "event_end_date": "2026-11-03", "venue_name": "東京ドーム",
           "artist_name": "Example Artist", "title": "Example Artist Dome Tour", "event_category": "concert",
           "source_class": "venue_official", "confidence": "high",
           "evidence_url": "https://www.tokyo-dome.co.jp/event/1", "evidence_snippet": "2026年11月3日 開演18:00",
           "content_extractor": "requests_bs4", "verified_at_utc": "2026-09-24T03:05:00Z"}
    row.update(kw)
    return row


def inbox(*cands):
    return {"schema_version": 1, "run_at_utc": "2026-09-24T03:10:00Z",
            "automation_id": "msv-venue-discovery", "candidates": list(cands), "rejected": []}


def run(ib, config=CONFIG):
    return apply_inbox(ib, config, venue_maps=VENUE_MAPS, artist_maps=ARTIST_MAPS)


class ApplyInboxTest(unittest.TestCase):
    def test_appends_valid_candidate_with_defaults(self):
        result = run(inbox(cand()))
        self.assertEqual(len(result.applied), 1)
        row = result.config["confirmed_events"][0]
        self.assertTrue(row["event_id"].startswith("vwd-"))
        self.assertIs(row["enabled"], True)
        self.assertEqual(row["url"], "https://www.tokyo-dome.co.jp/event/1")

    def test_second_application_is_noop(self):
        first = run(inbox(cand()))
        second = run(inbox(cand()), config=first.config)
        self.assertEqual(second.applied, [])
        self.assertEqual(len(second.duplicates), 1)
        self.assertEqual(second.config, first.config)

    def test_alias_venue_is_duplicate_of_existing(self):
        first = run(inbox(cand()))
        second = run(inbox(cand(venue_name="Tokyo Dome")), config=first.config)
        self.assertEqual(len(second.duplicates), 1)

    def test_rejects_unaccepted_source_class(self):
        result = run(inbox(cand(source_class="secondary_market")))
        self.assertEqual(result.rejected[0]["reason"], "source_class")
        self.assertEqual(result.config["confirmed_events"], [])

    def test_rejects_rejected_domain_and_http(self):
        result = run(inbox(cand(evidence_url="https://ticketjam.jp/e/1"),
                           cand(evidence_url="http://www.tokyo-dome.co.jp/e", title="B")))
        self.assertEqual(sorted(r["reason"] for r in result.rejected), ["evidence_url", "rejected_domain"])

    def test_rejects_unknown_venue_and_bad_date_and_empty_snippet(self):
        result = run(inbox(cand(venue_name="Unknown Hall"),
                           cand(event_start_date="2026/11/03", title="C"),
                           cand(evidence_snippet="", title="D")))
        self.assertEqual(sorted(r["reason"] for r in result.rejected), ["date", "evidence_snippet", "venue"])

    def test_does_not_mutate_input_config(self):
        config = copy.deepcopy(CONFIG)
        run(inbox(cand()), config=config)
        self.assertEqual(config, CONFIG)

    def test_schema_errors(self):
        for bad in ({}, {"schema_version": 2, "run_at_utc": "x", "candidates": []},
                    {"schema_version": 1, "run_at_utc": "2026-09-24T03:10:00Z", "candidates": "x"},
                    inbox(*[cand(title=str(i)) for i in range(31)])):
            with self.assertRaises(InboxSchemaError):
                run(bad)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 失敗を確認** — `uv run python -m pytest tests/test_apply_venue_discovery_inbox.py -q` → ModuleNotFoundError

- [ ] **Step 3: 実装**

`scripts/apply_venue_discovery_inbox.py`:

```python
"""Apply automation-written venue discovery candidates to the config idempotently."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .signals.entity_aliases import (
    load_artist_lookup_maps,
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INBOX = REPO_ROOT / "data" / "venue_discovery_inbox.json"
DEFAULT_CONFIG = REPO_ROOT / "data" / "venue_web_discovery_config.json"
MAX_CANDIDATES = 30
MAX_SNIPPET_CHARS = 400
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED = ("event_start_date", "venue_name", "artist_name", "title", "source_class",
            "evidence_url", "evidence_snippet")


class InboxSchemaError(ValueError):
    pass


@dataclass
class ApplyResult:
    config: dict[str, Any]
    applied: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


def _check_schema(inbox: Any) -> None:
    if not isinstance(inbox, dict) or inbox.get("schema_version") != 1:
        raise InboxSchemaError("schema_version must be 1")
    try:
        datetime.fromisoformat(str(inbox.get("run_at_utc", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise InboxSchemaError("run_at_utc must be ISO 8601") from exc
    cands = inbox.get("candidates")
    if not isinstance(cands, list) or not all(isinstance(c, dict) for c in cands):
        raise InboxSchemaError("candidates must be a list of objects")
    if len(cands) > MAX_CANDIDATES:
        raise InboxSchemaError(f"candidates exceeds {MAX_CANDIDATES}")


def _watch_venue_names(config: dict[str, Any], venue_maps) -> set[str]:
    names: set[str] = set()
    for venue in config.get("watch_venues", []):
        for raw in [venue.get("venue_name"), *venue.get("aliases", [])]:
            canonical, _ = normalize_venue_with_lookup(raw, *venue_maps)
            if canonical:
                names.add(canonical)
    return names


def _dedup_key(row: dict[str, Any], venue_maps, artist_maps) -> tuple[str, str, str]:
    venue, _ = normalize_venue_with_lookup(row.get("venue_name"), *venue_maps)
    artist, _ = normalize_with_lookup(row.get("artist_name") or row.get("title"), *artist_maps)
    return (str(row.get("event_start_date") or ""), venue, artist.casefold())


def _reject_reason(row: dict[str, Any], config: dict[str, Any], watch: set[str], venue_maps) -> str | None:
    if any(not str(row.get(k) or "").strip() for k in REQUIRED if k != "evidence_snippet"):
        return "required"
    for key in ("event_start_date", "event_end_date"):
        if row.get(key) and not DATE_RE.match(str(row[key])):
            return "date"
    if row["source_class"] not in set(config.get("accepted_source_classes", [])):
        return "source_class"
    url = urlparse(str(row["evidence_url"]))
    if url.scheme != "https" or not url.hostname:
        return "evidence_url"
    host = url.hostname.lower()
    if any(host == d or host.endswith("." + d) for d in config.get("rejected_domains", [])):
        return "rejected_domain"
    snippet = str(row.get("evidence_snippet") or "").strip()
    if not snippet or len(snippet) > MAX_SNIPPET_CHARS:
        return "evidence_snippet"
    venue, _ = normalize_venue_with_lookup(row["venue_name"], *venue_maps)
    if venue not in watch:
        return "venue"
    return None


def apply_inbox(inbox: dict[str, Any], config: dict[str, Any], *, venue_maps, artist_maps) -> ApplyResult:
    _check_schema(inbox)
    result = ApplyResult(config=copy.deepcopy(config))
    events = result.config.setdefault("confirmed_events", [])
    watch = _watch_venue_names(config, venue_maps)
    seen = {_dedup_key(e, venue_maps, artist_maps) for e in events}
    for cand in inbox["candidates"]:
        reason = _reject_reason(cand, config, watch, venue_maps)
        if reason:
            result.rejected.append({"title": cand.get("title"), "reason": reason})
            continue
        key = _dedup_key(cand, venue_maps, artist_maps)
        if key in seen:
            result.duplicates.append({"title": cand.get("title"), "key": list(key)})
            continue
        row = dict(cand)
        row.setdefault("event_end_date", row["event_start_date"])
        row.setdefault("url", row["evidence_url"])
        row["enabled"] = True
        row["event_id"] = "vwd-" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:12]
        events.append(row)
        seen.add(key)
        result.applied.append({"title": row["title"], "event_id": row["event_id"]})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if not args.inbox.exists():
        print(f"inbox not found: {args.inbox}")
        return 0
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        result = apply_inbox(json.loads(args.inbox.read_text(encoding="utf-8")), config,
                             venue_maps=load_venue_lookup_maps(), artist_maps=load_artist_lookup_maps())
    except (InboxSchemaError, json.JSONDecodeError) as exc:
        print(f"invalid inbox: {exc}", file=sys.stderr)
        return 1
    if result.applied:
        args.config.write_text(json.dumps(result.config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = (f"venue discovery inbox: applied={len(result.applied)} "
               f"duplicates={len(result.duplicates)} rejected={len(result.rejected)}")
    print(summary)
    for row in result.rejected:
        print(f"  rejected: {row['reason']}: {row['title']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

configの既存書式は`indent=2, sort_keys=True, ensure_ascii=False`＋末尾改行（2026-09-23確認）。既存行が再整形されて差分になることを禁止するため、Step 4で1件適用→`git diff`が追記行だけであることも確認してから`git checkout`で戻す。

`data/venue_discovery_inbox.json`:

```json
{
  "schema_version": 1,
  "run_at_utc": "2026-09-23T00:00:00Z",
  "automation_id": "msv-venue-discovery",
  "candidates": [],
  "rejected": []
}
```

`.github/workflows/update_signals_venue_web_discovery.yml`:
- `on:`に追加:

```yaml
  push:
    branches:
      - main
    paths:
      - data/venue_discovery_inbox.json
```

- `Update venue web discovery signals` stepの直前に追加:

```yaml
      - name: Apply venue discovery inbox
        run: |
          uv run python -m scripts.apply_venue_discovery_inbox
```

- `Validate venue web discovery outputs`のpytest対象に`tests/test_apply_venue_discovery_inbox.py tests/test_publication_filter.py`を追加

- [ ] **Step 4: 通過確認**

```bash
uv run python -m pytest tests/test_apply_venue_discovery_inbox.py -q
uv run python -m scripts.apply_venue_discovery_inbox
git diff --stat data/venue_web_discovery_config.json
```

Expected: PASS、`applied=0 duplicates=0 rejected=0`、configの差分なし

- [ ] **Step 5: Commit** — `git add scripts/apply_venue_discovery_inbox.py tests/test_apply_venue_discovery_inbox.py data/venue_discovery_inbox.json .github/workflows/update_signals_venue_web_discovery.yml && git commit -m "feat: apply automation-written venue discovery inbox in Actions"`

---

### Task 6: MSV 鮮度監視

**Files:**
- Create: `scripts/check_automation_freshness.py`, `tests/test_check_automation_freshness.py`, `.github/workflows/watch_automation_freshness.yml`

**Interfaces:**
- Produces: `check_freshness(path: Path, *, max_age_days: float, now: datetime) -> tuple[bool, str]`
- Produces: CLI `python -m scripts.check_automation_freshness --file PATH --max-age-days N`（stale/不在/壊れはexit 1）

- [ ] **Step 1: failing tests**

```python
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.check_automation_freshness import check_freshness

NOW = datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)


class FreshnessTest(unittest.TestCase):
    def write(self, payload):
        d = tempfile.mkdtemp()
        p = Path(d) / "inbox.json"
        p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        return p

    def test_fresh(self):
        ok, _ = check_freshness(self.write({"run_at_utc": "2026-09-25T00:00:00Z"}), max_age_days=3, now=NOW)
        self.assertTrue(ok)

    def test_stale(self):
        ok, msg = check_freshness(self.write({"run_at_utc": "2026-09-23T23:59:00Z"}), max_age_days=3, now=NOW)
        self.assertFalse(ok)
        self.assertIn("stale", msg)

    def test_missing_file(self):
        ok, msg = check_freshness(Path("/nonexistent/inbox.json"), max_age_days=3, now=NOW)
        self.assertFalse(ok)

    def test_broken_json_or_missing_field(self):
        for payload in ("{", {"schema_version": 1}):
            ok, _ = check_freshness(self.write(payload), max_age_days=3, now=NOW)
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 失敗確認** — `uv run python -m pytest tests/test_check_automation_freshness.py -q`

- [ ] **Step 3: 実装**

```python
"""Fail when an automation-written JSON file has not been refreshed recently."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def check_freshness(path: Path, *, max_age_days: float, now: datetime) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"
    try:
        run_at = datetime.fromisoformat(
            str(json.loads(path.read_text(encoding="utf-8"))["run_at_utc"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError) as exc:
        return False, f"unreadable run_at_utc in {path}: {exc}"
    age = now - run_at
    if age > timedelta(days=max_age_days):
        return False, f"stale: {path} run_at_utc={run_at.isoformat()} age={age}"
    return True, f"fresh: {path} age={age}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--max-age-days", type=float, required=True)
    args = parser.parse_args(argv)
    ok, message = check_freshness(args.file, max_age_days=args.max_age_days, now=datetime.now(timezone.utc))
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`.github/workflows/watch_automation_freshness.yml`:

```yaml
name: Watch automation freshness

on:
  workflow_dispatch:
  schedule:
    - cron: "0 1 * * *" # daily 10:00 JST

permissions:
  contents: read

jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - name: Check venue discovery inbox freshness
        run: |
          python -m scripts.check_automation_freshness --file data/venue_discovery_inbox.json --max-age-days 3
```

（`scripts.check_automation_freshness`は標準libだけで動くためuv不要。`scripts/__init__.py`経由のimportで依存が要る場合は`validate_external_events`と同様にsetup-pythonだけで実行できることを確認する）

- [ ] **Step 4: 通過確認** — `uv run python -m pytest tests/test_check_automation_freshness.py -q && python3 -m scripts.check_automation_freshness --file data/venue_discovery_inbox.json --max-age-days 3`

Expected: PASS、`fresh`

- [ ] **Step 5: Commit** — `git add scripts/check_automation_freshness.py tests/test_check_automation_freshness.py .github/workflows/watch_automation_freshness.yml && git commit -m "feat: alert when venue discovery automation stops"`

---

### Task 7: MSV docs・Skill

**Files:**
- Delete: `docs/ticketjam_official_review_automation.md`
- Modify: `AGENTS.md`（Source Mapに「LLM automationは`data/venue_discovery_inbox.json`だけを書く。反映以降はActions」を1行追加し、ticketjam automation文書への参照があれば除去）
- Modify: `.agents/skills/venue-web-discovery/SKILL.md`（原則のLP優先順位からticketjamを除去。手順5〜9を「候補をinbox schema（spec §4.2）で`data/venue_discovery_inbox.json`へ書き、候補0件でも`run_at_utc`を更新し、inboxだけcommit/push。反映・DB・LP・manifestはActions」に置き換え。「Codexが自動調整できるのはconfigの設定とconfirmed rows」を「inboxだけ」に改める）
- Modify: `docs/spec_update_pipeline.md`（ticketjam節とtickejam review節の削除、venue discovery節にinbox→Actions適用フロー、鮮度監視を追加、workflow一覧更新）
- Modify: `docs/spec_data.md`（ticketjam source、review queue/state、`ticketjam_policy`等payload field削除を反映）
- Modify: `docs/spec_app.md`, `docs/spec_event_status.md`, `docs/event_signal_audit_automation.md`, `README.md`（ticketjam記述の削除・更新）
- Modify: `docs/context/DECISIONS.md`（新decision: ticketjam撤去、判断はinbox、反映はActions、鮮度監視。過去decisionは消さずsupersede注記）
- Modify: `docs/context/STATUS.md`（現在地とre-entry）
- Modify: `docs/context/PROJECT_CONTEXT.md`（ticketjam記述のみ）

- [ ] **Step 1: 編集**
- [ ] **Step 2: 確認**

```bash
git grep -n -i ticketjam -- AGENTS.md README.md docs .agents | grep -v "docs/context/DECISIONS.md" | grep -v "docs/ai/plans/"
git diff --check
```

Expected: 1つ目はCSV列名・撤去の経緯説明以外なし。`git diff --check`出力なし

- [ ] **Step 3: Commit** — `git add -A AGENTS.md README.md docs .agents && git commit -m "docs: route venue discovery through inbox and retire ticketjam"`

---

### Task 8: RTR 公開exportと検証

**Files:**
- Create: `src/rm_trend_radar/public_export_validation.py`, `tests/test_public_export_validation.py`, `exports/public_rm_articles.json`, `.github/workflows/validate_public_export.yml`, `.github/workflows/watch_export_freshness.yml`
- Modify: `src/rm_trend_radar/__main__.py`

**Interfaces:**
- Produces: `validate_public_export(payload: dict, *, now: datetime | None = None, max_age_days: float | None = None) -> list[str]`（違反メッセージのlist。空なら合格）
- Produces: CLI `python -m rm_trend_radar validate-public-export [PATH] [--max-age-days N]`（違反ありでexit 1）

- [ ] **Step 1: failing tests**

```python
import unittest
from datetime import datetime, timezone

from rm_trend_radar.public_export_validation import validate_public_export


def article(**kw):
    row = {"public_category": "pricing_optimization", "public_category_label": "料金設定・価格最適化",
           "title_ja": "直前料金を下げずに競争力を保つ", "summary_ja": "短い紹介文。",
           "source_name": "IDeaS", "published_date": "2026-09-01", "url": "https://ideas.com/a"}
    row.update(kw)
    return row


def payload(*articles, run_at="2026-09-24T06:10:00Z"):
    return {"schema_version": 1, "run_at_utc": run_at, "automation_id": "rm-trend-radar-lp-reflection",
            "source_repo": "rm-trend-radar", "articles": list(articles)}


class PublicExportValidationTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_public_export(payload(article())), [])

    def test_extra_field_rejected(self):
        self.assertTrue(validate_public_export(payload(article(personal_summary="x"))))

    def test_missing_or_empty_field_rejected(self):
        a = article(); del a["source_name"]
        self.assertTrue(validate_public_export(payload(a)))
        self.assertTrue(validate_public_export(payload(article(title_ja=" "))))

    def test_length_limits(self):
        self.assertTrue(validate_public_export(payload(article(title_ja="あ" * 81))))
        self.assertTrue(validate_public_export(payload(article(summary_ja="あ" * 161))))
        self.assertEqual(validate_public_export(payload(article(title_ja="あ" * 80, summary_ja="あ" * 160))), [])

    def test_category_label_date_url(self):
        self.assertTrue(validate_public_export(payload(article(public_category="unknown"))))
        self.assertTrue(validate_public_export(payload(article(public_category_label="別ラベル"))))
        self.assertTrue(validate_public_export(payload(article(published_date="2026/09/01"))))
        self.assertTrue(validate_public_export(payload(article(url="http://ideas.com/a"))))

    def test_duplicate_url(self):
        self.assertTrue(validate_public_export(payload(article(), article(title_ja="別"))))

    def test_freshness(self):
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        self.assertTrue(validate_public_export(payload(article()), now=now, max_age_days=7))
        self.assertEqual(validate_public_export(payload(article()), now=now, max_age_days=8), [])

    def test_header(self):
        self.assertTrue(validate_public_export({"schema_version": 2, "articles": []}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 失敗確認** — `.venv/bin/python -m pytest tests/test_public_export_validation.py -q -p no:cacheprovider --basetemp=.pytest_basetemp_task8`

- [ ] **Step 3: 実装**

`src/rm_trend_radar/public_export_validation.py`:

```python
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from .public_category import PUBLIC_CATEGORY_LABELS

PUBLIC_FIELDS = ("public_category", "public_category_label", "title_ja", "summary_ja",
                 "source_name", "published_date", "url")
TITLE_MAX_CHARS = 80
SUMMARY_MAX_CHARS = 160
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_public_export(payload: dict[str, Any], *, now: datetime | None = None,
                           max_age_days: float | None = None) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    try:
        run_at = datetime.fromisoformat(str(payload.get("run_at_utc", "")).replace("Z", "+00:00"))
    except ValueError:
        errors.append("run_at_utc must be ISO 8601")
        run_at = None
    if run_at and now and max_age_days is not None and now - run_at > timedelta(days=max_age_days):
        errors.append(f"stale export: run_at_utc={payload['run_at_utc']}")
    articles = payload.get("articles")
    if not isinstance(articles, list):
        return errors + ["articles must be a list"]
    seen: set[str] = set()
    for i, a in enumerate(articles):
        where = f"articles[{i}]"
        if not isinstance(a, dict):
            errors.append(f"{where} must be an object"); continue
        keys = set(a)
        if keys != set(PUBLIC_FIELDS):
            errors.append(f"{where} fields must be exactly {PUBLIC_FIELDS}: extra={sorted(keys - set(PUBLIC_FIELDS))} missing={sorted(set(PUBLIC_FIELDS) - keys)}")
            continue
        if any(not isinstance(a[k], str) or not a[k].strip() for k in PUBLIC_FIELDS):
            errors.append(f"{where} has empty field"); continue
        if len(a["title_ja"]) > TITLE_MAX_CHARS:
            errors.append(f"{where} title_ja exceeds {TITLE_MAX_CHARS}")
        if len(a["summary_ja"]) > SUMMARY_MAX_CHARS:
            errors.append(f"{where} summary_ja exceeds {SUMMARY_MAX_CHARS}")
        if PUBLIC_CATEGORY_LABELS.get(a["public_category"]) != a["public_category_label"]:
            errors.append(f"{where} public_category/label mismatch")
        if not DATE_RE.match(a["published_date"]):
            errors.append(f"{where} published_date must be YYYY-MM-DD")
        url = urlparse(a["url"])
        if url.scheme != "https" or not url.hostname:
            errors.append(f"{where} url must be https")
        if a["url"] in seen:
            errors.append(f"{where} duplicate url")
        seen.add(a["url"])
    return errors
```

`__main__.py`: `validate-public-export` subparserを追加（`path` positional default `exports/public_rm_articles.json`、`--max-age-days` float optional）。実行時はJSONを読み、`validate_public_export(payload, now=datetime.now(timezone.utc), max_age_days=args.max_age_days)`の結果を1行ずつstderrへ出し、あればreturn 1、なければ`articles=<n>`をprintしてreturn 0。既存subcommandの分岐様式に合わせる。

`exports/public_rm_articles.json`の初期値: SideBiz現行JSONから生成する。

```bash
cd /Users/nakamurakeiichi/Developer/rm-trend-radar && mkdir -p exports && .venv/bin/python - <<'EOF'
import json
src=json.load(open('../SideBiz_HotelRM/02_Service/web_lp/data/overseas_rm_articles.json',encoding='utf-8'))
F=("public_category","public_category_label","title_ja","summary_ja","source_name","published_date","url")
out={"schema_version":1,"run_at_utc":"2026-09-23T00:00:00Z","automation_id":"rm-trend-radar-lp-reflection",
     "source_repo":"rm-trend-radar","articles":[{k:a[k] for k in F} for a in src["articles"]]}
open('exports/public_rm_articles.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(len(out["articles"]))
EOF
```

`.gitignore`に`exports/`が含まれないことを確認する。

`.github/workflows/validate_public_export.yml`:

```yaml
name: Validate public export

on:
  push:
    branches: [main]
    paths:
      - exports/public_rm_articles.json
      - src/rm_trend_radar/public_export_validation.py
  pull_request:
    paths:
      - exports/public_rm_articles.json

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Validate
        env:
          PYTHONPATH: src
        run: python -m rm_trend_radar validate-public-export exports/public_rm_articles.json
```

`.github/workflows/watch_export_freshness.yml`: 同構成で`on: schedule: - cron: "0 1 * * *"`と`workflow_dispatch`、runは`python -m rm_trend_radar validate-public-export exports/public_rm_articles.json --max-age-days 7`。

- [ ] **Step 4: 通過確認**

```bash
.venv/bin/python -m compileall -q src app.py
.venv/bin/python -m pytest tests -q -p no:cacheprovider --basetemp=.pytest_basetemp_task8
PYTHONPATH=src .venv/bin/python -m rm_trend_radar validate-public-export exports/public_rm_articles.json
```

Expected: 全PASS、`articles=143`

- [ ] **Step 5: Commit** — `git add src/rm_trend_radar/public_export_validation.py src/rm_trend_radar/__main__.py tests/test_public_export_validation.py exports/public_rm_articles.json .github/workflows/validate_public_export.yml .github/workflows/watch_export_freshness.yml && git commit -m "feat: add validated public article export for SideBiz"`

---

### Task 9: RTR docs

**Files:**
- Modify: `AGENTS.md`（Product And Publication Boundariesに「automationは`exports/public_rm_articles.json`だけを書き、SideBiz反映はSideBiz Actionsが行う」を1行）
- Modify: `docs/spec_002_review_workflow.md`（自動化節: automationの責務をexport更新までに、export schemaと検証上限、SideBiz取込、鮮度監視7日）
- Modify: `docs/context/DECISIONS.md`（D-20260923-020: exportを公開正本、SideBiz pull、automationはRTRのみ、model `gpt-6-luna`。D-20260902-019をsupersede）
- Modify: `docs/context/STATUS.md`
- Modify: `README.md`（`validate-public-export` command）

- [ ] **Step 1: 編集**
- [ ] **Step 2: `git diff --check`**
- [ ] **Step 3: Commit** — `git commit -am "docs: make public export the SideBiz handoff"`

---

### Task 10: SideBiz 取込workflowとticketjam後始末

**Files:**
- Create: `.github/workflows/sync_overseas_rm_articles.yml`
- Modify: `02_Service/web_lp/scripts/refresh_market_portal_data.py:368-371,434-438`
- Modify: `02_Service/web_lp/tests/test_event_source_policy.py`（ticketjamを前提にしたcaseを「未知sourceはnews扱い」または削除）
- Modify: `docs/operations/public-lp-publication-pipeline.md`、`docs/context/DECISIONS.md`、`docs/context/STATUS.md`

- [ ] **Step 1: ticketjam分岐削除**

```python
def signal_kind(source_id: str) -> tuple[str, str]:
    return "news", "ニュース速報"
```

```python
def lp_event_kind(source_id: str) -> tuple[str, str]:
    if source_id in {"official_events", "venue_web_discovery"}:
        return "official", "会場公式日程"
    return "news", "ニュース速報"
```

`docs/operations/public-event-source-policy.json`にticketjam.jpの許可が含まれていれば削除する。

- [ ] **Step 2: 移行等価性の確認**

```bash
cd /Users/nakamurakeiichi/Developer/SideBiz_HotelRM
cp 02_Service/web_lp/data/overseas_rm_articles.json /private/tmp/claude-501/-Users-nakamurakeiichi-Developer-market-stats-viewer/9c4a81c6-1e86-4c5f-b5df-b958a50e391a/scratchpad/rm_before.json
UPDATED=$(python3 -c "import json;print(json.load(open('02_Service/web_lp/data/overseas_rm_articles.json'))['updated_on'])")
python3 02_Service/web_lp/scripts/refresh_overseas_rm_articles.py --input-json ../rm-trend-radar/exports/public_rm_articles.json --updated-on "$UPDATED"
git diff --stat -- 02_Service/web_lp
```

Expected: `overseas_rm_articles.json`の`articles`が一致し、差分が`source_repo`値（`rm-trend-radar`で同じなら0）以外に無い。差分があれば原因を特定してから進める。確認後`git checkout -- 02_Service/web_lp`で戻す。

- [ ] **Step 3: workflow作成**

`.github/workflows/sync_overseas_rm_articles.yml`:

```yaml
name: Sync overseas RM articles

on:
  workflow_dispatch:
  schedule:
    - cron: "30 10 * * *" # daily 19:30 JST, after publish_market_portal

permissions:
  contents: write

concurrency:
  group: publish-market-portal
  cancel-in-progress: false

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout SideBiz
        uses: actions/checkout@v4
        with:
          path: sidebiz
          persist-credentials: true

      - name: Checkout rm-trend-radar export
        uses: actions/checkout@v4
        with:
          repository: NemuKei/rm-trend-radar
          token: ${{ secrets.RTR_READ_TOKEN }}
          path: rtr
          sparse-checkout: |
            exports

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Refresh overseas RM articles when export changed
        shell: bash
        run: |
          set -euo pipefail
          current=$(python - <<'PY'
          import json
          print(json.dumps(json.load(open("sidebiz/02_Service/web_lp/data/overseas_rm_articles.json", encoding="utf-8"))["articles"], sort_keys=True))
          PY
          )
          incoming=$(python - <<'PY'
          import json
          F=("public_category","public_category_label","title_ja","summary_ja","source_name","published_date","url")
          print(json.dumps([{k:a[k] for k in F} for a in json.load(open("rtr/exports/public_rm_articles.json", encoding="utf-8"))["articles"]], sort_keys=True))
          PY
          )
          if [ "$current" = "$incoming" ]; then
            echo "No article changes."
            exit 0
          fi
          python sidebiz/02_Service/web_lp/scripts/refresh_overseas_rm_articles.py \
            --input-json rtr/exports/public_rm_articles.json \
            --updated-on "$(TZ=Asia/Tokyo date +%F)"

      - name: Test
        run: |
          python -m unittest discover -s sidebiz/02_Service/web_lp/tests -p "test_refresh_overseas_rm_articles.py"

      - name: Commit and push
        shell: bash
        run: |
          set -euo pipefail
          git -C sidebiz config user.name "github-actions[bot]"
          git -C sidebiz config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git -C sidebiz add -- \
            02_Service/web_lp/data/overseas_rm_articles.json \
            02_Service/web_lp/overseas_rm_articles.html \
            02_Service/web_lp/data/content_freshness.json
          if git -C sidebiz diff --cached --quiet; then
            echo "No changes to commit."
            exit 0
          fi
          git -C sidebiz commit -m "chore: sync overseas RM articles"
          git -C sidebiz push origin HEAD:main
```

`refresh_overseas_rm_articles.py`が`normalize_articles`で順序や項目を変える場合、比較の`current`/`incoming`が同じ正規化を通るように、比較をscriptの`normalize_articles`呼出しに置き換える（`sys.path`に`sidebiz/02_Service/web_lp/scripts`を追加してimport）。

- [ ] **Step 4: 検証**

```bash
python3 -m unittest discover -s 02_Service/web_lp/tests -p "test_*.py"
python3 -c "import yaml,sys;yaml.safe_load(open('.github/workflows/sync_overseas_rm_articles.yml'))" 2>/dev/null || ruby -ryaml -e 'YAML.load_file(".github/workflows/sync_overseas_rm_articles.yml")'
git status --short
```

Expected: PASS。`git status`に`01_SNS_X/**`の既存変更以外はこのtaskの対象fileだけ

- [ ] **Step 5: docs更新（運用docにautomationはSideBizへ書き込まない、RM取込はsync workflow、PAT `RTR_READ_TOKEN`要件）**

- [ ] **Step 6: Commit** — 対象fileだけを明示して`git add`し、`git commit -m "feat: pull overseas RM articles from rm-trend-radar export"`

---

### Task 11: 全体検証、automation prompt、push

- [ ] **Step 1: 3repoの全test**

```bash
cd /Users/nakamurakeiichi/Developer/market-stats-viewer && uv run python -m pytest tests -q && uv run python -m scripts.validate_external_events --expected-as-of-date "$(TZ=Asia/Tokyo date +%F)"
cd /Users/nakamurakeiichi/Developer/rm-trend-radar && .venv/bin/python -m pytest tests -q -p no:cacheprovider --basetemp=.pytest_basetemp_final
cd /Users/nakamurakeiichi/Developer/SideBiz_HotelRM && python3 -m unittest discover -s 02_Service/web_lp/tests -p "test_*.py"
```

- [ ] **Step 2: automation promptを`docs/ai/plans/2026-09-23-automation-prompts.md`（MSV）に書く** — `msv-venue-discovery`（spec §4.5）と`rm-trend-radar-lp-reflection`新prompt（spec §5.3）。各promptに: 読む文書、書いてよいfileは1つだけ、候補0件でも`run_at_utc`更新、commit/push手順、禁止事項（build、DB、他repo、force push、stash）

- [ ] **Step 3: 利用者確認を得てpush** — push順: RTR → MSV → SideBiz。利用者の作業（PAT発行と`RTR_READ_TOKEN`登録、Codex appで`lp`停止・新automation作成）を依頼

- [ ] **Step 4: push後確認** — MSV: `Publish external events assets`成功とRelease asset更新、`Watch automation freshness`手動実行成功。RTR: `Validate public export`成功。SideBiz: secret登録後に`Sync overseas RM articles`手動実行でno-op成功

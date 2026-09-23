# 収集automation再構成 設計

- 日付: 2026-09-23
- 対象repo: `market-stats-viewer`（MSV）、`rm-trend-radar`（RTR）、`SideBiz_HotelRM`（SideBiz）
- 状態: 設計承認済み、spec review待ち

## 1. 目的と成功状態

### 目的

イベント・市場統計・海外RM記事の収集から公開までを、壊れにくく、止まったら気付ける構造にする。LLMの担当を「判断して1ファイルを書く」だけに縮め、反映・build・検証・公開・取込は決定論的なGitHub Actionsへ寄せる。

### 成功状態

1. ticketjamの取得・確認・レビュー運用が3repoから撤去され、LP掲載内容が撤去前と同等（ticketjam起点の確認済み公式行は維持）である。
2. MSVのLLM automationは`data/venue_discovery_inbox.json`だけを書き換えてpushし、以降の反映〜Release公開はActionsで完結する。
3. RTRのLLM automationは`exports/public_rm_articles.json`だけを書き換えてpushし、SideBizへ直接書き込まない。SideBizはActionsでRTRのexportを取り込む。
4. automationが止まった場合、GitHub Actionsの失敗通知で気付ける。
5. 将来Codex Cloudの定期実行が使えるようになった時、判断stepの実行場所だけ差し替えれば移行できる。

### 非目的

- クラウドでのLLM実行（Codex Cloud定期実行が提供されるまで保留）
- SQLiteのgit管理廃止、DB schema変更
- evidence再取得による機械検証（後続候補。inbox検証は構造・policy検査までとする）
- `ticketjam_watch`等CSV列の削除（互換のため列は残し、未使用にする）
- AGENTS.mdの全面改訂（責務が変わった行だけ更新する）

## 2. 決定事項

| 論点 | 決定 | 理由 |
|---|---|---|
| LLM実行基盤 | このMacBook Pro 1台のCodex app automation（ChatGPTサブスク内） | Codex Cloudに定期実行がなく、Codex app automationはlocal project専用。API従量課金は当面避ける |
| ticketjam | 全面撤去 | 公開には既に使っていない（`--ticketjam-policy discovery`で除外済み）。最重量のautomationとdataを削れる |
| 発見入口の代替 | 既存`venue-web-discovery` Skillを使うautomation | 会場起点の公式確認で、二次流通由来のノイズを持ち込まない |
| RM記事の受け渡し | SideBizがRTRを読み取り専用PATでpullする | automationが他repoへ書き込まない。漏洩時の影響が読み取りに限られる |
| 停止検知 | 毎日cronで判断ファイルの鮮度を検査し、超過で失敗させる | Mac停止をGitHub通知で可視化する |
| モデル | MSV発見: `gpt-6-sol`/medium、RTR紹介文: `gpt-6-luna`/medium | 判断難度に合わせる。構造検査で誤りを止める |

## 3. 目標構成

```
┌ MacBook Pro: Codex app automation ─────────────────────────────────────┐
│ msv-venue-discovery (gpt-6-sol)          rm-trend-radar-lp-reflection (gpt-6-luna) │
│  → MSV data/venue_discovery_inbox.json    → RTR exports/public_rm_articles.json     │
└───────────────┬────────────────────────────────────────┬────────────────┘
                │ push                                   │ push
┌ MSV Actions ──▼───────────────────────────┐ ┌ RTR Actions ▼──────────────────┐
│ update_signals_venue_web_discovery.yml    │ │ validate_public_export.yml (新) │
│  (+push trigger, +inbox apply step)       │ └───────────────┬────────────────┘
│  → publish_external_events_assets.yml     │                 │ read-only PAT
│ watch_automation_freshness.yml (新)       │                 │
└───────────────┬───────────────────────────┘                 │
                │ Release external-events-latest (public)     │
┌ SideBiz Actions ▼───────────────────────────────────────────▼──────────┐
│ publish_market_portal.yml (既存)   sync_overseas_rm_articles.yml (新)   │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. MSV

### 4.1 ticketjam撤去

削除する:

- `.github/workflows/update_signals_ticketjam.yml`
- `scripts/signals/sources/ticketjam.py`、`scripts/ticketjam_discovery.py`、`scripts/ticketjam_official_checks.py`、`scripts/ticketjam_review_state.py`、`scripts/prepare_ticketjam_review.py`、`scripts/build_ticketjam_supplement_report.py`
- ticketjam専用tests（`tests/test_ticketjam_*.py`、`tests/test_prepare_ticketjam_review.py`、`tests/test_build_ticketjam_supplement_report.py`）
- `data/ticketjam_review_queue.json`、`data/ticketjam_review_state.json`、`data/ticketjam_supplement_report.{json,md}`、`data/ticketjam_venue_pages.csv`
- `docs/ticketjam_official_review_automation.md`

変更する:

- `scripts/update_event_signals_data.py`: ticketjam sourceの登録と処理を除去
- `scripts/build_lp_events.py`: `--ticketjam-policy`とreview queue生成を除去。公開結果は現行`discovery`と同値にする
- `scripts/validate_external_events.py`: `ticketjam_policy`必須検査を除去。ticketjam.jp URLを公開不可とする検査は残す
- `update_events_official.yml`、`update_signals.yml`: supplement report stepを除去
- `update_signals_venue_web_discovery.yml`: ticketjam testsとqueueの`git add`を除去
- `publish_external_events_assets.yml`: `workflow_run`から`Update event signals data (Ticketjam)`を除去
- 共有モジュール（`artist_registry.py`、`build_artist_registry_wikidata.py`、`events/registry.py`、`events/types.py`、`audit_*`、`app.py`、dictionary-maintenance skill script）: ticketjam専用分岐を除去。CSV列の読み書き互換は維持する
- 上記に対応する共有tests（`test_build_lp_events.py`、`test_validate_external_events.py`、`test_publish_external_events_workflow.py`、`test_event_text_quality.py`）

data:

- `data/event_signals.sqlite`から`source_id='ticketjam_events'`の`signals`行（1,175行）と`signal_sources`行を削除する。事前に行数を記録し、削除後に他sourceの行数不変を確認する
- `data/venue_web_discovery_config.json`の`confirmed_events`（951行、全て公式source class）は変更しない

契約:

- `lp_events.json`の`ticketjam_policy`等のticketjam由来fieldは削除する（2026-09-23時点でSideBizは`ticketjam_policy`を参照していないことを確認済み）
- `lp_impact`: 掲載件数は撤去前後で一致することを期待値とし、`build_lp_events`の出力件数・event_key集合を撤去前と比較する

### 4.2 venue discovery inbox

`data/venue_discovery_inbox.json`（automationだけが書く）:

```json
{
  "schema_version": 1,
  "run_at_utc": "2026-09-24T03:10:00Z",
  "automation_id": "msv-venue-discovery",
  "candidates": [
    {
      "event_start_date": "2026-11-03",
      "event_end_date": "2026-11-03",
      "event_start_time": "18:00",
      "venue_name": "東京ドーム",
      "raw_venue_name": "東京ドーム",
      "artist_name": "Example Artist",
      "raw_artist_name": "Example Artist",
      "title": "Example Artist Dome Tour 2026",
      "event_category": "concert",
      "source_class": "venue_official",
      "confidence": "high",
      "evidence_url": "https://www.tokyo-dome.co.jp/...",
      "evidence_snippet": "2026年11月3日(火・祝) 開演18:00 ...",
      "content_extractor": "requests_bs4",
      "discovery_query": "東京ドーム 2026年11月 公演",
      "verified_at_utc": "2026-09-24T03:05:00Z"
    }
  ],
  "rejected": [
    {"query": "...", "url": "...", "reason": "secondary_market"}
  ]
}
```

- candidate行は既存`confirmed_events`行と同じfield名を使う（`event_id`、`enabled`、`score`、`url`、`announced_at_utc`は適用時に既存規則で補う）
- 候補0件の回も`run_at_utc`を更新してpushする（生存信号）
- 1回のcandidates上限は30件

### 4.3 inbox適用

新規`scripts/apply_venue_discovery_inbox.py`:

- 入力: inbox、`data/venue_web_discovery_config.json`
- 検証: schema_version、必須field、日付形式、`source_class`が`accepted_source_classes`内、`evidence_url`がhttpsかつ`rejected_domains`外、`evidence_snippet`非空かつ上限長以内、`venue_name`が`watch_venues`またはvenue alias辞書で解決可能
- 重複: `event_start_date + canonical venue_name + canonical artist_name/title`で既存`confirmed_events`と照合し、既存行は上書きしない（冪等）
- 出力: configへappend、適用/却下/重複の件数と理由をstdoutとGitHub step summaryへ出す
- 却下があってもexit 0、schema不正はexit 1

`update_signals_venue_web_discovery.yml`:

- triggerに`push`（`branches: [main]`、`paths: [data/venue_discovery_inbox.json]`）を追加
- `update_event_signals_data --only venue_web_discovery`の前に`apply_venue_discovery_inbox`を実行
- `git add`対象に`data/venue_web_discovery_config.json`（既存）を維持し、inboxはActionsから変更しない
- 既存の`workflow_run`連鎖でReleaseが公開される

### 4.4 停止検知

新規`.github/workflows/watch_automation_freshness.yml`:

- 毎日cron + `workflow_dispatch`
- `data/venue_discovery_inbox.json`の`run_at_utc`が3日より古い、またはfileが無ければ失敗
- RTRの停止検知はRTR側に置く（5.2）。privateのRTRをMSVから読むためのtokenを増やさない
- 失敗時はGitHub標準の失敗通知に任せる（追加の通知経路は作らない）

### 4.5 automation

- 既存`lp`（ticketjam公式確認・LP同期）を停止する
- 新規`msv-venue-discovery`: 毎日1回、`execution_environment=local`、model `gpt-6-sol`、reasoning `medium`、cwd MSV
- prompt要旨: root AGENTS.mdと`venue-web-discovery` Skillに従い、`watch_venues`を会場起点で検索し、公式/準公式本文で確認できた候補だけをinboxへ書く。inbox以外のfileを変更しない。git同期→inbox更新→inboxだけcommit/push。build・DB・Release・SideBizに触れない
- `venue-web-discovery` Skill: 手順5〜8を「inboxへ書いてpushする。反映はActions」に改める

## 5. RTR

### 5.1 public export

新規`exports/public_rm_articles.json`（automationだけが書く）:

```json
{
  "schema_version": 1,
  "run_at_utc": "2026-09-24T06:10:00Z",
  "automation_id": "rm-trend-radar-lp-reflection",
  "source_repo": "rm-trend-radar",
  "articles": [
    {
      "public_category": "...",
      "public_category_label": "...",
      "title_ja": "...",
      "summary_ja": "...",
      "source_name": "IDeaS",
      "published_date": "2026-09-01",
      "url": "https://..."
    }
  ]
}
```

- `articles`は公開7項目だけ。初期値はSideBiz現行`02_Service/web_lp/data/overseas_rm_articles.json`の`articles`から移す
- SideBizの`load_articles_from_json`は`articles`配列を持つobjectを受け付けるため、SideBiz側のloader変更は不要

### 5.2 検証

- 新規`src/rm_trend_radar/public_export_validation.py`と`python -m rm_trend_radar validate-public-export <path>`: 7項目限定、全項目非空、URL https・重複なし、`title_ja`80字以内、`summary_ja`160字以内（2026-09-23時点の公開143件は最大58字/120字）、`public_category`は現行6種（`ai_search_booking_behavior`、`distribution_ota_direct`、`forecast_occupancy_controls`、`organization_process`、`pricing_optimization`、`revenue_metrics_owner_view`）のいずれか、`published_date`はYYYY-MM-DD
- 新規`.github/workflows/validate_public_export.yml`: exportのpush時とPRで実行
- 新規`.github/workflows/watch_export_freshness.yml`: 毎日cron、`run_at_utc`が7日超で失敗

### 5.3 automation

- `rm-trend-radar-lp-reflection`を改める: model `gpt-6-luna`、cwdはRTRのみ
- prompt要旨: 最新RSS snapshot artifactを取得し、exportのURL集合と比較し、有用な新着を最大5件、7項目だけでexportへ追加する。候補0件でも`run_at_utc`を更新する。validate後、exportだけcommit/push。SideBizとローカルSQLiteに触れない

## 6. SideBiz

- 新規`.github/workflows/sync_overseas_rm_articles.yml`: 毎日cron + `workflow_dispatch`。`actions/checkout`で`NemuKei/rm-trend-radar`を`secrets.RTR_READ_TOKEN`で取得し、`refresh_overseas_rm_articles.py --input-json <rtr>/exports/public_rm_articles.json --updated-on <JST today>`を実行、既存testsを通し、差分があればcommit/push
- `updated_on`はexportの内容が変わった時だけ進める（差分なしなら何もcommitしない）
- `refresh_market_portal_data.py`のticketjam分岐と関連testsを除去する（MSV撤去後の後始末）
- 利用者の未commit変更（`01_SNS_X/**`）には触れない
- `docs/operations/public-lp-publication-pipeline.md`のautomation役割を更新

## 7. docs

- MSV: `AGENTS.md`（Source Mapからticketjam automation文書を除去、automation責務を1行で記載）、`docs/spec_update_pipeline.md`、`docs/spec_data.md`、`docs/context/DECISIONS.md`（新decision）、`docs/context/STATUS.md`、README
- RTR: `AGENTS.md`（automationはexportだけを書く旨）、`docs/spec_002_review_workflow.md`、`docs/context/DECISIONS.md`（D-20260902-019をsupersede）、`docs/context/STATUS.md`
- SideBiz: 運用docとDECISIONS

## 8. 実行方法

- Opusが実装計画を書き、taskごとに`codex exec -m gpt-6-sol -s workspace-write -C <repo>`でSolへ指示する
- task完了ごとにOpusがdiff review、focused tests、生成物検証を行い、repoごとにlocal commitする
- 全task完了後、利用者の確認を得てからpushする（MSV mainへのpushはRelease公開を連鎖させるため）
- 利用者の作業: RTR read-only fine-grained PAT発行とSideBiz secret `RTR_READ_TOKEN`登録、Codex appで`lp`停止と新automation作成（promptはOpusが用意）

## 9. 検証

- MSV: 全tests、`build_lp_events`の撤去前後比較（件数、event_key集合）、`build_external_events_manifest`、`validate_external_events`、inbox適用の正常系・却下系・冪等性tests、workflow YAML構文
- RTR: compileall、全tests、`validate-public-export`で初期exportが通ること
- SideBiz: `refresh_overseas_rm_articles.py --input-json`で初期exportから現行と同じJSON/HTMLが生成されること（`updated_on`以外差分なし）、policy tests
- push後: 各workflowの初回run成功、Release asset更新、SideBiz公開JSONの件数

## 10. リスクと戻し方

- ticketjam撤去で掲載件数が変わる: 撤去前後比較で差分が出たら撤去を止めて原因を特定する
- inbox適用の不具合: inboxはActionsから変更しないため、scriptを直してworkflowを再実行すれば再適用できる（冪等）
- automationがMac停止で止まる: 停止検知workflowが失敗する。手動で`codex exec`を1回実行して回復
- PAT期限切れ: SideBiz syncが失敗し通知される。PATを再発行して登録
- 戻し方: repoごとのcommitをrevertし、Codex appで`lp`を再開する

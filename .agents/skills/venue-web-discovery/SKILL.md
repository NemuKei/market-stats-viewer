---
name: venue-web-discovery
description: 会場起点のWeb検索・公式/準公式ページ確認で大型イベント発表を検知し、候補を data/venue_discovery_inbox.json に書くときに使う。Bruno Mars / Stray Kids のような大型会場公演の検知、Codex Automation による公式根拠確認、venue discovery inbox の作成、設定改善の検討に使用する。config・DB・LP への反映は GitHub Actions が行う。
---

# Venue Web Discovery

このSkillは、LP掲載をゴールにした大型会場イベント検知の手順を固定する。

## 原則

- LP掲載の表示優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music` とする。
- Google検索結果、AI概要、一般ニュース、SNS単体、二次流通単体はDB更新根拠にしない。
- DB更新根拠にできるのは `venue_official`、`artist_official`、`promoter_official`、`ticket_official` の公式/準公式ページ本文だけ。
- Skill本文は自動編集しない。Codex Automationが書き込めるのは `data/venue_discovery_inbox.json` だけ。`data/venue_web_discovery_config.json` への追記、DB、LP、manifest、Releaseは GitHub Actions（`update_signals_venue_web_discovery.yml` と後続の公開workflow）が行う。
- 別端末の Codex Automation でも動くよう、ローカル絶対パス、ブラウザ履歴、個人ログイン状態に依存しない。
- 本文抽出は `requests_bs4` を default extractor とし、`crawl4ai` は optional fallback extractor として使う。
- `crawl4ai` を使ってよいのは、JS生成ページ、`requests_bs4` で本文抽出に失敗したページ、公式サイト内crawlやリンク探索が必要なページ、アーティスト公式サイトに限る。
- Firecrawl は将来の paid optional provider として保留し、browser-use は調査・Skill改善・例外調査用として保留する。

## 手順

1. `docs/context/PROJECT_CONTEXT.md` の `Always Read Block` と、`docs/spec_data.md` / `docs/spec_update_pipeline.md` のイベント配布契約を確認する。
2. `data/venue_web_discovery_config.json` の `provider_policy`、`watch_venues`、`query_templates`、`accepted_source_classes`、`preferred_domains`、`preferred_domain_extractors`、`rejected_domains` を読む。
3. 会場別名を使って検索し、`content_extractor=requests_bs4|crawl4ai` で公式/準公式ページ本文を確認する。
   - 既定は `python -m scripts.venue_web_discovery_extract <url> --content-extractor requests_bs4`
   - JS生成や複雑HTMLで失敗する場合だけ `--content-extractor crawl4ai` を使う
   - `crawl4ai` 未導入または失敗時は `requests_bs4` へfallbackし、本文根拠が取れなければDB更新しない
4. 公式/準公式ページ本文に次の要素が揃う候補だけを confirmed event として扱う。
   - 公演日
   - 会場名
   - アーティスト名またはイベント名
   - 公式/準公式 source class
   - evidence URL と短い evidence snippet
5. 既に `confirmed_events` または `data/lp_events.json` にある公演は候補から除く。候補は1回30件まで。
6. `data/venue_discovery_inbox.json` を schema_version=1 で丸ごと書き直す。`run_at_utc` は実行時刻（UTC、末尾Z）。`candidates` の各行は `confirmed_events` と同じfield名（`event_start_date`、`event_end_date`、`event_start_time`、`venue_name`、`raw_venue_name`、`artist_name`、`raw_artist_name`、`title`、`event_category`、`source_class`、`confidence`、`evidence_url`、`evidence_snippet`、`content_extractor`、`discovery_query`、`verified_at_utc`）を使う。採用しなかった有力候補は `rejected` に `query`、`url`、`reason` を残す。候補0件でも `run_at_utc` を更新する（停止検知の生存信号）。
7. `data/venue_web_discovery_config.json` の一時コピーに対して `python -m scripts.apply_venue_discovery_inbox --config <一時コピー>` を実行し、rejected が出たら理由を見て inbox を直す。repo の config は変更しない。
8. `data/venue_discovery_inbox.json` だけを commit / push する。push を合図に Actions が検証・config追記・signals・LP・Release まで反映する。

## Crawl4AI optional setup

- `crawl4ai` は必須依存ではない。通常運用は `requests_bs4` だけで動く。
- 別端末や GitHub Actions で使う場合は、必要な環境だけで `uv sync --extra crawl4ai` を実行する。
- 初回は `uv run crawl4ai-setup` を実行し、`uv run crawl4ai-doctor` で Playwright/browser を確認する。
- browser 関連で失敗する場合は、公式手順に従って `uv run python -m playwright install chromium` を試す。
- optional provider の疎通確認は、`uv run python -m scripts.venue_web_discovery_extract https://www.straykidsjapan.com/runitjapan/ --content-extractor crawl4ai --min-text-chars 200` を使う。
- `crawl4ai` が使えない場合でも、confirmed event へ進めてよいのは `requests_bs4` または手動確認で公式/準公式URL本文の根拠が取れた場合だけ。

## 設定改善

- 検知漏れがある場合は、まず `query_templates`、`preferred_domains`、`watch_venues`、`known_examples` を改善する。
- 誤検知がある場合は、`rejected_domains`、`rejected_source_classes`、必須labelsを改善する。
- Skill本文、DB schema、source priority、Release asset契約を変える必要がある場合は、別タスクとして正本docsから更新する。

## 出力確認

- `venue_web_discovery` の signals は `labels_json` に `event_start_date`、`event_end_date`、`venue_name`、`raw_venue_name`、`artist_name`、`raw_artist_name`、`event_category`、`source_class`、`confidence`、`evidence_url`、`evidence_snippet` を持つ。
- `content_extractor` は確認に使った本文抽出providerを示す監査用ラベルであり、DB採用根拠そのものではない。
- `lp_events.json` は同一キー `event_date + canonical venue_name + canonical artist_name` で統合し、`display_source_id` と `supporting_sources` を持つ。
- `lp_impact` は通常 `display_count_change`、`source_priority_change`、`manifest_asset_change` のいずれかまたは複数になる。
- inbox が3日更新されないと `watch_automation_freshness.yml` が失敗する。

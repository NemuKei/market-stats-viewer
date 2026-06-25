---
name: venue-web-discovery
description: 会場起点のWeb検索・公式/準公式ページ確認で大型イベント発表を検知し、venue_web_discovery signal、LP-ready events、設定改善を扱うときに使う。Bruno Mars / Stray Kids のような大型会場公演の検知、Codex Automation による公式根拠確認、data/venue_web_discovery_config.json 更新、event_signals.sqlite / lp_events.json 更新を行う場合に使用する。
---

# Venue Web Discovery

このSkillは、LP掲載をゴールにした大型会場イベント検知の手順を固定する。

## 原則

- LP掲載の表示優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music > ticketjam_events` とする。
- Google検索結果、AI概要、一般ニュース、SNS単体、二次流通単体はDB更新根拠にしない。
- DB更新根拠にできるのは `venue_official`、`artist_official`、`promoter_official`、`ticket_official` の公式/準公式ページ本文だけ。
- Skill本文は自動編集しない。Codexが自動調整できるのは `data/venue_web_discovery_config.json` の設定と confirmed event rows だけ。
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
5. `data/venue_web_discovery_config.json` の `confirmed_events` に、根拠付き候補を追加または更新する。各行に `content_extractor` を記録する。
6. `python -m scripts.update_event_signals_data --only venue_web_discovery` を実行し、`data/event_signals.sqlite` に反映する。
7. `python -m scripts.build_lp_events` を実行し、`data/lp_events.json` を再生成する。
8. `python -m scripts.build_external_events_manifest --release-tag external-events-latest` を実行し、manifest に `lp_events.json` を含める。
9. 重複統合結果で、同一イベントの表示sourceが最上位だけになっていることを確認する。

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

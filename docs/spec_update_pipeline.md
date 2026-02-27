# docs/spec_update_pipeline.md（全文置換）

# spec_update_pipeline — 更新パイプライン仕様

## 目的
推移表Excelの更新を検知し、正規化したデータ（sqlite + meta）を生成・更新する。

## 実行箇所（MVP）
- GitHub Actions（schedule + workflow_dispatch）
- ローカル手動実行（開発時）

## 処理フロー（MVP）
1. 取得元ページのHTMLを取得
2. 推移表ExcelのURLを抽出
3. Excelをダウンロード
4. sha256 を計算し、前回値と比較（差分が無ければ終了）
5. Excelを読み込み、想定3シート（`1-2/2-2/3-2`）をパースしてRAW化
   - 読み込みは openpyxl の `load_workbook(..., read_only=False, data_only=True)` を採用する
   - `read_only=False` は、セル参照型のパースで性能劣化が出るケースを避ける目的
6. 全国（00）は 01〜47 合算で生成
7. SQLite（market_stats）を再構築（MVPは replace で良い）
8. meta.json を更新
9. GitHub Actionsで更新があれば commit/push

## 冪等性
- 同じExcel（hash同一）なら出力を更新しない（commitしない）

## 失敗時
- HTML構造変更でURL抽出に失敗した場合：
  - Actionsは失敗（赤）
  - 次対応として scripts側にフォールバック（手動URL指定）を追加する余地はある（P1）

## 追記: 2系統データ更新（2026-02-11）
- workflow `update_data.yml`（core data）は以下を順次実行する。
  - `python -m scripts.update_data`
  - `python -m scripts.update_tcd_data`
- 差分がある場合は `data/` を含めて commit/push する。

## 追記: TCD更新パイプライン（MVP）
1. 観光庁「旅行・観光消費動向調査」ページから `集計表` Excelリンクのみ収集する。
2. 確報（年次・四半期）および2次速報（四半期）を対象にする。
3. Excelの `表題` シート A1 を優先し、`period_type` / `period_key` / `release_type` を判定する。
4. `T06` シートで `宿泊数` 行を起点に8行（1泊..8泊以上）を抽出する。
5. `data/market_stats.sqlite` の `tcd_stay_nights` テーブルを再構築する。
6. `data/meta_tcd.json` に `processed_files(url, sha256, title_a1, fetched_at)` を保存する。
7. 取得元hashに差分がない場合は no-op とする。

## 追記: 自動更新スケジュール（2026-02-13）
- GitHub Actions `update_data.yml` の定期実行は `cron: 0 3 * * 1`。
- 実行時刻は毎週月曜 03:00 UTC（日本時間 月曜 12:00）。
- 手動実行は `workflow_dispatch` を使う。

## Addendum (2026-02-25) Workflow Split for Event Official Data
- `update_data.yml` は core統計データ更新のみを担当する（会場公式イベント更新を含めない）。
- 会場公式イベント更新は `update_events_official.yml` へ分離する。
  - 実行: `python -m scripts.update_events_data --skip-artist-inference` → `python -m scripts.build_events_artist_inferred`
  - 定期実行: `cron: 0 4 * * 1`（毎週月曜 04:00 UTC）
- 目的: 失敗分離（events側の障害でcore統計更新を止めない）と運用負荷の分離。

## ICD/TA Additions
- Add: python -m scripts.update_icd_data
- Add: python -m scripts.update_ta_data
- ICD updates icd_spend_items / icd_entry_port_summary and data/meta_icd.json.
- TA updates ta_company_amounts and data/meta_ta.json.

## Airport Volume Addition
- Add: `python -m scripts.update_airport_volume_data`
- Updates table: `airport_arrivals_monthly` in `data/market_stats.sqlite`
- Updates meta: `data/meta_airport_volume.json`
- No-op rule: if downloaded source `signature` is unchanged, sqlite/meta are not updated.


## Addendum (2026-02-18) Stay Facility Occupancy
- `python -m scripts.update_data` now also parses sheet `4-2` (monthly facility-type occupancy).
- A new sqlite table `stay_facility_occupancy` is rebuilt on each successful update.
- No-op condition is `source_sha256` + `pipeline_version` match.
- `meta.json` stores occupancy row count and min/max ym.

## Addendum (2026-02-18) Stay Facility Occupancy Scope Expansion
- Sheet `4-2` parsing now keeps both nationwide (`00`) and prefecture rows (`01-47`).
- Output table `stay_facility_occupancy` stores `pref_code` and `pref_name`.

## Addendum (2026-02-22) Event Hub
- Script: `python -m scripts.update_events_data`
- Flow:
  1. `data/venue_registry.csv` を読み、`is_enabled=1` の会場を処理
  2. 会場ごとに `source_type` に対応するプラグインでイベント取得
  3. 日付ウィンドウフィルタ（today-30 〜 today+365）を適用
  4. 会場署名（sha256）で no-op 判定 → 変化なしの会場は DB 更新スキップ
  5. 変化ありの場合のみ events UPSERT（`data_hash` 差分のみ更新）
  6. `data/events.sqlite` に出力
- Domain throttle: `DomainThrottle` クラスで同一ドメイン間 3秒、異ドメイン間 1秒
- 日付フィルタ: 取得後・署名計算前に `filter_events_by_date()` で範囲外を除外
- 失敗隔離: 会場単位 try/except、1会場失敗で全体を落とさない
- 全 enabled 会場が全滅した場合のみ exit code 1
- 会場追加手順: `data/venue_registry.csv` に1行追加 → 対応する source strategy を実装
- CLI options: `--limit N`, `--only venue1,venue2`, `--verbose`
- 対応ストラテジー: yokohama_arena_json, zepp_schedule, saitama_arena_schedule, tokyo_dome_calendar, vantelin_dome_schedule, kyocera_dome_schedule, belluna_dome_schedule, makuhari_messe_schedule, fukuoka_paypay_dome_schedule, k_arena_yokohama_schedule, sapporo_dome_schedule, zozo_marine_stadium_schedule, pia_arena_mm_schedule, portmesse_nagoya_events, asue_arena_osaka_events, nissan_stadium_calendar, mufg_stadium_schedule, marine_messe_fukuoka_event

## Addendum (2026-02-25) Event Artist Inference
- `python -m scripts.update_events_data` 実行後に、`python -m scripts.build_events_artist_inferred` を自動実行して `data/events_artist_inferred.csv` を更新する。
- 補完辞書は `artist_registry.seed.csv + artist_registry.jp.seed.csv + artist_registry.manual.csv` を統合して利用する。
- 推論対象は `performers` が空のイベントで、`title` に加えて `description` も参照する。
- `events_artist_inferred.csv` は `event_uid` を持ち、アプリ側は `event_uid` 一致を優先して補完する（互換で `title` 一致も許容）。
- `build_events_artist_inferred` は CSV 更新後に `events.sqlite` へ同期し、`events.artist_name_resolved` / `events.artist_confidence` を更新する。
  - `performers` がある場合: `artist_name_resolved` は source 値（辞書一致時は canonical 化）を採用し、`artist_confidence` は `source` or `source_normalized`
  - `performers` が空で推論成功の場合: `artist_name_resolved` は推論名、`artist_confidence` は `high` or `medium`
  - どちらもない場合: `artist_name_resolved` は空、`artist_confidence` は `low`
- 誤補完低減のため、`DOME` など汎用語エイリアスと、`ベン/たま/ナビ` 等の曖昧短縮aliasを補完候補から除外する。
- `title` 単体推論は音楽イベントキーワードに一致する場合のみ採用し、就活/展示会/スポーツ系の非音楽キーワードを含むタイトルは除外する。

## Addendum (2026-02-25) Artist Registry Monthly Refresh
- Workflow: `.github/workflows/update_artist_registry.yml`
- Schedule: monthly (`cron: 20 3 1 * *`) + `workflow_dispatch`
- Flow:
  1. `artist_registry.seed.csv` を Wikidata（`--countries kr`）で更新
  2. `artist_registry.jp.seed.csv` を Wikidata（`--countries jp`）で更新
  3. `build_events_artist_inferred` を実行して補完CSVを再生成
- No-op policy:
  - seed生成時、`artist_id` ごとに実データ（canonical/aliases/source/is_enabled）が不変なら既存 `updated_at` を保持する。
  - 実データ差分がある行だけ `updated_at` を当日へ更新する。
  - 生成結果がファイル同一なら commit しない。
- Manual override policy:
  - `artist_registry.manual.csv` は workflow で上書きしない。
  - 同一 `artist_id` が seed と manual にある場合、利用時は manual を優先する（ローダーで後勝ちマージ）。

## Addendum (2026-02-23) Event Signals (News)
- Script: `python -m scripts.update_event_signals_data`
- Update target DB: `data/event_signals.sqlite`
- Scope note (for BCL consumers):
  - `event_signals.sqlite` is a news-signal feed focused on music live/concert topics.
  - It is not a complete multi-category events master DB.
- Sources (MVP):
  - `starto_concert`（STARTO 公演情報 / CONCERT）
  - `kstyle_music`（Kstyle MUSIC）
- Source-specific extraction policy:
  - `starto_concert`: `https://starto.jp/s/p/live?ct=concert` 一覧から公演詳細（`/s/p/live/<id>`）を巡回し、SCHEDULE（日付・開演時間・会場）を抽出する
  - `kstyle_music`: 記事詳細本文に `■公演情報`（実データ上の `■開催概要` 含む）がある記事のみ対象とし、該当セクションから会場・日時情報を抽出する
  - 両sourceとも日本公演のみ採用（都道府県/日本開催キーワードで判定）
- Source failure isolation:
  - source単位で例外隔離（片方失敗でも片方は継続）
- No-op:
  - sourceごとに `signal_uid -> content_hash` から signature を算出
  - `signal_sources.last_signature` と一致する場合、当該sourceのDB更新をスキップ
  - `signals` は `content_hash` が変わった行のみ UPSERT
  - `signal_sources.updated_at_utc/last_signature` は変化がある場合のみ更新
- Access policy:
  - `requests.Session` + UA明示
  - User-Agent: `market-stats-viewer-signals-bot/1.0 (+https://deltahelmlab.com/)`
  - ドメイン単位レート制限（全GETに適用）
- CLI:
  - `--only starto_concert,kstyle_music`
  - `--verbose`
- Workflow:
  - `.github/workflows/update_signals.yml`
  - `workflow_dispatch` + 定期実行（12時間ごと）
  - 差分がある場合のみ commit

## Addendum (2026-02-27) Entity Alias Governance
- `python -m scripts.update_event_signals_data` 実行時に、`labels_json` の `artist_name` / `venue_name` を辞書正規化する。
  - 同時に `raw_artist_name` / `raw_venue_name` を保存し、取得元原文を保持する。
  - 辞書未解決の候補はログへ出力し、辞書メンテ対象として扱う。
- アーティスト辞書更新ルール:
  - 定期更新は既存の月次 workflow（`update_artist_registry.yml`）を継続する。
  - 自動更新対象は seed のみ（manual は自動更新しない）。
- 会場辞書更新ルール:
  - 会場は `venue_id` を不変IDとして扱い、正本は `data/venue_registry.csv`。
  - 別名・表記ゆれ・ニュース由来表記は `data/venue_aliases.csv` で吸収する。
  - 会場名変更が発生した場合:
    1. `venue_registry.csv` の `venue_name` を新正式名へ更新
    2. 旧正式名を `venue_aliases.csv` の `aliases_json` へ追加
    3. `venue_id` は変更しない
  - 会場辞書は現時点で Wikidata 自動同期しない（誤マッチ回避のため手動レビュー前提）。
  - 新規候補の反映タイミングは「`update_signals` ログで未解決候補を検知したとき」または「会場公式名称変更の確認時」。

## Addendum (2026-02-25) External Events Release Assets
- Workflow: `.github/workflows/publish_external_events_assets.yml`
- Trigger:
  - `workflow_run`（`Update events official data` / `Update event signals data` が `main` で成功したとき）
  - `workflow_dispatch`（手動再公開）
- Release:
  - tag: `external-events-latest`
  - assets: `events.sqlite`, `event_signals.sqlite`, `manifest.json`
- Manifest generation:
  - script: `python -m scripts.build_external_events_manifest --release-tag external-events-latest`
  - output: `data/manifest.json`
  - contains: `generated_at_utc`, `source_repository`, `source_commit_sha`, assetごとの `size_bytes` / `sha256`
- Upload policy:
  - `gh release upload ... --clobber` を使い、同名assetを上書きして常に最新を保持する

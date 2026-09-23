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
   - HTMLは実レスポンスの文字コードを補正し、日本語リンク文字列の判定を壊さないようにする
   - `推移表` を含む Excel リンクを優先する
3. Excelをダウンロード
4. sha256 を計算し、前回値と比較（差分が無ければ終了）
5. Excelを読み込み、月別推移の3シート（`1-* / 2-* / 3-*`）をパースしてRAW化
   - 現行ファイルは当年分を `1-1/2-1/3-1`、過去年分を `旧1-2/旧2-2/旧3-2` に分けている
   - シートは固定名ではなく、数値プレフィックスで current / legacy の両方を解決して結合する
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

## 追記: core統計データ更新（2026-02-11、2026-04-13更新）
- workflow `update_data.yml`（core data）は以下を順次実行する。
  - `python -m scripts.update_data`
  - `python -m scripts.update_tcd_data`
  - `python -m scripts.update_icd_data`
  - `python -m scripts.update_ta_data`
  - `python -m scripts.update_airport_volume_data`
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
  - 定期実行: `cron: 0 4 */3 * *`（各月1日から3日刻みで 04:00 UTC / 日本時間 13:00）
  - GitHub Actions の cron は「厳密に72時間ごと」を表現できないため、実運用は day-of-month step による「3日ごと目安」とする。
- 目的: 失敗分離（events側の障害でcore統計更新を止めない）と運用負荷の分離。

## ICD/TA Additions
- Add: `python -m scripts.update_icd_data`
- Add: `python -m scripts.update_ta_data`
- ICD updates `icd_spend_items` / `icd_entry_port_summary` and `data/meta_icd.json`.
  - ICD period metadata accepts both quarterly labels such as `2026年1-3月期【1次速報】` and annual labels such as `2025年（令和7年） 暦年【確報】`.
  - Annual metadata is saved as `period_label=YYYY年年間`, `period_key=YYYY`, and the detected `release_type`.
- TA updates `ta_company_amounts` and `data/meta_ta.json`.

## Airport Volume Addition
- Add: `python -m scripts.update_airport_volume_data`
- Updates table: `airport_arrivals_monthly` in `data/market_stats.sqlite`
- Updates meta: `data/meta_airport_volume.json`
- No-op rule: if downloaded source `signature` is unchanged, sqlite/meta are not updated.


## Addendum (2026-02-18) Stay Facility Occupancy
- `python -m scripts.update_data` now also parses sheet `4-*` (monthly facility-type occupancy).
- Current workbook uses `4-1` for current year and `旧4-2` for historical months.
- Update flow merges both sheets into one monthly series.
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
  - 2026-03-11 追加: `panasonic_stadium_suita_schedule`（`/schedule/index/year/YYYY/month/MM/` の月次HTML表）
  - 2026-03-11 追加: `edion_arena_osaka_pdf_schedule`（トップページに掲載される `monthlyYYMM.pdf` を取得し、第1競技場のみ抽出）
  - 署名 no-op 補足: `data_hash` が同じでも `artist_name_resolved` / `artist_confidence` / `event_category` が変わった場合は導出列だけ再同期する
  - `nissan_stadium_calendar` は開始欄の `19時30分` を `19:30` と解釈し、分を落とさない。
  - `tokyo_dome_calendar` は `開演` / `開始` / `START` を使い、開場時刻だけでは開始時刻を補完しない。開始時刻を含むsource keyが訂正される場合は、同じURL・日付・公演の旧行を訂正後のkeyへ移し、二重登録を防ぐ。利用側は更新済みsnapshotの全件再取込で同期する。
  - `mufg_stadium_schedule` は互換のため残す旧識別子で、実際の取得元は味の素スタジアム。開演・開始・START・キックオフの明示時刻だけを採用し、OPENや問い合わせ受付時間で補わない。

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
- カタカナ語の途中にある辞書名は照合しない（例: `ジョイン` 内の `ジョイ`、`コンサート` 内の `コーン`）。長音・記号を圧縮する照合でも、この条件を維持する。
- 3文字以下の名前、または6文字以下の英数字名は、本文内に出現しただけでは出演者と確定しない。先頭の年号・会場側の `コンサート` 見出しを除いた先頭一致、またはcanonical名への明示的な出演表現（`presents`、`LIVE ... WITH`、`This is`）を必要とする。最良候補が曖昧なら別のタイトル語へ繰り上げず、未解決へ戻す。
- `title` 単体推論は音楽イベントキーワードに一致する場合のみ採用し、就活/展示会/スポーツ系の非音楽キーワードを含むタイトルは除外する。
- 例外として、音楽イベントキーワードがなくても、辞書の canonical artist name がタイトル先頭に高信頼で一致し、かつ非音楽キーワードを含まない場合は `title` 単体推論を採用する。alias だけがタイトル先頭に一致する場合は採用しない。

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

## Addendum (2026-02-23) Event Signals (News / Secondary Reference)
- Script: `python -m scripts.update_event_signals_data`
- Update target DB: `data/event_signals.sqlite`
- Scope note (for BCL consumers):
  - `event_signals.sqlite` stores official/semi-official Web discovery and news signals.
  - It is not a complete multi-category events master DB.
- Sources (MVP):
  - `venue_web_discovery`（Codex Automation が公式/準公式ページ本文を確認した会場起点Web検知）
  - `starto_concert`（STARTO 公演情報 / CONCERT）
  - `kstyle_music`（Kstyle MUSIC）
- Source-specific extraction policy:
  - `venue_web_discovery`: `.agents/skills/venue-web-discovery/SKILL.md` を使う Codex Automation が会場起点で検索し、公式/準公式ページ本文に公演日、会場、アーティスト/イベント名が揃う候補だけをinboxへ書く。GitHub Actionsがinboxを `data/venue_web_discovery_config.json` の `confirmed_events` に適用する。保存処理は設定ファイルを読み、`event_signals.sqlite` の `source_id=venue_web_discovery` として `labels_json` に `event_start_date`、`event_end_date`、`venue_name`、`raw_venue_name`、`artist_name`、`raw_artist_name`、`event_category`、`source_class`、`confidence`、`evidence_url`、`evidence_snippet` を保存する。
    - DB更新根拠にできる `source_class` は `venue_official` / `artist_official` / `promoter_official` / `ticket_official` のみ。
    - Google検索結果、AI概要、一般ニュース、SNS単体、二次流通単体は発見導線として使えてもDB更新根拠にしない。
    - DB schema は増やさず、設定ファイルと `labels_json` で運用する。
    - `event_status=postponed|cancelled` の保存、LP表示抑止、振替公演、Release gateは `docs/spec_event_status.md` を正本とする。
    - Skill本文とconfigはCodex Automationから変更しない。automationが書くのは `data/venue_discovery_inbox.json` のみ。
    - 本文抽出providerは `content_extractor=requests_bs4|crawl4ai|browser` とする。既定は `requests_bs4`、`crawl4ai` は optional fallback provider であり、JS生成ページ、`requests_bs4` 失敗ページ、公式サイト内crawlやリンク探索が必要なページ、アーティスト公式サイトだけに使う。
    - `crawl4ai` は optional dependency とし、通常の `uv sync --frozen` では必須にしない。必要な環境だけ `uv sync --extra crawl4ai`、`uv run crawl4ai-setup`、`uv run crawl4ai-doctor` を実行する。
    - Firecrawl は将来の paid optional provider として保留し、browser-use は調査・Skill改善・例外調査用に保留する。
    - `content_extractor` は確認に使った抽出providerの監査ラベルであり、DB採用根拠そのものではない。採用根拠は常に公式/準公式URLと本文根拠である。
  - `starto_concert`: `https://starto.jp/s/p/live?ct=concert` 一覧から公演詳細（`/s/p/live/<id>`）を巡回し、SCHEDULE（日付・開演時間・会場）を抽出する
  - `kstyle_music`: recent news sitemap、検索結果、必要な場合の `backfill_article_urls` 明示URLから記事を取得する。記事詳細本文に `■公演情報`（実データ上の `■開催概要` 含む）がある記事のみ対象とし、該当セクションから会場・日時情報を抽出する。`backfill_article_urls` は監査で本文・日程・会場を確認済みだが通常入口から漏れた記事だけに使い、取得対象ソースの優先順位は変更しない。
- `starto_concert` / `kstyle_music` は日本公演のみ採用（都道府県/日本開催キーワードで判定）
- Source failure isolation:
  - source単位で例外隔離（片方失敗でも片方は継続）
- No-op:
  - sourceごとに `signal_uid -> content_hash` から signature を算出
  - `signal_sources.last_signature` と一致する場合、当該sourceのDB更新をスキップ
  - `signals` は既定で `content_hash` が変わった行のみ UPSERT
  - `signal_sources.updated_at_utc/last_signature` は変化がある場合のみ更新
- Event text quality gate:
  - source parser完了後、DBのclear/prune/upsert/signature更新より前に、表示・統合に使うイベント文字列を共通validatorで検証する
  - Unicode replacement character、禁止control character、または「元文字列を既知の誤encodingへencodeしてUTF-8 strict decodeすると日本語へ復元できる」高確度な誤decodeを拒否する
  - 正常なCyrillic、絵文字、アクセント付きLatin文字、日本語記号は許可する。文字種だけを根拠に拒否しない
  - 不正レコードが1件でもあるsource更新はDB変更前に失敗させる。部分反映、黙示除外、自動逆変換はしない
  - `build_lp_events` は `events.sqlite` / `event_signals.sqlite` 由来レコードを同じvalidatorでpreflightし、不正時はoutputを書かない
  - 既存破損データの回復はcanonical event URL単位で再取得し、正常レコードへ置換する。最古の `first_seen_at_utc` を保持し、UID/content hash/LP event keyを再計算して監査する。通常の `new_only` による自然回復へ依存しない
- Access policy:
  - `requests.Session` + UA明示
  - User-Agent: `market-stats-viewer-signals-bot/1.0 (+https://deltahelmlab.com/)`
  - ドメイン単位レート制限（全GETに適用）
- CLI:
  - `--only venue_web_discovery,starto_concert,kstyle_music`
  - `--verbose`
- LP-ready output:
  - Script: `python -m scripts.build_lp_events`
  - Inputs: `data/events.sqlite`, `data/event_signals.sqlite`
  - Output: `data/lp_events.json`
  - 通常生成の履歴範囲: 基準日から90日前まで。`--past-days N` でboundedな日数を変更でき、`--include-past` は監査・再生成用に保存済み過去行を全件含める。
  - 履歴判定は開催開始日ではなく `event_end_date` を使い、基準日時点で開催中の複数日イベントを過去扱いしない。
  - payloadは `include_past`、`history_window_days`、`history_start_date` を持つ。通常生成は `include_past=true`、`history_window_days=90` とする。
  - Grouping key: `event_date + canonical venue_name + canonical artist_name`
  - Display source priority: `official_events > venue_web_discovery > starto_concert/kstyle_music`
  - Lower-priority matches are retained in `supporting_sources`.
- Workflow:
  - `.github/workflows/update_signals_venue_web_discovery.yml`（公式/準公式Web検知）: 定期実行、手動実行、または`main`の`data/venue_discovery_inbox.json`へのpushで起動する。inbox適用、`venue_web_discovery`のDB更新、`lp_events.json`生成、focused testsと一時manifest検証を順に行い、差分があればconfig・DB・LPをcommit/pushする。inboxはActionsから変更しない。repository variable `VENUE_WEB_DISCOVERY_ENABLE_CRAWL4AI=true` のときだけoptional Crawl4AI setupを行う。
  - `.github/workflows/update_signals.yml`（ニュース: `starto_concert,kstyle_music`）: 12時間ごとの定期実行と手動実行を受け、DBとLPを更新する。
  - `.github/workflows/update_events_official.yml`（会場公式）: 定期実行と手動実行を受け、会場公式DBとLPを更新する。
  - `.github/workflows/watch_automation_freshness.yml`（停止検知）: 毎日cronまたは手動でinboxの鮮度を検査する。
  - 各更新workflowは`build_lp_events`を後段で実行し、差分がある場合だけcommitする。

## Addendum (2026-05-12) Event Signal Coverage and Normalization Audit
- 目的:
  - 会場公式以外のイベント情報について、記事取得前の取りこぼし、本文抽出失敗、辞書未解決、カテゴリ誤分類、同一イベントの未統合を分けて検知する。
  - 初期対象は `kstyle_music` とする。`starto_concert` へ広げるかは、K-Style監査の出力形式と運用負荷を確認してから判断する。
- 非目標:
  - 監査の初期実装では、`events.sqlite` / `event_signals.sqlite` の既存スキーマを変更しない。
  - 監査の初期実装では、ニュース記事本文全文を保存しない。保存するのはURL、タイトル、掲載日時、短い根拠文字列、抽出結果、判定理由とする。
  - 会場公式データをニュース由来データで上書きしない。同一日程が会場公式に存在する場合、利用側の優先表示は従来どおり会場公式を優先する。
- 取得漏れ監査:
  - 入力:
    - K-Style の recent news sitemap
    - K-Style の検索結果（例: `■公演情報`, `■開催概要`）
    - K-Style の musicカテゴリページまたは newest ページ
    - 既知の取得漏れURLサンプル。これは入口監査とは別に、過去に漏れた実例を現行parserが抽出できるかを確認する回帰サンプルとして使う。
    - 既存 `data/event_signals.sqlite` の `kstyle_music` 行
  - 監査軸:
    1. 取得頻度: 現行のニュース更新間隔（12時間ごと）で、候補記事が次回取得までに取得入口から流れていないかを確認する。
    2. 取得入口: sitemap、検索結果、カテゴリページ、newestページのどこで候補記事を発見できるかを比較する。
    3. 取得件数上限: `pages`、`sitemap_max_candidates`、カテゴリページ巡回数を変えた場合に、候補記事数とノイズ記事数がどの程度変わるかを記録する。
    4. parser抽出可否: 記事本文に公演日程があるが、現行parserが `event_start_date`、`venue_name`、`artist_name` を抽出できない記事を検知する。
  - 監査後の低リスク取り込み:
    - K-Style の通常入口から漏れた記事でも、記事本文に日本国内公演の日付と会場が明記され、現行parserで `event_start_date` と `venue_name` を抽出できる場合は、`kstyle_music` の `backfill_article_urls` に明示URLとして追加できる。
    - `backfill_article_urls` は過去漏れの限定的な補完であり、source優先順位、DBスキーマ、LP表示契約、Release asset更新条件を変更しない。
    - `parser_gap`、海外公演、本文詳細未確認、または日本国内公演か判断できない候補は `backfill_article_urls` に追加しない。
  - 出力:
    - `articles_scanned`: 取得入口ごとの記事数
    - `candidate_articles`: 公演候補記事数
    - `matched_existing_articles`: 既存 `kstyle_music` に同一URLが存在する記事数
    - `missed_candidate_articles`: 記事URL単位の取得漏れ候補
    - `missed_occurrences`: 日程単位の取得漏れ候補
    - `miss_reason`: `frequency_gap` / `entry_gap` / `page_limit_gap` / `parser_gap` / `normalization_gap`
    - `oldest_candidate_in_scan` / `newest_candidate_in_scan`
    - `recommended_frequency_hours`
    - `recommended_pages`
    - `recommended_sitemap_max_candidates`
- 正規化監査:
  - イベント正規化:
    - 比較キーは `event_date + canonical venue_name + canonical artist_name` を基本とする。
    - 同一キーに複数ソースが存在する場合は重複削除ではなく、同一イベント候補として `same_event_candidates` に出力する。
    - 同一キーに近いが、会場名またはアーティスト名だけが未解決で一致できない場合は `normalization_gap` として出力する。
  - 会場正規化:
    - `raw_venue_name` を `venue_registry.csv` と `venue_aliases.csv` で解決できるか確認する。
    - 住所付き会場名、地域接頭辞付き会場名、表記ゆれを `venue_alias_candidates` として出力する。
    - 会場名変更の場合は `venue_id` を変更せず、旧名称を `venue_aliases.csv` に追加する候補として出力する。
  - アーティスト正規化:
    - `raw_artist_name` を `artist_registry.seed.csv`、`artist_registry.jp.seed.csv`、`artist_registry.manual.csv` で解決できるか確認する。
    - 未解決、曖昧一致、短いaliasによる誤一致候補を `artist_alias_candidates` として出力する。
    - `manual` 辞書は自動上書きしない。自動反映する場合もCodex automationが差分を作成し、verifyを通す。
  - カテゴリ精査:
    - `event_category=その他` だが、タイトル、説明、artist解決結果、本文根拠から音楽イベントと判断できる候補を `category_review_candidates` に出力する。
    - `event_category=コンサート` だが、展示会、物販、配信、受賞式、テレビ放送など日程需要への影響が限定的な候補も `category_review_candidates` に出力する。
- Codex automation の役割:
  - イベント情報監査手順:
    - 正本: `docs/event_signal_audit_automation.md`
    - Codex automation は、監査レポート生成、低リスク修正案の作成、verify、PR作成、自動マージ判定、マージ後監査までを行う。
    - Codex automation は `data/event_signal_audit_report.json` の `summary.automation_bucket_counts`、`summary.candidate_lp_impact_counts`、`summary.lp_impact` を確認し、候補配列内の各行が持つ `automation_bucket`、`lp_impact`、`needs_review_reason` と `needs_review` 一覧を読んで、「自動マージ可」「PR作成のみ」「人間確認が必要」を分ける。
    - 自動マージ可否のチェックリストは `docs/event_signal_audit_automation.md` の `Auto-merge Gate Checklist` を正本とする。
    - 自動マージした場合は、同じ手順書の `Post-merge Audit` を必ず実行し、実際の差分、DB行、LP影響、禁止ファイルの有無を確認する。
  - 自動で行ってよいこと:
    - 監査レポート生成
    - 低リスクな `venue_aliases.csv` 追加案の作成
    - 低リスクな `artist_registry.manual.csv` 追加案の作成
    - 狭いparser形式対応のPR作成
    - 監査スクリプト、K-Style更新、辞書監査、カテゴリ監査、補完評価レポート生成のverify
  - 自動マージを許可する条件:
    - 変更対象が監査レポート、alias追加、テスト追加、K-Style parserの狭い形式対応、またはK-Style確認済み候補の限定取り込みに限られる
    - `events.sqlite` / `event_signals.sqlite` の大規模再生成を含まない
    - `data/event_signals.sqlite` を変更する場合、`source_id='kstyle_music'` の本文確認済みURLに対する限定追加または更新だけである
    - `venue_id` / `artist_id` の変更を含まない
    - verify がすべて成功する
    - `needs_review_reason` が残っていない
    - 外部LP向けの配布データ影響が `lp_impact=none`、または影響内容が `display_count_change` / `category_change` / `duplicate_grouping_change` / `source_priority_change` として明示され、想定どおりである
    - 自動マージ後に `Post-merge Audit` を実行し、結果を記録する
  - 自動マージしない変更:
    - DBスキーマ変更
    - 会場正式名変更
    - 新しい外部サービス依存
    - parser全体の大幅再設計
    - 取得対象ソースの大幅追加
    - `data/manifest.json` 更新
    - Release asset 更新
    - source優先順位変更
- 外部LPへの影響確認:
  - 外部LPが利用する配布単位は `events.sqlite` / `event_signals.sqlite` / `lp_events.json` / `manifest.json` である。
  - 監査スクリプト追加、監査レポート生成、docs更新だけでは、配布DBとmanifestの内容を変更しないため、LP表示への直接影響はない。
  - 辞書、カテゴリ分類、parser、取得件数、取得頻度を変更する場合は、LP側の表示件数、カテゴリ表示、同一イベントのまとまり、会場公式・ニュース・二次流通の優先順位に影響し得る。
  - 統合監査レポートは `summary.lp_impact` と候補ごとの `lp_impact` を出力する。値は `none`、`display_count_change`、`category_change`、`duplicate_grouping_change`、`source_priority_change` のいずれか、または複数とする。

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
  - 対象範囲は「`capacity >= 10000` を基本対象、`1000 <= capacity < 10000` は重点会場のみ」とする。
    - `capacity >= 10000`: 公式ソース未実装でも `is_enabled=0` の辞書用途で保持する。
    - 重点会場: 会場公式取得対象、または公式/準公式Web検知と辞書照合に継続的に必要な会場を登録する。
    - `capacity < 1000` または capacity 不明: 明示要件が出るまで常設対象外。
  - 会場名変更が発生した場合:
    1. `venue_registry.csv` の `venue_name` を新正式名へ更新
    2. 旧正式名を `venue_aliases.csv` の `aliases_json` へ追加
    3. `venue_id` は変更しない
  - 会場辞書は現時点で Wikidata 自動同期しない（誤マッチ回避のため手動レビュー前提）。
  - 新規候補の反映タイミングは「`update_signals` ログで未解決候補を検知したとき」または「会場公式名称変更の確認時」。

## Addendum (2026-02-25) External Events Release Assets
- Workflow: `.github/workflows/publish_external_events_assets.yml`
- Trigger:
  - `push`（`main` で配布入力または公開workflowが更新されたとき）
    - 対象path: `.github/workflows/publish_external_events_assets.yml`, `scripts/build_external_events_manifest.py`, `data/events.sqlite`, `data/event_signals.sqlite`, `data/lp_events.json`
    - ローカルcheckoutから直接pushされた配布入力またはmanifest生成処理の更新を自動公開する。push起点ではtrigger commitをcheckoutして、manifestの`source_commit_sha`とasset内容を一致させる。公開workflow自身の変更も対象に含め、導入PRのmerge直後に現行assetを再公開する。
  - `workflow_run`（`Update events official data` / `Update event signals data (News)` / `Update event signals data (Venue Web Discovery)` が `main` で成功したとき）
    - GitHub Actionsが`GITHUB_TOKEN`で作成したcommitは後続の`push` workflowを起動しないため、scheduled/manualの上流workflow経路として維持する。
  - `workflow_dispatch`（手動再公開）
- Release:
  - tag: `external-events-latest`
  - assets: `events.sqlite`, `event_signals.sqlite`, `lp_events.json`, `manifest.json`
- Manifest generation:
  - script: `python -m scripts.build_external_events_manifest --release-tag external-events-latest`
  - output: `data/manifest.json`
  - contains: `generated_at_utc`, `source_repository`, `source_commit_sha`, assetごとの `size_bytes` / `sha256`
- Upload policy:
  - script: `python -m scripts.upload_release_assets --tag external-events-latest <files...>`。同名assetを削除してから再uploadし、常に最新を保持する。upload順は `events.sqlite` → `event_signals.sqlite` → `lp_events.json` → `manifest.json`。
  - tagはrelease idの解決だけに使い、asset一覧・削除・upload・検証は `releases/{release_id}/assets` 系endpointで行う。直前の別publishでassetが置換された後、`releases/tags/{tag}` とrelease一覧endpointは削除済みasset idを数分以上返し続けることがあり（2026-09-23 run 35835686906で `gh release upload --clobber` がHTTP 404）、`gh release upload --clobber` はこのstale一覧を使うため採用しない。
  - 削除時の404は「既に削除済み」として扱う。upload時の422（同名asset残存）と5xxは最大3回（待機20s / 40s）まで再試行する。
  - upload後にid scoped一覧で各assetが1件・`state=uploaded`・sizeと`digest`（sha256）がローカルと一致することを確認し、不一致ならstepを失敗させる。
  - `concurrency: release-assets-${{ github.ref }}`（`cancel-in-progress: false`）でpublishを直列化する。
  - 利用側で `gh release download` など tag endpoint経由でassetを解決する場合も同じstaleの影響を受け得る（置換直後にHTTP 404）。利用側の再試行やid scoped endpoint利用は各repo側で扱う。
- 再実行手順:
  1. ローカルcheckoutから`main`へ対象pathを直接pushした場合は`push` run、上流GitHub Actionsが完了した場合は`workflow_run` runを確認する
  2. publish run が `failure` / `cancelled` の場合は原因を修正して再実行する。上流workflowが `failure` / `cancelled` / `skipped` の場合は、先に上流workflowを復旧または再実行する
  3. 対象更新後にpublish runが存在しない、またはrelease assetが更新されていない場合は、`publish_external_events_assets.yml` を `workflow_dispatch` で手動実行する
  4. 確認は GitHub Release `external-events-latest` の asset `updated_at` と `manifest.json` の `generated_at_utc` / `source_commit_sha` を見る

### 会場起点Web検知からLP配布への継続運用

- MacBook Pro上のCodex app automation `msv-venue-discovery`（`gpt-6-sol` / medium）は、会場起点で公式/準公式ページ本文を確認し、`data/venue_discovery_inbox.json`だけを更新してpushする。既存`lp` automationは停止する。Codex Cloudには定期実行がないため、現行の定期判断はlocal automationで行う。
- inbox（schema_version 1）は`run_at_utc`、`automation_id=msv-venue-discovery`、`candidates`、`rejected`を持つ。candidateは既存`confirmed_events`と同じfield名を使い、`event_start_date`、`event_end_date`、`event_start_time`、`venue_name`、`raw_venue_name`、`artist_name`、`raw_artist_name`、`title`、`event_category`、`source_class`、`confidence`、`evidence_url`、`evidence_snippet`、`content_extractor`、`discovery_query`、`verified_at_utc`を記録する。候補は1回30件以下で、0件でも`run_at_utc`を更新する。
- `scripts.apply_venue_discovery_inbox`は、schema version、必須項目、日付形式、許可`source_class`、httpsの根拠URLと拒否domain、400文字以内の非空`evidence_snippet`、監視会場またはaliasで解決できる会場名を検査する。`event_start_date + canonical venue_name + canonical artist_name/title`が既存`confirmed_events`と一致する行は上書きしない。適用・却下・重複件数をstdoutとGitHub step summaryに、却下理由をstdoutに出す。候補の却下だけなら成功、schema不正なら失敗する。
- inboxの`main`へのpushで`update_signals_venue_web_discovery.yml`が起動し、適用後にDB、LP、manifest対象assetを検証する。成功した上流workflowを`publish_external_events_assets.yml`の`workflow_run`が受け、manifest生成・検証を経てRelease `external-events-latest`を公開する。
- `watch_automation_freshness.yml`は毎日実行し、inboxがない、または`run_at_utc`が3日より古い場合に失敗する。GitHub Actionsの失敗通知を停止検知に使う。
- `as_of_date` の既定はAsia/Tokyoの日付。UTCの`generated_at_utc`と混同しない。`data/manifest.json`はGit管理せず、Release時にcheckoutしたcommitから生成する。国内所在地が確定できない上位sourceはLPから保留し、公開validatorが47都道府県の完全一致を確認する。

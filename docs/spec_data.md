# spec_data — データ仕様（取得/正規化/保存）

## 取得元（MVP）
- 観光庁ページから「推移表（Excel）」をダウンロードする
- シート：
  - 延べ宿泊者数（総数）：`1-*`
  - 日本人延べ宿泊者数：`2-*`
  - 外国人延べ宿泊者数：`3-*`
- 観光庁の現行ファイルでは当年分が `1-1/2-1/3-1`、過去年分が `旧1-2/旧2-2/旧3-2` に分かれている。
- 取得スクリプトは固定シート名を前提にせず、数値プレフィックスで current / legacy の両方を解決して結合する。

## 正規化（RAW）
### キー
- ym：YYYY-MM
- pref_code：00（全国）, 01〜47（都道府県）
- pref_name：都道府県名 / 全国

### 値
- total：延べ宿泊者数（総数）
- jp：日本人延べ宿泊者数
- foreign：外国人延べ宿泊者数

## 全国の扱い（ズレ耐性）
- 推移表に全国行があっても、MVPでは **アプリ側生成を正**とする
  - 01〜47の合算で pref_code=00 を生成
  - 推移表由来の00行は採用しない（あれば除外する）

## 保存先
### SQLite
- path：`data/market_stats.sqlite`
- table：`market_stats`
- columns：
  - ym TEXT
  - pref_code TEXT
  - pref_name TEXT
  - total REAL
  - jp REAL
  - foreign REAL
- index：
  - ym
  - pref_code

### meta.json
- path：`data/meta.json`
- fields（例）：
  - source_page_url
  - source_xlsx_url
  - source_sha256
  - fetched_at_utc
  - rows
  - min_ym
  - max_ym

## 追補（2026-02-18）宿泊施設種別 客室稼働率
### 追加データセット
- source sheet: `4-*`（都道府県別、宿泊施設タイプ別 客室稼働率 推移表（月別））
- 観光庁の現行ファイルでは当年分が `4-1`、過去年分が `旧4-2` に分かれている。
- 取得スクリプトは current / legacy の両方を結合して時系列を再構成する。
- scope: 全国（`全 国`）のみを採用
- grain: `ym x facility_type`
- value: `occupancy_rate`（%）

### SQLite 追加テーブル
- table: `stay_facility_occupancy`
- columns:
  - `ym` TEXT
  - `facility_type` TEXT
  - `occupancy_rate` REAL
- index:
  - `ym`
  - `facility_type`

### meta.json 追加フィールド
- `pipeline_version`
- `facility_occupancy_rows`
- `facility_occupancy_min_ym`
- `facility_occupancy_max_ym`

## 追補（2026-02-18）宿泊施設種別 客室稼働率（改）
- 対象は全国（00）に加えて都道府県（01-47）を保持する。
- `stay_facility_occupancy` テーブル列:
  - `ym`, `pref_code`, `pref_name`, `facility_type`, `occupancy_rate`
- UI では全国/都道府県を切替できる前提データとする。

## 追補（2026-02-22）イベントハブ
- SSOT: `data/events.sqlite`（既存の market_stats.sqlite とは分離）
- テーブル `venues`（会場マスタ）:
  - `venue_id` TEXT PK, `venue_name`, `pref_code`, `pref_name`, `capacity`,
    `official_url`, `source_type`, `source_url`, `config_json`, `is_enabled`,
    `last_signature`, `created_at_utc`, `updated_at_utc`
- テーブル `events`（イベント本体）:
  - `event_uid` TEXT PK, `venue_id` FK, `title`, `start_date`, `start_time`,
    `end_date`, `end_time`, `all_day`, `status`, `url`, `description`,
    `performers`, `artist_name_resolved`, `artist_confidence`, `capacity`,
    `source_type`, `source_url`, `source_event_key`, `data_hash`,
    `first_seen_at_utc`, `updated_at_utc`
- `event_uid` 規約: `{venue_id}:{source_event_key}` or `{venue_id}:h:{sha256[:16]}`
- `capacity`: イベント固有があればそれ、なければ会場キャパを COALESCE で利用
- 会場定義: `data/venue_registry.csv`（1行=1会場、追加は1行追加のみ）
- `artist_name_resolved`: BCL/表示向けの解決済みアーティスト名（`performers` は取得元生値を保持）
- `artist_confidence`: `source` / `source_normalized` / `high` / `medium` / `low`

### 外部アプリ向けのイベントデータ契約
- 外部アプリが利用する配布単位は GitHub Release `external-events-latest` の `events.sqlite` / `event_signals.sqlite` / `manifest.json` とする。
- `manifest.json` は配布ファイルの鮮度と同一性を確認するためのメタデータであり、利用側は `generated_at_utc`、各 asset の `sha256`、`size_bytes` を確認できる。
- 外部アプリは、次の3層を同じ意味のイベント情報として混ぜない。
  - `events.sqlite`: 会場公式サイトまたは会場公式に準じる公開スケジュールから取得した日程。会場別の定期予定表として扱う。
  - `event_signals.sqlite` の `starto_concert` / `kstyle_music`: ニュース記事または公式に近い告知ページから抽出した速報。興行決定や追加公演の早期検知に使う。
  - `event_signals.sqlite` の `ticketjam_events`: 二次流通サイト上で確認できる参考日程。公式取得が弱い会場やニュースで拾いにくいアーティストの補完に使う。
- 外部アプリが「確定日程」として優先表示する場合は、まず `events.sqlite` を使う。`event_signals.sqlite` は速報・参考・補完として扱い、同一日程が公式側に存在する場合は公式側を優先する。
- 外部アプリが速報性を重視する場合は、`event_signals.sqlite` を使ってよい。ただし `source_id` ごとの性質を表示または内部判定に残し、ニュース由来と二次流通由来を同じ信頼度として扱わない。
- 外部アプリが同一日程を統合する場合の比較キーは、原則として `event_date + canonical venue_name + canonical artist_name` とする。
  - `events.sqlite` 側の `event_date` は `events.start_date` を使う。
  - `events.sqlite` 側の `canonical artist_name` は `artist_name_resolved` を優先し、空の場合のみ `performers` を使う。
  - `event_signals.sqlite` 側の `event_date` / `canonical venue_name` / `canonical artist_name` は `signals.labels_json` の `event_start_date` / `venue_name` / `artist_name` を使う。
- 外部アプリが新着判定を行う場合、`ticketjam_events` は `published_at_utc` ではなく `first_seen_at_utc` を使う。Ticketjam の公開ページから安定した掲載日時を取得できないためである。
- 外部アプリがデータ品質を判断する場合、少なくとも次の情報を保持する。
  - `source_id`: `events.sqlite` 由来か、ニュース由来か、二次流通由来かを判定する。
  - `url`: 利用者が元ページで確認するための参照先。
  - `updated_at_utc` または `first_seen_at_utc`: データ更新または初回検知の時刻。
  - `raw_artist_name` / `raw_venue_name`: `event_signals.sqlite` で正規化前の表記確認が必要な場合に使う。
- 外部アプリは `ticketjam_events` を会場網羅の代替として使わない。`ticketjam_events` は `artist-gap` / `venue-gap` を補う参考ソースであり、会場公式取得が安定している会場では公式データを優先する。
- 外部アプリ向けの利用例:
  - BCL などの需要予測支援: `events.sqlite` を基準にし、`event_signals.sqlite` は追加検知と早期注意喚起に使う。
  - イベント監視ダッシュボード: 3層を別ラベルで表示し、公式日程、ニュース速報、二次流通参考を分けて比較する。
  - 辞書メンテナンス支援: `raw_*` と canonical 名の差分、未解決ログ、`ticketjam_supplement_report.json` を使って artist/venue 辞書候補を抽出する。

## 追補（2026-02-23）イベント速報/参考シグナル
- SSOT: `data/event_signals.sqlite`（`events.sqlite` とは分離）
- 対象範囲（BCL向け注記）:
  - 収集ソースは `starto_concert` / `kstyle_music` / `ticketjam_events`
  - `starto_concert` / `kstyle_music` はニュース由来、`ticketjam_events` は二次流通由来の参考データ
  - 全カテゴリ横断の網羅DBではない（野球/その他イベントの網羅は目的外）
- 保存方針:
  - 本文は保存しない（ニュース全文のDB保存禁止）
  - 保存対象は `掲載日時 / タイトル / URL / 短い抜粋（一覧で取得できる場合のみ）`
  - `ticketjam_events` は `labels_json` に `artist_name / venue_name / event_start_date / event_end_date` を必須保存する
  - `ticketjam_events` は 1日程=1データを原則とし、複数日開催のシリーズでも日別ページ単位で保存する
  - `ticketjam_events` は未来開催のみを保持し、過去開催は定期更新時に除去する
  - `ticketjam_events` は会場網羅の正本DBではなく、`artist-gap` / `venue-gap` を補う参考ソースとして扱う
  - `ticketjam_events` の会場ページ対応は `data/ticketjam_venue_pages.csv` で管理する
    - 1行=1 Ticketjam 会場ページと内部 `venue_id` の対応
    - 初期 scope は 北海道 / 東京都 / 神奈川県 / 千葉県 / 埼玉県 / 愛知県 / 大阪府 / 兵庫県 / 福岡県
    - `is_enabled=1` は日次巡回対象、`is_enabled=0` は辞書保持のみ
  - 補完評価レポート:
    - `data/ticketjam_supplement_report.json`: 機械処理向けサマリ
    - `data/ticketjam_supplement_report.md`: 目視確認向けサマリ
    - `ticketjam_watch` / `ticketjam_benchmark_tier` / `official_fetch_candidate` を使って自動集計する

### テーブル: `signal_sources`
- `source_id` TEXT PRIMARY KEY
- `source_name` TEXT NOT NULL
- `source_url` TEXT NOT NULL
- `source_type` TEXT NOT NULL
- `config_json` TEXT
- `is_enabled` INTEGER NOT NULL DEFAULT 1
- `last_signature` TEXT
- `created_at_utc` TEXT NOT NULL
- `updated_at_utc` TEXT NOT NULL

### テーブル: `signals`
- `signal_uid` TEXT PRIMARY KEY（`sha256(source_id + url)`）
- `source_id` TEXT NOT NULL
- `published_at_utc` TEXT NOT NULL（ISO8601 Z）
- `title` TEXT NOT NULL
- `url` TEXT NOT NULL
- `snippet` TEXT
- `score` INTEGER NOT NULL DEFAULT 0
- `labels_json` TEXT
- `content_hash` TEXT NOT NULL
- `first_seen_at_utc` TEXT NOT NULL
- `updated_at_utc` TEXT NOT NULL

### Index
- `signals(published_at_utc)`
- `signals(source_id)`

## 追補（2026-02-27）イベント名辞書の正規化
- 目的:
  - 会場公式（`events.sqlite`）とニュース（`event_signals.sqlite`）で、同一会場/同一アーティストの表記を揃える。
- 正規化の保存方針（`signals.labels_json`）:
  - `artist_name` / `venue_name`: 正規化後の表示名を保持
  - `raw_artist_name` / `raw_venue_name`: 取得元の原文を保持（監査・辞書更新用）
- アーティスト辞書:
  - 入力ソース: `artist_registry.seed.csv` + `artist_registry.jp.seed.csv` + `artist_registry.manual.csv`
  - マージ優先順: `seed -> jp.seed -> manual`（後勝ち）
  - Ticketjam 補完フラグ列:
    - `ticketjam_watch`: `0/1`。Ticketjam の `artist-gap` 補完対象として監視するか
    - `ticketjam_benchmark_tier`: `S / A / B / reference / ""`
      - `S`: 直近1年で五大ドーム完走級
      - `A`: 全国ドームツアー級
      - `B`: 複数ドーム開催級
      - `reference`: 格としては十分だが、初期監視は後回し
    - `ticketjam_watch_reason`: 初期値は `artist_gap`
- 会場辞書:
  - 正本: `data/venue_registry.csv`（`venue_id` 固定）
  - 別名辞書: `data/venue_aliases.csv`
  - Ticketjam 会場ページ対応: `data/ticketjam_venue_pages.csv`
  - 解決優先順: `venue_registry` の正式名 + `venue_aliases` の別名（`venue_id` 単位で後勝ち）
  - 対象範囲:
    - 基本対象: `capacity >= 10000` の会場は、会場公式ソースの実装有無に関わらず辞書へ保持する。公式取得未対応でも `is_enabled=0` の辞書用途で先行登録してよい。
    - 重点会場: `1000 <= capacity < 10000` の会場は、ユーザー影響が高いものだけを対象にする。判断基準は「会場公式イベントの取得対象である」または「`ticketjam_events` の採用/未解決候補で継続的に出現し、GUI確認や辞書照合KPIに影響する」のいずれか。
    - 原則対象外: `capacity < 1000` または capacity 不明の小規模会場は、明示的な運用要件が出るまで辞書の常設対象にしない。
  - Ticketjam venue-first Phase 1 では、会場辞書へ追加した canonical 会場に対して `ticketjam_venue_pages.csv` の page URL を紐付け、Ticketjam 側 raw 表記は `venue_aliases.csv` で吸収する。
  - Ticketjam 補完フラグ列:
    - `ticketjam_watch`: `0/1`。Ticketjam の `venue-gap` 補完対象として監視するか
    - `official_fetch_candidate`: `0/1`。本来は会場公式ソース追加を検討すべき会場か
    - `official_gap_reason`: `no_official_site / weak_schedule / hard_to_parse / temporary_fallback / ""`
      - `ticketjam_watch=1` と `official_fetch_candidate=1` は両立してよい
  - 補完評価レポートの集計キー:
    - `event_date + canonical venue_name + canonical artist_name`
    - baseline は `events.sqlite` + `starto_concert` + `kstyle_music`
- 一意性ルール:
  - 正規化キー（keep/compact）が複数 canonical に衝突する場合、そのキーは自動適用しない。
  - 自動適用は一意に解決できるキーのみ。

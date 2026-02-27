# spec_data — データ仕様（取得/正規化/保存）

## 取得元（MVP）
- 観光庁ページから「推移表（Excel）」をダウンロードする
- シート：
  - 1-2：月別 延べ宿泊者数（総数）
  - 2-2：月別 日本人延べ宿泊者数
  - 3-2：月別 外国人延べ宿泊者数

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
- source sheet: `4-2`（都道府県別、宿泊施設タイプ別 客室稼働率 推移表（月別））
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
    `performers`, `capacity`, `source_type`, `source_url`, `source_event_key`,
    `data_hash`, `first_seen_at_utc`, `updated_at_utc`
- `event_uid` 規約: `{venue_id}:{source_event_key}` or `{venue_id}:h:{sha256[:16]}`
- `capacity`: イベント固有があればそれ、なければ会場キャパを COALESCE で利用
- 会場定義: `data/venue_registry.csv`（1行=1会場、追加は1行追加のみ）

## 追補（2026-02-23）イベント速報（ニュースシグナル）
- SSOT: `data/event_signals.sqlite`（`events.sqlite` とは分離）
- 保存方針:
  - 本文は保存しない（ニュース全文のDB保存禁止）
  - 保存対象は `掲載日時 / タイトル / URL / 短い抜粋（一覧で取得できる場合のみ）`

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
- 会場辞書:
  - 正本: `data/venue_registry.csv`（`venue_id` 固定）
  - 別名辞書: `data/venue_aliases.csv`
  - 解決優先順: `venue_registry` の正式名 + `venue_aliases` の別名（`venue_id` 単位で後勝ち）
- 一意性ルール:
  - 正規化キー（keep/compact）が複数 canonical に衝突する場合、そのキーは自動適用しない。
  - 自動適用は一意に解決できるキーのみ。

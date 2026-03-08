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
    `performers`, `artist_name_resolved`, `artist_confidence`, `capacity`,
    `source_type`, `source_url`, `source_event_key`, `data_hash`,
    `first_seen_at_utc`, `updated_at_utc`
- `event_uid` 規約: `{venue_id}:{source_event_key}` or `{venue_id}:h:{sha256[:16]}`
- `capacity`: イベント固有があればそれ、なければ会場キャパを COALESCE で利用
- 会場定義: `data/venue_registry.csv`（1行=1会場、追加は1行追加のみ）
- `artist_name_resolved`: BCL/表示向けの解決済みアーティスト名（`performers` は取得元生値を保持）
- `artist_confidence`: `source` / `source_normalized` / `high` / `medium` / `low`

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
  - `ticketjam_events` の会場ページ対応は `data/ticketjam_venue_pages.csv` で管理する
    - 1行=1 Ticketjam 会場ページと内部 `venue_id` の対応
    - 初期 scope は 北海道 / 東京都 / 神奈川県 / 千葉県 / 埼玉県 / 愛知県 / 大阪府 / 兵庫県 / 福岡県
    - `is_enabled=1` は日次巡回対象、`is_enabled=0` は辞書保持のみ

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
  - Ticketjam 会場ページ対応: `data/ticketjam_venue_pages.csv`
  - 解決優先順: `venue_registry` の正式名 + `venue_aliases` の別名（`venue_id` 単位で後勝ち）
  - 対象範囲:
    - 基本対象: `capacity >= 10000` の会場は、会場公式ソースの実装有無に関わらず辞書へ保持する。公式取得未対応でも `is_enabled=0` の辞書用途で先行登録してよい。
    - 重点会場: `1000 <= capacity < 10000` の会場は、ユーザー影響が高いものだけを対象にする。判断基準は「会場公式イベントの取得対象である」または「`ticketjam_events` の採用/未解決候補で継続的に出現し、GUI確認や辞書照合KPIに影響する」のいずれか。
    - 原則対象外: `capacity < 1000` または capacity 不明の小規模会場は、明示的な運用要件が出るまで辞書の常設対象にしない。
  - Ticketjam venue-first Phase 1 では、会場辞書へ追加した canonical 会場に対して `ticketjam_venue_pages.csv` の page URL を紐付け、Ticketjam 側 raw 表記は `venue_aliases.csv` で吸収する。
- 一意性ルール:
  - 正規化キー（keep/compact）が複数 canonical に衝突する場合、そのキーは自動適用しない。
  - 自動適用は一意に解決できるキーのみ。

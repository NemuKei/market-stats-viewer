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

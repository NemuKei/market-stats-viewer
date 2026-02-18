# spec_airport_volume_data

## 目的
- 空港別の入国者数（人数）を、月次で可視化するためのMVPデータ仕様。
- 将来の ICD `entry_port` 連携を見据え、`airport_code` を join キーとして保持する。

## データソース（一次情報）
- 出典: e-Stat（政府統計の総合窓口）
  - 統計名: 出入国管理統計 / 出入（帰）国者数
  - データセット一覧 URL:
    - `https://www.e-stat.go.jp/stat-search/files?cycle=1&cycle_facet=tclass1%3Acycle&layout=dataset&page=1&result_back=1&tclass1=000001012481&tclass2val=0&toukei=00250011&tstat=000001012480`
  - 対象テーブル:
    - `総括 YY-MM-01 港別 出入国者`
  - 取得ファイル:
    - 記事内リンク `EXCEL 閲覧用`（`file-download?statInfId=...&fileKind=4`）

## 採用理由
- 公的統計であり、月次更新が継続される。
- 港別に `外国人入国者数` を直接取得できる。
- 認証不要の直接ダウンロード（Excel）で運用可能。

## 粒度
- `period_key`: 月次（`YYYY-MM`）
- `airport_name_raw`: ソース表記（港名）
- 指標: `外国人入国者数`（人数）

## MVPフィルタ方針
- ソースは「港別」のため、海港・軍民共用等が混在する。
- MVPでは主要空港のみを採用し、固定マッピングで抽出する。
- 採用空港（コード）:
  - `NRT`, `HND`, `KIX`, `NGO`, `FUK`, `CTS`, `OKA`, `SDJ`, `KIJ`, `KOJ`, `HIJ`, `KMJ`, `NGS`

## テーブル仕様
- DB: `data/market_stats.sqlite`
- table: `airport_arrivals_monthly`
- columns:
  - `period_key` TEXT (`YYYY-MM`)
  - `airport_name_raw` TEXT
  - `airport_name` TEXT（正規化表示名）
  - `airport_code` TEXT（join用キー）
  - `arrivals` INTEGER（入国者数）
  - `unit` TEXT（`persons`）
  - `source_name` TEXT
  - `source_url` TEXT（取得したExcel URL）
  - `updated_at_utc` TEXT

## 正規化方針（join土台）
- `airport_name_raw` はソース値を保持する。
- `airport_name` は表示用正規化名を保持する。
- `airport_code` は将来の ICD `entry_port` 対応付けのキーとして利用する。
- 例:
  - `成田（空港）` -> `airport_name=成田国際空港`, `airport_code=NRT`
  - `羽田（空港）` -> `airport_name=東京国際空港（羽田）`, `airport_code=HND`
  - `関西（空港）` -> `airport_name=関西国際空港`, `airport_code=KIX`

## メタ情報
- file: `data/meta_airport_volume.json`
- fields:
  - `source_name`
  - `source_list_url`
  - `source_signature`
  - `source_excel_url`
  - `source_sha256`
  - `fetched_at_utc`
  - `period_min`
  - `period_max`
  - `row_count`
  - `airports`
  - `processed_sources`
  - `unit`

## 注意点
- 元統計は港ベースであり、空港以外が含まれる。
- e-Stat 側の HTML 構造やリンク仕様変更時は、取得ロジック修正が必要。

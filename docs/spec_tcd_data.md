# spec_tcd_data - 旅行・観光消費動向調査データ仕様

## 目的
- 旅行・観光消費動向調査（TCD）の「宿泊数(8区分)別 延べ泊数」を全国で可視化するためのデータ仕様を定義する。

## ソース
- 観光庁「旅行・観光消費動向調査」ページの `集計表` Excel。
- 対象:
  - 確報（年次・四半期）
  - 2次速報（四半期）

## 抽出ルール
- Excelの `表題` シート A1 を優先し、`period_type` / `period_key` / `release_type` を判定する。
- `T06` シートで列Aが `宿泊数` の行をセクション開始とする。
- セクション直下8行を泊数ビンとして扱う。
- 取得対象の系列:
  - 列B: `domestic_total`（国内旅行（合計））
  - 列E: `domestic_business`（国内旅行（出張・業務））

## 保存先
- SQLite: `data/market_stats.sqlite`
- table: `tcd_stay_nights`

## カラム
- `period_type` (`annual` / `quarter`)
- `period_key` (`YYYY` or `YYYYQ1`..`YYYYQ4`)
- `period_label`（表示用ラベル）
- `release_type`（`確報` / `2次速報`）
- `segment`（`domestic_total` / `domestic_business`）
- `nights_bin`（`1泊`..`8泊以上`）
- `value`（REAL）
- `source_url`
- `source_title`
- `source_sha256`

## メタ
- `data/meta_tcd.json`
- fields:
  - `source_page_url`
  - `last_checked_at`
  - `processed_files[]`: `{url, sha256, title_a1, fetched_at}`
  - `available_periods`
  - `note`（確報優先ルール）

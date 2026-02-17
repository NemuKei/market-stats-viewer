# spec_ta_data

## 目的
- 旅行業者取扱額（TA）の各社別内訳を SQLite に取り込み、年度総計および取得可能な月次を可視化に供給する。

## 取得元
- 索引ページ:
  - `https://www.mlit.go.jp/kankocho/tokei_hakusyo/ryokogyotoriatsukaigaku.html`
- 索引ページから年度ページを辿り、年度ページ内の「各社別内訳」Excelを取得。

## テーブル

### `ta_company_amounts`
- `fiscal_year`（例: `2024`）
- `period`（`total` または `YYYY-MM`）
- `company`
- `segment`（`overseas` / `foreign` / `domestic` / `total`）
- `amount`（単位: 千円）

## 抽出ルール（MVP）
- Excelの4ブロック（海外旅行 / 外国人旅行 / 国内旅行 / 合計）から、
  当該ファイルの主期間列（例: `2024年度`, `2025年`）の取扱額を抽出する。
- 合計行（`合計`）は除外する。
- 各社行のみを格納する。

## メタ
- `data/meta_ta.json`
- 主な項目:
  - `source_index_url`
  - `last_checked_at`
  - `processed_files`（`excel_url`, `fiscal_year`, `period`, `sha256`, `rows`）
  - `row_count`
  - `fiscal_years`
  - `periods`
  - `segments`
  - `unit`（`thousand_yen`）


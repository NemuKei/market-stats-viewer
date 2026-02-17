# spec_icd_data

## 目的
- インバウンド消費動向調査（ICD）のMVPデータを、既存の `data/market_stats.sqlite` に同居させて提供する。
- 対象は次の2系統。
  - 国籍別: 費目別旅行支出（単価 + 構成比）
  - 入国/出国空港・港別: 平均泊数 + 総旅行支出（回答者数付き）

## 取得元
- ページ: `https://www.mlit.go.jp/kankocho/tokei_hakusyo/gaikokujinshohidoko.html`
- 対象ファイル: ページ内の最新「集計表（Excel）」1件（`.xls` / `.xlsx`）

## 解析対象シート
- 費目別支出:
  - `参考2`（全目的）
  - `参考10`（観光・レジャー目的）
- 入国空港/港:
  - `表4-1`（平均泊数: 全目的）
  - `参考1`（総旅行支出: 全目的）
  - `参考7`（平均泊数: 観光・レジャー目的）※取得可能時
  - `参考9`（総旅行支出: 観光・レジャー目的）※取得可能時

## テーブル

### `icd_spend_items`
- `period_label`
- `period_key`
- `release_type`
- `purpose` (`all` / `leisure`)
- `nationality`
- `item_group`
- `item`
- `spend_yen`
- `share_pct`

### `icd_entry_port_summary`
- `period_label`
- `period_key`
- `release_type`
- `purpose` (`all` / `leisure`)
- `port_type` (`entry` / `exit`)
- `entry_port`（`全体` を含む）
- `nationality`
- `respondents`
- `spend_yen`
- `avg_nights`
- `spend_per_night_yen`（`avg_nights > 0` のときのみ算出）

## メタ
- `data/meta_icd.json`
- 主な項目:
  - `source_page_url`
  - `source_excel_url`
  - `source_excel_filename`
  - `source_excel_sha256`
  - `fetched_at_utc`
  - `period_label`
  - `period_key`
  - `release_type`
  - `sheets_used`
  - `row_counts`

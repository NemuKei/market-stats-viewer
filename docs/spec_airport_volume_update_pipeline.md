# spec_airport_volume_update_pipeline

## エントリ
- ローカル:
  - `python -m scripts.update_airport_volume_data`
- CI:
  - `.github/workflows/update_data.yml` から実行

## 処理順（MVP）
1. e-Stat の対象データセット一覧ページを取得する。
2. 最新の `総括 YY-MM-01 港別 出入国者` 行を特定する。
3. 直近複数月（最大48か月）の対象行を収集する。
4. 各行の `EXCEL 閲覧用` をダウンロードし、`sha256` を計算する。
5. `{period_key, excel_url, sha256}` から `source_signature` を作る。
6. 既存 `data/meta_airport_volume.json` の `source_signature` と比較する。
7. 一致時は no-op で `return 0`（sqlite/meta を更新しない）。
8. 不一致時のみ Excel をパースして主要空港データを整形する。
9. `data/market_stats.sqlite` の `airport_arrivals_monthly` を更新する。
10. `data/meta_airport_volume.json` を更新する。

## 変更検知（無駄コミット防止）
- 比較キー: `source_signature`
- 一致時:
  - DB再生成なし
  - meta更新なし
  - Exit code `0`

## 生成物
- SQLite:
  - `data/market_stats.sqlite`
  - table: `airport_arrivals_monthly`
- Meta:
  - `data/meta_airport_volume.json`

## 失敗時
- 対象行が見つからない、またはパース結果が空のときは例外終了。
- 想定要因:
  - e-Stat HTML 構造変更
  - 対象テーブル名変更
  - 主要空港マッピング未対応

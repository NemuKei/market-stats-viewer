# spec_tcd_update_pipeline - TCD更新パイプライン仕様

## 目的
- 旅行・観光消費動向調査（TCD）データの取得〜更新を自動化する。

## 実行エントリ
- ローカル: `python -m scripts.update_tcd_data`
- CI: `.github/workflows/update_data.yml` から実行

## 処理フロー（MVP）
1. 観光庁のTCDページHTMLを取得する。
2. `集計表` のExcelリンクのみ抽出する（都道府県別参考は除外）。
3. 各ExcelをダウンロードしてSHA256を算出する。
4. `meta_tcd.json` の `processed_files` と比較して差分有無を判定する。
5. 差分なしで既存テーブルが利用可能な場合は no-op で終了する。
6. 差分ありの場合のみ以下を実行する。
7. `表題` シート A1 から期間・リリースを判定する。
8. `T06` の `宿泊数` セクション（直下8行）を抽出する。
9. SQLite `tcd_stay_nights` テーブルを再構築する。
10. `meta_tcd.json` を更新する。

## 可用性・保守
- 既存 `market_stats` テーブルには影響を与えない。
- 解析失敗時は例外で停止し、誤データ上書きを避ける。
- `latest（確報優先）` 判定に必要な情報を `meta_tcd.json.note` に明記する。

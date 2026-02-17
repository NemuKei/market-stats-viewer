# spec_icd_update_pipeline

## エントリ
- ローカル実行:
  - `python -m scripts.update_icd_data`
- CI:
  - `.github/workflows/update_data.yml` から実行

## 処理フロー（MVP）
1. ICDページを取得し、最新の「集計表（Excel）」リンクを1件選択する。
2. Excelをダウンロードし、SHA256を計算する。
3. 対象シート（`参考2/10`, `表4-1`, `参考1` など）を解析する。
   - 空港/港は `入国空港・海港` と `出国空港・海港` の両セクションを抽出する。
4. `icd_spend_items` と `icd_entry_port_summary` を再構築する。
5. `data/meta_icd.json` を更新する。

## 失敗時
- 対象リンク/シートが見つからない場合は例外終了。
- 次回更新で復旧可能なよう、取得元URLとシート情報を `meta_icd.json` に残す。

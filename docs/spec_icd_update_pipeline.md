# spec_icd_update_pipeline

## エントリ
- ローカル実行:
  - `python -m scripts.update_icd_data`
- CI:
  - `.github/workflows/update_data.yml` から実行

## 処理フロー（MVP）
1. ICDページを取得し、最新の「集計表（Excel）」リンクを1件選択する。
   - `都道府県` を含むリンクは対象外とする。
   - `.xls` と `.xlsx` の両方を対象にする。
2. Excelをダウンロードし、SHA256を計算する。
3. workbook内の上部セルから期間 metadata を検出する。
   - 四半期表記は `YYYY年M-M月期` を `period_label=YYYY年M-M月期`、`period_key=YYYYQn` として保存する。
   - 年間表記は `YYYY年年間` または `YYYY年（令和N年） 暦年` を `period_label=YYYY年年間`、`period_key=YYYY` として保存する。
   - `【確報】` や `【1次速報】` などの括弧内表記は `release_type` として保存する。
4. 対象シート（`参考2/10`, `表4-1`, `参考1` など）を解析する。
   - 空港/港は `入国空港・海港` と `出国空港・海港` の両セクションを抽出する。
5. `icd_spend_items` と `icd_entry_port_summary` を再構築する。
6. `data/meta_icd.json` を更新する。

## 失敗時
- 対象リンク/シートが見つからない場合は例外終了。
- 次回更新で復旧可能なよう、取得元URLとシート情報を `meta_icd.json` に残す。
- 期間 metadata を検出できない場合は例外終了。四半期表記と年間表記のどちらにも該当しない新しい表題形式が出た場合は、表題形式を確認して parser とこの仕様を同時に更新する。

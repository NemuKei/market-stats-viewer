# spec_ta_update_pipeline

## エントリ
- ローカル実行:
  - `python -m scripts.update_ta_data`
- CI:
  - `.github/workflows/update_data.yml` から実行

## 処理フロー（MVP）
1. TA索引ページから年度ページリンクを収集する。
2. 各年度ページで「各社別内訳」Excelリンクを収集する。
3. 各Excelを解析し、`fiscal_year` / `period` / `company` / `segment` / `amount` を抽出する。
4. `ta_company_amounts` を再構築する。
5. `data/meta_ta.json` を更新する。

## 期間の扱い
- 年度総計は `period=total`。
- 月次は `YYYY-MM` に正規化。

## 失敗時
- 単一ファイルの解析失敗はスキップして継続し、最終的に1件も抽出できない場合のみ例外終了。


# docs/spec_update_pipeline.md（全文置換）

# spec_update_pipeline — 更新パイプライン仕様

## 目的
推移表Excelの更新を検知し、正規化したデータ（sqlite + meta）を生成・更新する。

## 実行箇所（MVP）
- GitHub Actions（schedule + workflow_dispatch）
- ローカル手動実行（開発時）

## 処理フロー（MVP）
1. 取得元ページのHTMLを取得
2. 推移表ExcelのURLを抽出
3. Excelをダウンロード
4. sha256 を計算し、前回値と比較（差分が無ければ終了）
5. Excelを読み込み、想定3シート（`1-2/2-2/3-2`）をパースしてRAW化
   - 読み込みは openpyxl の `load_workbook(..., read_only=False, data_only=True)` を採用する
   - `read_only=False` は、セル参照型のパースで性能劣化が出るケースを避ける目的
6. 全国（00）は 01〜47 合算で生成
7. SQLite（market_stats）を再構築（MVPは replace で良い）
8. meta.json を更新
9. GitHub Actionsで更新があれば commit/push

## 冪等性
- 同じExcel（hash同一）なら出力を更新しない（commitしない）

## 失敗時
- HTML構造変更でURL抽出に失敗した場合：
  - Actionsは失敗（赤）
  - 次対応として scripts側にフォールバック（手動URL指定）を追加する余地はある（P1）

## 追記: 2系統データ更新（2026-02-11）
- workflow `update_data.yml` は以下を順次実行する。
  - `python -m scripts.update_data`
  - `python -m scripts.update_tcd_data`
- 差分がある場合は `data/` を含めて commit/push する。

## 追記: TCD更新パイプライン（MVP）
1. 観光庁「旅行・観光消費動向調査」ページから `集計表` Excelリンクのみ収集する。
2. 確報（年次・四半期）および2次速報（四半期）を対象にする。
3. Excelの `表題` シート A1 を優先し、`period_type` / `period_key` / `release_type` を判定する。
4. `T06` シートで `宿泊数` 行を起点に8行（1泊..8泊以上）を抽出する。
5. `data/market_stats.sqlite` の `tcd_stay_nights` テーブルを再構築する。
6. `data/meta_tcd.json` に `processed_files(url, sha256, title_a1, fetched_at)` を保存する。
7. 取得元hashに差分がない場合は no-op とする。

## 追記: 自動更新スケジュール（2026-02-13）
- GitHub Actions `update_data.yml` の定期実行は `cron: 0 3 * * 1`。
- 実行時刻は毎週月曜 03:00 UTC（日本時間 月曜 12:00）。
- 手動実行は `workflow_dispatch` を使う。

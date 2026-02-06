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
5. 3シートをパースしてRAW化
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

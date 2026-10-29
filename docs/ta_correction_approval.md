# TA訂正値の承認と適用

現在、TA週次更新はIssue #34の承認待ちで一時スキップしている。空港など他の更新は継続する。この文書やプレビューmanifestはユーザー承認の代わりにならない。

## 重複解決

- `(fiscal_year, period, company, segment)` が同じで金額も同じなら統合する。入力行順は採用値に影響しない。
- 金額が違う場合は原則エラーで停止し、DB/metaを書き換えない。
- `--duplicate-selection his-2026-03-main-table` を明示した場合だけ、2026-03のHIS合計の本表採用案を使える。
- 例外は年度2025、月2026-03、正規化済み会社名 `エイチ・アイ・エス（6社計 ＊4）`、区分totalに限定する。全重複行の資料URLが `https://www.mlit.go.jp/kankocho/content/002002289.xlsx`、SHA-256が `c01db7269370a8cd593e3d3bdb5f97d7aee11fb52a4df9c0be1cff0391595b67`、候補値の集合が38,188,442と38,188,444千円であることも必要。
- 本表38,188,442は両表の内訳合計と一致するための提案であり、公式の優先指定を確認したものではない。選択は既定で無効。環境変数や以前のmetaから自動では有効にしない。

## 承認用パッケージ

Sharedの `market-stats-viewer-review-20261029` にある `ta_changes_v3_proposed.csv`、`ta_application_plan_v3_proposed.json`、`ta_candidate_rows_v3_proposed.json` が提案の正本。v1/v2一覧も残す。提案は金額変更2,996・追加4,414・集計行除外266・不変3,958・保留0、反映後の見込み11,368件。

HIS本表採用、一覧の全件、集計266件の除外と、実行する適用・公開・再開の範囲をユーザーが承認するまで実行しない。承認を一覧・manifestのハッシュとともに記録する。

## 初回適用（承認後だけ）

1. リモートとローカルの変更を確認し、他の担当作業を保持する。TA停止を維持したまま、入力DB/metaが承認時のSHAと一致することを確認する。不一致なら新しい一覧を作って再承認し、旧manifestを更新して承認を流用しない。
2. DB/metaの復旧用コピーをリポジトリ外へ対で保存する。SQLiteのsidecarや更新中writerがあれば停止して調べる。
3. 次の**TA単独コマンド**を、承認済みmanifestの絶対パスを指定して実行する。今は実行不可。

```sh
uv run python -m scripts.update_ta_data \
  --duplicate-selection his-2026-03-main-table \
  --approved-preview /absolute/path/to/ta_application_plan_v3_proposed.json
```

このコマンドは現在の公式ページの資料を全件再取得する。`--approved-preview` はDB/metaのSHA、全資料のURL集合・SHA、全解決済み行のSHA、DBからの全変更行のSHA、extractor version、選択方針を照合する。保存直前にも照合する。どれかが変わっていれば保存前に停止する。manifestの指定時は署名一致のno-opも使わず照合する。

4. 終了コード0だけで公開しない。保存後のTA全行をread-onlyで読み、`resolve_ta_records`で正規化した全行SHAがmanifestの`resolved_rows_sha256`と一致することを確認する。復旧用コピーのTA行からの全変更SHAも`changes_sha256`に一致させる。件数11,368、HIS=38,188,442、集計行なし、metaのversion/選択方針/65資料ハッシュ、他統計テーブルの値の保持も確認する。
5. 差異・取得失敗・不明金額・異値重複・保存失敗・検証失敗ではcommit/pushや停止解除をしない。入力が変わった場合は新規プレビューと再承認へ戻す。保存中の例外は既存のStatsUpdateがDB/meta対をロールバックする。復旧できなければjournalとバックアップを保持して復旧を確認する。検証失敗を理由に例外を増やしたり、manifestのSHAを合わせて続行したりしない。
6. 承認済みの公開範囲で、対象DB/metaだけをcommit・pushする。他の作業ファイルを一緒に含めない。

## 週次の再開（別途その実行範囲が承認された後）

適用・公開後の値の確認が済んでから、`update_data.yml`のTAスキップログを次の呼出しへ戻す。空港・他workflowは変更しない。

```sh
uv run python -m scripts.update_ta_data --duplicate-selection his-2026-03-main-table
```

初回適用のmanifestを週次へ固定しない。週次は通常の新資料更新を続けるが、HISの例外は上記のキー・SHA・候補値にだけ有効。対象資料が変わり異値重複が残る場合や他の異値重複が発生した場合は停止する。週次の明示選択を外せば例外は無効になる。

workflow差分とシェル構文を検証し、承認された範囲でcommit・pushしてリモート本文を読む。Actionsの手動実行・再実行は別途許可がない限り行わず、次の定期実行を確認する。

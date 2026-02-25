# STATUS（market-stats-viewer）

最終更新: 2026-02-25

## Done（直近完了）
- 常設コンテキストの正本パスを `docs/context/STATUS.md` / `docs/context/DECISIONS.md` に統一
- `docs/DECISIONS.md` は互換リダイレクト化し、既存参照を壊さない構成にした
- 会場公式イベントのアーティスト補完を `title + description` 参照へ拡張し、補完辞書を `seed + jp.seed + manual` 統合利用へ変更
- `update_events_data` 実行後に `events_artist_inferred.csv` 自動再生成を追加
- 会場公式イベントの種別を `コンサート / 野球 / その他` へ分離し、アーティスト名の辞書正規化をカテゴリ判定とキーワード検索に反映
- アーティスト辞書seedの月次Wikidata更新workflowを追加し、差分なし行の `updated_at` 保持で不要コミットを抑制
- GitHub Actions の会場公式イベント更新を `update_events_official.yml` として分離し、`update_data.yml` はcore統計更新専用に整理

## Doing
- なし（変更発生時に更新）

## Next（最大3）
1. 仕様変更時は `DECISIONS -> spec -> 実装` の順で同期する
2. UI/データ更新タスクが発生したら本ファイルを最新スナップショットへ更新する

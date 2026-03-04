# STATUS（market-stats-viewer）

最終更新: 2026-03-04

## Done（直近完了）
- `events.sqlite` に `artist_name_resolved` / `artist_confidence` を追加し、`build_events_artist_inferred` 実行時に source値 + 辞書正規化 + 推論結果を同期するよう更新（BCL側が sqlite 単体で利用可能）
- event_signals更新時に artist/venue 辞書正規化を保存時適用し、`labels_json` へ `raw_artist_name` / `raw_venue_name` を保持するよう更新
- 会場別名辞書 `data/venue_aliases.csv` を追加し、`venue_registry` 正本 + alias吸収の運用に整理
- 運用ルールを仕様へ反映（新規候補反映、会場名称変更時の手順、Wikidata定期更新はアーティストのみ継続）
- 外部連携向けに Release assets 公開workflow（`publish_external_events_assets.yml`）を追加し、`external-events-latest` へ `events.sqlite` / `event_signals.sqlite` / `manifest.json` を自動公開する運用を追加
- `scripts.build_external_events_manifest` を追加し、assetの `sha256` / `size_bytes` / 生成時刻を `data/manifest.json` へ出力する導線を追加
- 常設コンテキストの正本パスを `docs/context/STATUS.md` / `docs/context/DECISIONS.md` に統一
- `docs/DECISIONS.md` は互換リダイレクト化し、既存参照を壊さない構成にした
- 会場公式イベントのアーティスト補完を `title + description` 参照へ拡張し、補完辞書を `seed + jp.seed + manual` 統合利用へ変更
- `update_events_data` 実行後に `events_artist_inferred.csv` 自動再生成を追加
- 会場公式イベントの種別を `コンサート / 野球 / その他` へ分離し、アーティスト名の辞書正規化をカテゴリ判定とキーワード検索に反映
- アーティスト辞書seedの月次Wikidata更新workflowを追加し、差分なし行の `updated_at` 保持で不要コミットを抑制
- GitHub Actions の会場公式イベント更新を `update_events_official.yml` として分離し、`update_data.yml` はcore統計更新専用に整理
- 会場公式コンサート抽出のQA修正として、曖昧alias誤補完の除外・未確定performers判定・非音楽キーワード優先分類を追加
- 二次流通由来の参考ソース `ticketjam_events` を event_signals に追加し、必須4項目（イベント日・会場・アーティスト・イベント名）を満たすレコードのみ保存するよう更新
- UIに `全国イベント参考（二次流通）` を追加し、ニュースビューとは別枠で表示するよう更新
- `ticketjam_events` を「未来開催」かつ「`Event` / `MusicEvent` + `categorie_groups` が `live_domestic/live_international`（コンサート系）」へ変更し、増分巡回の既定上限を `max_sitemaps=120` / `max_event_urls=400` に引き上げ
- `ticketjam_events` に音楽系 `categories` slug 限定・非ライブ系キーワード除外・曖昧カテゴリ（`male/female-artist`）へのライブ語必須を追加し、`prune_nonconforming=true` で既存ノイズを自動削除するよう更新
- `ticketjam_events` は `prune_missing=false` とし、差分巡回で未取得行を消さない代わりに、開催終了済みデータを更新時に自動削除するよう更新
- event_signals 更新workflowを分離し、ニュース（STARTO/Kstyle）と Ticketjam（二次流通）を別ジョブで実行する運用へ変更
- `publish_external_events_assets.yml` の `workflow_run` トリガーをニュース/ Ticketjam 両workflowに対応させた

## Doing
- なし（変更発生時に更新）

## Next（最大3）
1. 仕様変更時は `DECISIONS -> spec -> 実装` の順で同期する
2. Release assets の定期公開結果（workflow_run）を監視し、失敗時の再実行手順を運用に反映する
3. UI/データ更新タスクが発生したら本ファイルを最新スナップショットへ更新する

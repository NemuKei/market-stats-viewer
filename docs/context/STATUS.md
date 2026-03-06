# STATUS（market-stats-viewer）

最終更新: 2026-03-06

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
- `ticketjam_events` の初回取り込みを `--ticketjam-bootstrap-full` で強制実行できるようにし、既定 `bootstrap_max_sitemaps=8000` / `bootstrap_max_event_urls=50000` の網羅取得モードを追加
- `ticketjam_events` は通常運用で `upsert_existing=false`（新規中心）を既定化し、日次は増分のみ取り込む運用へ更新
- `ticketjam_events` の重複表示対策として、`event_id` 重複に加え、同一公演キー（イベント日+開始時間+会場+アーティスト+タイトル）重複を更新時に集約するよう更新
- event_signals 更新workflowを分離し、ニュース（STARTO/Kstyle）と Ticketjam（二次流通）を別ジョブで実行する運用へ変更
- `publish_external_events_assets.yml` の `workflow_run` トリガーをニュース/ Ticketjam 両workflowに対応させた

## Doing
- T-20260306-006: `update_event_signals_data --only ticketjam_events --rebuild` 実行待ち

## Next（最大3）
1. 仕様変更時は `DECISIONS -> spec -> 実装` の順で同期する
2. Release assets の定期公開結果（workflow_run）を監視し、失敗時の再実行手順を運用に反映する
3. UI/データ更新タスクが発生したら本ファイルを最新スナップショットへ更新する

## Task Backlog（Venue Dictionary Completeness）
- [ ] T-20260306-001: 会場辞書の対象範囲を定義する（運用対象: 1万人以上会場 + 重点会場）
- [x] T-20260306-002: `ticketjam_events` 未解決会場候補を頻度順で抽出し、ノイズ語（会場でない文字列）を分離する
- [x] T-20260306-003: 既存 `venue_registry` への alias 追加を実施する（高頻度上位から）
- [x] T-20260306-004: 未登録の1万人以上会場を `venue_registry` へ追加する（`is_enabled=0` で辞書用途先行）
- [x] T-20260306-005: 辞書反映後のマッチ率を計測し、KPIを記録する（全体マッチ率 / 1万人以上マッチ率）
- [ ] T-20260306-006: `update_event_signals_data --only ticketjam_events --rebuild` を実施し、既存データへ辞書を再適用する
- [ ] T-20260306-007: UIの二次流通ビューでサンプル会場（京セラ/東京ドーム/ヤンマー等）の抽出結果を目視検証する
- [ ] T-20260306-008: 会場一致のみ採用フラグ（実験モード）を導入し、フィルタON/OFF比較を可能にする
- [ ] T-20260306-009: 会場一致かつ `capacity >= 10000` の採用ルールを本番既定に切り替える

KPI（2026-03-06, `ticketjam_events` 現在DBに対する辞書照合）:
- 全体会場マッチ率（registry or alias）: 15.58% -> 32.67%（+17.09pt）
- 1万人以上会場マッチ率（全体比）: 5.42% -> 5.42%（横ばい）

## Remaining Task Triage (ASCII)
Now:
- T-20260306-006

Next:
- T-20260306-007, T-20260306-001

After Next:
- T-20260306-008, T-20260306-009

Later:
- なし（必要時に追加）

統合メモ:
- T-20260306-002〜005 を1エピック「辞書整備バッチ（抽出→反映→計測）」として運用する
- T-20260306-008〜009 を1エピック「会場ベース採用ルール切替」として段階導入する

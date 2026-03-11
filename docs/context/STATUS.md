# STATUS（market-stats-viewer）

最終更新: 2026-03-11

## Done（直近完了）
- Release assets 公開workflowの定期監視を実施した。2026-03-11 時点の直近10 run は `success 9 / skipped 1 / failure 0` で、最新成功 run は `22931909506`。Release `external-events-latest` の asset `events.sqlite / event_signals.sqlite / manifest.json` は `2026-03-11T01:15:01Z` 更新を確認し、即時の手動再公開は不要と判断した
- `大阪府立体育会館（エディオンアリーナ大阪）` の会場公式 source を追加した。`edion_arena_osaka_pdf_schedule` で公式トップページ上の `monthlyYYMM.pdf` を取得し、第1競技場のみを `events.sqlite` へ反映するよう更新した。ローカル実行では `15件 fetched`（大相撲三月場所 `15日程`）を確認し、会場マスタも `is_enabled=1`・`ticketjam_watch=0`・`official_fetch_candidate=0` へ切り替えた
- `Panasonic Stadium Suita` の会場公式 source を追加した。`panasonic_stadium_suita_schedule` で公式 `https://suitacityfootballstadium.jp/schedule/index/year/YYYY/month/MM/` の月次HTML表を取得し、会場マスタも `is_enabled=1`・`ticketjam_watch=0`・`official_fetch_candidate=0` へ切り替えた。ローカル実行では `9件 fetched` を確認
- `events.sqlite` 更新時の no-op 経路を見直し、`data_hash` が同じでも `artist_name_resolved` / `artist_confidence` / `event_category` の導出値が変わった場合は再同期するよう更新した
- `official_fetch_candidate=1` の大阪会場を棚卸しし、`Panasonic Stadium Suita` と `大阪府立体育会館（エディオンアリーナ大阪）` は会場公式ソース追加優先、`ヤンマースタジアム長居` は公式サイト障害が解消するまで Ticketjam 補完継続と判断した。`Panasonic` は月次HTML表、`エディオン` は月次PDF導線、`ヤンマー` は 2026-03-11 時点で WordPress fatal error を確認
- `ticketjam_watch` / `ticketjam_benchmark_tier` / `official_fetch_candidate` を使った補完評価レポート自動集計を追加した。`python -m scripts.build_ticketjam_supplement_report` で `data/ticketjam_supplement_report.json` / `.md` を生成し、Ticketjam workflow 後段でも自動更新するようにした。baseline は `events.sqlite + starto_concert + kstyle_music`、比較キーは `event_date + canonical venue_name + canonical artist_name`
- Ticketjam 大阪スパイクの評価を実施し、`hybrid` を既定 discovery のまま維持する判断を確定した。GitHub Actions run `22835162881`（`prefecture_month`, bootstrap full）は `91件`・全件大阪・`artist-gap` ベンチマークヒット `0件`、run `22836011961`（`hybrid`, bootstrap full）は `2561件`・大阪 `380件`・`artist-gap` ベンチマークヒット `福山雅治 9 / 三代目 J SOUL BROTHERS from EXILE TRIBE 2` だった。`prefecture_month` は比較・軽量調査用 mode として残し、本線運用には使わない
- Ticketjam 大阪スパイクの discovery として、`prefecture_month` / `prefecture_month_hybrid` mode を追加した。`https://ticketjam.jp/prefectures/osaka/month?events_page=n` の `p-event-list` と直後の JSON-LD から event URL / 日付 / 会場 / 都道府県を候補抽出し、CLI から `--ticketjam-discovery-mode` で切替できるよう更新した
- Ticketjam 補完スパイク向けに、アーティスト辞書へ `ticketjam_watch` / `ticketjam_benchmark_tier` / `ticketjam_watch_reason`、会場辞書へ `ticketjam_watch` / `official_fetch_candidate` / `official_gap_reason` を追加した。大阪の初期 `artist-gap` ベンチマーク（S/A/B/reference）と `venue-gap` 候補（ヤンマースタジアム長居 / Panasonic Stadium Suita / エディオンアリーナ大阪）も登録した
- Ticketjam の目的を再定義し、「会場網羅の代替」ではなく `artist-gap` / `venue-gap` を埋める補完ソースとして扱う方針を spec / DECISIONS へ固定した。大阪府を初期スパイク対象にし、追加ユニーク日程とノイズ率で価値判定する
- `ticketjam_events` の取得を pure venue-page から hybrid（会場ページ + 公開 sitemap 補完）へ見直した。会場ページは `date/time/venue` の page-specific 情報源として優先し、会場ページだけでは出てこない event URL は sitemap で補完するよう更新
- Ticketjam の stale JSON-LD により `event_end_date < event_start_date` となるケースを修正した。event page 見出しと会場ページ文脈を優先し、`ticketjam_events` は 1日程=1データとして `event_start_date == event_end_date` で保存するよう更新
- 二次流通ビューの防御線として、既存DBに逆転した期間が残っていても UI 上は `event_end_date >= event_start_date` へ補正して表示するよう更新
- Ticketjam を venue page 起点へ切り替え、`data/ticketjam_venue_pages.csv` を追加した。Phase 1 は 北海道 / 東京都 / 神奈川県 / 千葉県 / 埼玉県 / 愛知県 / 大阪府 / 兵庫県 / 福岡県 の `75会場`（`is_enabled=1` は `68会場`）で、`イベント一覧` から event URL を収集し、`駐車場券` などの付随商品を除外するよう更新
- Phase 1 会場マスタを `venue_registry` / `venue_aliases` へ取り込み、会場辞書を `69 -> 104会場` に拡張した。既存会場は `venue_id` を維持し、Ticketjam 側の別表記は alias へ吸収する運用に整理した
- 会場辞書の対象範囲を定義し、`capacity >= 10000` は常設対象、`1000 <= capacity < 10000` は重点会場のみ、`capacity < 1000` / 不明は原則対象外とする運用を `DECISIONS` / spec へ反映
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
- `ticketjam_events` の採用ゲートを「会場辞書一致 + `capacity>=1000`」へ切替し、取得時カテゴリ縛りを外したうえで `event_category`（コンサート/野球/その他）を付与するよう更新
- 二次流通ビューに会場公式寄せの種別フィルタ（すべて/コンサート/野球/その他）を追加
- `ticketjam_events` の `--ticketjam-bootstrap-full` 検証を GitHub Actions で `bootstrap_max_sitemaps=1200` / `bootstrap_max_event_urls=12000` にて完走し、現行ゲート適用後の確定値を記録した（`3242 fetched -> 319 kept`, `event_category=コンサート 304 / その他 15`）

## Doing
- （なし）

## Next（最大3）
1. `ヤンマースタジアム長居` の公式サイト障害が解消したら公式 source を再評価する
2. Release assets の定期公開結果を継続監視する
3. （なし）

## Task Backlog（Venue Dictionary Completeness）
- [x] T-20260306-001: 会場辞書の対象範囲を定義する（運用対象: 1万人以上会場 + 重点会場）
- [x] T-20260306-002: `ticketjam_events` 未解決会場候補を頻度順で抽出し、ノイズ語（会場でない文字列）を分離する
- [x] T-20260306-003: 既存 `venue_registry` への alias 追加を実施する（高頻度上位から）
- [x] T-20260306-004: 未登録の1万人以上会場を `venue_registry` へ追加する（`is_enabled=0` で辞書用途先行）
- [x] T-20260306-005: 辞書反映後のマッチ率を計測し、KPIを記録する（全体マッチ率 / 1万人以上マッチ率）
- [x] T-20260306-006: `update_event_signals_data --only ticketjam_events --rebuild` を実施し、既存データへ辞書を再適用する
- [x] T-20260306-007: UIの二次流通ビューでサンプル会場（京セラ/東京ドーム/ヤンマー等）の抽出結果を目視検証する（方針変更により後続タスクへ統合）
- [x] T-20260306-008: 会場一致のみ採用フラグ（実験モード）を導入し、フィルタON/OFF比較を可能にする（方針変更により T-20260306-011/012 へ置換）
- [x] T-20260306-009: 会場一致かつ `capacity >= 10000` の採用ルールを本番既定に切り替える（方針変更により `capacity >= 1000` へ置換）

## Task Backlog（Ticketjam Venue-First + Category Alignment）
- [x] T-20260306-010: 取得方針を仕様化する（カテゴリ絞り解除 + 会場辞書一致 + `capacity >= 1000` + 種別3区分）
- [x] T-20260306-011: `ticketjam_events` の取得時フィルタを「会場辞書基準」へ変更する（カテゴリslug必須を外す）
- [x] T-20260306-012: 会場辞書一致かつ `capacity >= 1000` の採用ゲートを実装する
- [x] T-20260306-013: Ticketjamデータの `event_category` を `コンサート / 野球 / その他` に分岐する（Ticketjamカテゴリ優先、不足時は既存ルールで補完）
- [x] T-20260306-014: 二次流通ビューのGUIを会場公式ビュー寄りに揃える（種別フィルタ、列順、操作導線）
- [x] T-20260306-015: `--ticketjam-bootstrap-full` 実行で再構築し、会場別件数と種別件数を検証する（2026-03-06: GitHub Actions run `22758325580`, `1200/12000` で完走確認）
- [x] T-20260306-016: `DECISIONS` / `spec_update_pipeline` / `spec_app` を新方針へ同期する

## Task Backlog（Ticketjam Venue-First Phase 1）
- [x] T-20260308-001: Phase 1 会場マスタを取り込み、`venue_registry` / `venue_aliases` を 9都道府県・`capacity >= 1000` 方針へ拡張する
- [x] T-20260308-002: `data/ticketjam_venue_pages.csv` を追加し、Ticketjam 会場ページ URL と内部 `venue_id` の対応を正本化する
- [x] T-20260308-003: `ticketjam_events` の event URL 収集を venue page 起点へ切り替え、`イベント一覧` のみ巡回する
- [x] T-20260308-004: venue page 起点でも既存運用を壊さないよう、legacy sitemap config を runtime 互換として残しつつ `DECISIONS` / spec / STATUS を同期する
- [x] T-20260308-005: Ticketjam の stale JSON-LD に引きずられる日付逆転を修正し、page-specific 日付/時刻/会場を優先する
- [x] T-20260308-006: pure venue-page だけでは主要会場の網羅性が足りないため、公開 sitemap を補完導線として再導入する
- [x] T-20260308-007: `ticketjam_events` を 1日程=1データへ変更し、複数日開催も日別レコードで保持する

## Task Backlog（Ticketjam Supplement Spike: Osaka）
- [x] T-20260309-001: Ticketjam の役割を `artist-gap` / `venue-gap` 補完ソースへ再定義し、成功指標を spec / DECISIONS / STATUS へ固定する
- [x] T-20260309-002: アーティスト辞書へ `ticketjam_watch` / `ticketjam_benchmark_tier` / `ticketjam_watch_reason` を追加する
- [x] T-20260309-003: 会場辞書へ `ticketjam_watch` / `official_fetch_candidate` / `official_gap_reason` を追加する
- [x] T-20260309-004: 大阪府の初期 `artist-gap` ベンチマーク対象を登録する（S/A/B と reference を分離）
- [x] T-20260309-005: 大阪府の初期 `venue-gap` 会場を登録する（例: 公式が弱い・無い・取りづらい会場）
- [x] T-20260309-006: Ticketjam 大阪スパイクの discovery 実装を追加する（都道府県 month ページ優先、既存導線と比較可能にする）
- [x] T-20260309-007: 大阪スパイクの評価を実施し、`artist-gap additional hits` / `venue-gap additional hits` / `noise rate` を記録して Go/No-Go を判断する

## Task Backlog（Ticketjam Supplement Operations）
- [x] T-20260311-001: `ticketjam_watch` / `ticketjam_benchmark_tier` / `official_fetch_candidate` を使った評価レポート自動集計を追加する
- [x] T-20260311-002: `official_fetch_candidate=1` の大阪会場について、Ticketjam 補完継続か会場公式ソース追加優先かを棚卸しする
- [x] T-20260311-003: `Panasonic Stadium Suita` の会場公式 source を追加する（月次HTML表）
- [x] T-20260311-004: `大阪府立体育会館（エディオンアリーナ大阪）` の会場公式 source を追加する（月次PDF行事案内）

KPI（2026-03-06, `ticketjam_events` 現在DBに対する辞書照合）:
- 全体会場マッチ率（registry or alias）: 15.58% -> 32.67%（+17.09pt）
- 1万人以上会場マッチ率（全体比）: 5.42% -> 5.42%（横ばい）
- 補足: `--rebuild` 実行時の取得上限（`max_sitemaps=120`, `max_event_urls=400`）では 69件再構築だったため、全量再適用が必要な場合は `--ticketjam-bootstrap-full` を使う

2026-03-06 実測メモ:
- ローカル縮小 bootstrap（`300/5000`）: `49件`、`event_category=コンサート 46 / その他 3`、会場上位は `豊洲PIT 6` / `GORILLA HALL OSAKA 4` / `サントリーホール 4` / `東京芸術劇場 コンサートホール 4`
- `origin/main` 現在DB（2026-03-06 04:58 UTC の日次増分後）: `198件`、`event_category=(null) 178 / コンサート 19 / その他 1`。増分更新だけでは旧データが多く残るため、現行ルールの確定値には bootstrap full 再構築が必要
- GitHub Actions 手動実行: `Update event signals data (Ticketjam)` run `22758325580` は 2026-03-06 09:55 UTC 開始、2026-03-06 11:17 UTC に success で完了。`sitemap attempts=1210 successes=1200 urls=3691`、`3242 fetched`、ゲート後 `319 kept`（`unknown venue 2855 / low capacity 68`）
- bootstrap full 完走後の `origin/main` 現在DB: `319件`、`event_category=コンサート 304 / その他 15`、会場上位は `TOKYO DOME CITY HALL 24` / `豊洲PIT 19` / `オリックス劇場 18` / `Zepp DiverCity(Tokyo) 16` / `Kアリーナ横浜 14`

2026-03-08 実装メモ:
- Phase 1 会場 CSV 取り込み後の辞書件数は `104会場`。`ticketjam_venue_pages.csv` は `75行`、うち日次巡回対象 `68行`
- smoke test: 京セラドーム大阪の venue page 単体取得で `6件 kept`（`Vaundy 2 / オリックス 4`）。`駐車場券` 系は event URL 収集時に除外できることを確認
- smoke test: `国立競技場` と `MUFGスタジアム` を同時取得しても、alias 衝突なく別会場として正規化できることを確認
- 原因切り分け: 京セラドーム大阪の会場ページ自体は `Vaundy 2 / オリックス 4` しか露出せず、pure venue-page では網羅不足。`JO1` などは event page の JSON-LD が古い日付・会場を返すケースがあり、page 見出しと venue page 文脈で補正が必要と確認
- parser smoke: `JO1DER SHOW 2026 'EIEN 永縁'`（2026-04-22 / 2026-04-23）と `Vaundy DOME TOUR 2026`（2026-03-15）で、`event_start_date == event_end_date` の日別レコードとして抽出できることを確認

2026-03-11 実測メモ:
- GitHub Actions run `22835162881`（`prefecture_month`, bootstrap full）: `ticketjam_events 91件`、全件 `大阪府`。上位会場は `オリックス劇場 16 / フェスティバルホール 14 / エディオンアリーナ大阪 14 / 大阪城ホール 12 / 京セラドーム大阪 11`
- 同 run の `artist-gap` ベンチマークヒットは `0件`
- 同 run の `venue-gap` 候補ヒットは `ヤンマースタジアム長居 0 / Panasonic Stadium Suita 0 / エディオンアリーナ大阪 14`
- GitHub Actions run `22836011961`（`hybrid`, bootstrap full）: `ticketjam_events 2561件`、うち `大阪府 380件`
- 同 run の `artist-gap` ベンチマークヒットは `福山雅治 9 / 三代目 J SOUL BROTHERS from EXILE TRIBE 2`
- 同 run の `venue-gap` 候補ヒットは `ヤンマースタジアム長居 3 / Panasonic Stadium Suita 7 / エディオンアリーナ大阪 14`
- 判断: `prefecture_month` 単体は補完ソース本線としては弱く、`hybrid` を既定運用のまま維持する
- 補完評価レポート（現行DB）: `ticketjam_unique_schedules 2234`、監視スコープ内 `33`、`additional_unique_schedules 31`、`noise_rate 0.0606`
- アーティスト補完ヒット: `福山雅治 9件(additional 9)`、`三代目 J SOUL BROTHERS from EXILE TRIBE 2件(overlap 2)`、その他ベンチマークは `0件`
- 会場補完ヒット: `エディオンアリーナ大阪 13件(additional 13)`、`Panasonic Stadium Suita 6件(additional 6)`、`ヤンマースタジアム長居 3件(additional 3)`
- 大阪 `official_fetch_candidate=1` 棚卸し:
  - `Panasonic Stadium Suita`: `https://suitacityfootballstadium.jp/schedule/` に月次HTML表・前月/次月導線あり。公式 source 追加を優先
  - `大阪府立体育会館（エディオンアリーナ大阪）`: `https://www.furitutaiikukaikan.ne.jp/` に月次 `行事案内` PDF 導線あり。公式 source 追加を優先
  - `ヤンマースタジアム長居`: `https://www.nagai-park.jp/stadium/` が 2026-03-11 時点で WordPress fatal error。公式 source 追加は保留、Ticketjam 補完継続
- Panasonic Stadium Suita 公式 source 実装メモ:
  - `panasonic_stadium_suita_schedule` を追加し、2026-03-11 のローカル実行で `9件 fetched / 1 derived field refreshed`
  - 公式化に伴い `ticketjam_watch=0`, `official_fetch_candidate=0` へ変更し、補完評価レポートの監視スコープ外へ移行
- エディオンアリーナ大阪 公式 source 実装メモ:
  - `edion_arena_osaka_pdf_schedule` を追加し、公式トップページから当月以降の `monthlyYYMM.pdf` を収集して第1競技場のみ抽出する
  - 2026-03-11 のローカル実行で `15件 fetched`（`大相撲三月場所` 15日程）を確認
  - 公式化に伴い `ticketjam_watch=0`, `official_fetch_candidate=0` へ変更し、補完評価レポートの監視スコープ外へ移行
- 補完評価レポート再集計後: 監視スコープ内 `14`、`additional_unique_schedules 12`、`noise_rate 0.1429`。会場補完対象は `ヤンマースタジアム長居` のみ
- Release assets 監視メモ:
  - 2026-03-11 時点の直近10 run: `success 9 / skipped 1 / failure 0`
  - 最新成功 run: `22931909506`（`workflow_run`, updated at `2026-03-11T01:15:04Z`）
  - Release `external-events-latest` asset 更新時刻: `2026-03-11T01:15:01Z`
  - 再公開が必要な場合は `publish_external_events_assets.yml` を `workflow_dispatch` で実行し、upstream が失敗している場合は先に upstream workflow を復旧する

## Remaining Task Triage (ASCII)
Now:
- `ヤンマースタジアム長居` の公式サイト障害が解消したら公式 source を再評価する

Next:
- Release assets の定期公開結果を継続監視する

After Next:
- （なし）

Later:
- （なし）

統合メモ:
- T-20260306-002〜005 を1エピック「辞書整備バッチ（抽出→反映→計測）」として運用する
- T-20260306-010〜016 を1エピック「Ticketjam 会場基準再設計（1000+ + 種別3区分 + GUI整合）」として段階導入する
- T-20260309-002〜007 を1エピック「Ticketjam 補完スパイク（大阪）」として運用する
- T-20260311-001〜004 を1エピック「Ticketjam 補完運用（評価自動化 + 公式候補棚卸し + 公式移管）」として運用する

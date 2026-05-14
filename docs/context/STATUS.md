# STATUS（market-stats-viewer）

最終更新: 2026-05-14

## Done（直近完了）
- Release assets 公開workflowの定期監視を実施した。2026-05-14 時点の直近 publish run `25837707963` は `workflow_run` / `success` で、Release `external-events-latest` の asset は `events.sqlite` / `event_signals.sqlite` / `manifest.json` がすべて `2026-05-14T02:16:29Z` に更新されていることを確認した。公開 manifest の `generated_at_utc` は `2026-05-14T02:16:27Z`、`source_commit_sha` は `530079f519e4e81a92d4575fdab6812d3cc8a565` で、最新 publish run の `headSha` と一致する。直近の upstream data workflow はニュース更新 `25837467120`、Ticketjam 更新 `25782552884`、会場公式更新 `25783373482` がいずれも `success`。即時の手動再公開は不要と判断した。監視のみで配布DB、manifest、Release assetの内容を変更していないため `lp_impact=none`
- `T-20260502-001` として、公式PDF由来タイトルの artist/category 補完漏れを修正した。`scripts/build_events_artist_inferred.py` で、音楽イベントキーワードがない場合でも辞書の canonical artist name がタイトル先頭に高信頼で一致し、非音楽キーワードを含まない場合は `title` 単体推論を採用するようにした。alias だけの先頭一致は採用しない。`tests/test_build_events_artist_inferred.py` を追加し、`Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜` を補完すること、`LIFE! ON STAGE` の alias 先頭一致を補完しないことを検証した。`data/events.sqlite` と `data/events_artist_inferred.csv` を最新mainデータ上で再同期し、ヤンマースタジアム長居PDF由来の2日程は `artist_name_resolved=Mrs. GREEN APPLE`、`artist_confidence=high`、`event_category=コンサート` になった。監査レポート再生成後のカテゴリ精査候補内訳は `other_but_music_likely 234`、`missing_category 103`、`concert_but_non_music_hint 7`。配布DB内のカテゴリが変わるため `lp_impact=category_change`
- `T-20260512-006` として、イベント情報監査の自動マージ可否チェックリストを `docs/event_signal_audit_automation.md` に追加した。`Required Evidence`、`Auto-merge Allowed Candidates`、`Auto-merge Prohibited Candidates`、`Required Classification`、`Decision Output Contract` を定義し、初期運用では `classification=auto_merge_candidate` でも `merge_action=do_not_merge` とした。`docs/spec_update_pipeline.md` からチェックリストを参照し、`docs/context/DECISIONS.md` に `D-20260512-004` を追加した。docs運用手順追加のみで配布DB、manifest、Release assetを変更しないため `lp_impact=none`
- `T-20260512-005` として Codex automation の dry-run 運用手順 `docs/event_signal_audit_automation.md` を追加した。automation は `data/event_signal_audit_report.json` の `summary.automation_bucket_counts`、`summary.candidate_lp_impact_counts`、`summary.lp_impact` を確認し、候補配列内の各行が持つ `automation_bucket`、`lp_impact`、`needs_review_reason` を使って `report_only`、`pr_candidate`、`human_review` に分ける。`needs_review` は人間確認対象の要約一覧として使う。初期運用では、監査レポート生成、低リスク修正案の作成、verify、PR作成までを許可し、自動マージは行わない。PR本文には変更対象ファイル、根拠、verify結果、`lp_impact`、残った `needs_review_reason` を必須記載とした。`docs/spec_update_pipeline.md` から手順書を参照し、`docs/context/DECISIONS.md` に `D-20260512-003` を追加した。docs運用手順追加のみで配布DB、manifest、Release assetを変更しないため `lp_impact=none`
- `T-20260512-007` として Windows ローカルの Python / uv 実行環境を確認した。sandbox 内から `uv run` を実行するとユーザー領域の uv cache 初期化で失敗するが、実環境実行では `uv run python -c "import requests, bs4"` が `C:\Users\n-kei\dev\github\market-stats-viewer\.venv\Scripts\python.exe` を使って成功した。`uv run python -m pytest tests\test_kstyle_source.py` は pytest collection まで進み、15件を実行したうえで、既知の `JIHO&EDEN` 期待値に対して `NINE.i` を返す artist解決 assertion failure だけが残った。環境修復タスクとしては、uvキャッシュ初期化エラーやPython検出エラーは実環境では再現しないため完了扱いとし、残るpytest失敗はK-Style parser改善タスクとして扱う。LP向け配布DB、manifest、Release assetは変更していないため `lp_impact=none`
- `T-20260512-004` として統合監査レポート生成スクリプト `scripts/build_event_signal_audit_report.py` を追加し、`data/event_signal_audit_report.json` / `data/event_signal_audit_report.md` を生成した。統合対象は K-Style取得漏れ監査、イベント単位正規化監査、辞書・カテゴリ監査で、必須項目 `missed_articles`、`missed_occurrences`、`same_event_candidates`、`venue_alias_candidates`、`artist_alias_candidates`、`category_review_candidates`、`needs_review` を出力する。ローカル生成では `missed_articles 31`、`missed_occurrences 19`、`same_event_candidates 50`、`venue_alias_candidates 30`、`artist_alias_candidates 30`、`category_review_candidates 30`、`needs_review_count 171`。`automation_bucket_counts` は `human_review 92`、`pr_candidate 29`、`report_only 69`。監査レポート生成のみで配布DB、manifest、Release assetを変更しないため `lp_impact=none`
- `T-20260512-003` として `.agents/skills/dictionary_maintenance/scripts/audit_alias_candidates.py` を拡張し、会場名、アーティスト名、カテゴリ分類のメンテナンス候補を構造化レポートとして出力できるようにした。`--output-json` / `--output-md` を追加し、`venue_alias_candidates`、`artist_alias_candidates`、`category_review_candidates`、`lp_impact` を出力する。ローカルDB実行では `--top 30` で会場alias候補30件、アーティスト候補30件、カテゴリ精査候補30件を出力し、最新mainデータ上でのカテゴリ精査候補の全体内訳は `other_but_music_likely 234`、`missing_category 103`、`concert_but_non_music_hint 7`。実装前の受け入れ条件サンプルである `Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜` は、ヤンマースタジアム長居PDF由来の2日程を `current_category=その他` / `expected_category=コンサート` / `inferred_artist_name=Mrs. GREEN APPLE` として検出できていた。監査レポート生成のみで配布DB、manifest、Release assetを変更しないため `lp_impact=none`
- 市場統計とイベント情報はLP側でも利用するため、今後このリポジトリで `market_stats.sqlite`、`events.sqlite`、`event_signals.sqlite`、`manifest.json`、Release asset、関連workflow、表示用のカテゴリ・期間・集計・正規化ロジックに触れる実装ではLP影響確認を必須にした。`AGENTS.md` の repo-specific domain rule に反映し、`docs/context/DECISIONS.md` に `D-20260512-002` を追加した
- `T-20260512-002` としてイベント単位の正規化監査スクリプト `scripts/audit_event_normalization_candidates.py` を追加した。監査は `data/events.sqlite` の会場公式日程と、`data/event_signals.sqlite` の `kstyle_music` / `starto_concert` / `ticketjam_events` を読み、比較キー `event_date + canonical venue_name + canonical artist_name` で同一イベント候補を出力する。最新mainデータ上のローカルDB実行では対象レコード3345件、比較可能レコードは `official_events 557` / `kstyle_music 77` / `starto_concert 180` / `ticketjam_events 243`、同一イベント候補73グループを検出した。正規化できない候補は2365件で、内訳は `unmatched_artist 1507`、`missing_artist 724`、`missing_category 103`、`unmatched_venue 63`
- `T-20260512-001` として K-Style の取得漏れ監査スクリプト `scripts/audit_kstyle_news_coverage.py` を追加した。監査は K-Style recent news sitemap、`■公演情報` / `■開催概要` 検索、既知漏れURLサンプル、既存 `data/event_signals.sqlite` を突き合わせ、`entry_gap`、`page_limit_gap`、`parser_gap`、`coverage_gap`、`detail_not_checked` を分けて出力する。実サイトスモークでは `pages=2` / `sitemap_max_candidates=10` / `max_detail_fetch=5` で候補65件、既存DB一致34件、未収録候補31件、未収録日程19件を検出した。既知サンプルでは `KARA` 2日程、`TREASURE` 15日程、`i-dle` 2日程を抽出でき、`FTISLAND` と `SEVENTEEN ドギョム&スングァン` は本文セクションは見つかるが日程抽出できない `parser_gap` として残る
- 会場公式以外のイベント情報について、取得漏れ監査と正規化メンテナンスを同じ運用単位として扱う方針をタスク化した。初期対象は `kstyle_music` とし、監査対象は取得頻度、取得入口、取得件数上限、parser抽出可否、イベント正規化、会場正規化、アーティスト正規化、カテゴリ分類とする。`docs/context/DECISIONS.md` に `D-20260512-001` を追加し、`docs/spec_update_pipeline.md` に監査入力、出力項目、Codex automation の役割、自動マージ許可条件を反映した
- 4月の core統計更新エラー対応を確認し、正本ドキュメントへ同期した。4/6 の宿泊統計更新では `Fix tourism stats workbook selection`（commit `6fa8652`）により、観光庁ページの文字コード誤判定を補正して `推移表` Excel リンクを選択し、Excel内の `1-* / 2-* / 3-* / 4-*` シートを current / legacy に分けて解決・結合する修正が入っていることを確認した。4/13 の ICD 更新では `fix: support annual ICD workbook metadata`（commit `dd0bdf4`）により、年間 workbook の `2025年（令和7年） 暦年【確報】` 形式から `period_label=2025年年間`、`period_key=2025`、`release_type=確報` を抽出できることを確認した。宿泊統計側は既存の `D-20260406-001` と `docs/spec_update_pipeline.md` に反映済みだったため、ICD側の `DECISIONS` / `spec_icd_update_pipeline` / `spec_icd_data` を追加同期した
- `ヤンマースタジアム長居` の会場公式 source を追加した。旧 `www.nagai-park.jp` は新 `nagaipark.com` へ移行しており、`https://nagaipark.com/news/` の月次 `イベントカレンダー` PDF から `施設・場所等 = ヤンマースタジアム長居` の行だけを `events.sqlite` へ保存する `nagai_park_event_calendar_pdf` を追加した。ローカル実行では `11件 fetched` を確認し、会場マスタも `is_enabled=1`・`ticketjam_watch=0`・`official_fetch_candidate=0` へ切り替えた。補完評価レポートでは `venue_gap.watch_count=0` となり、ヤンマースタジアム長居は Ticketjam 会場補完監視から外れた
- Release assets 公開workflowの定期監視を実施した。2026-05-02 時点の直近 publish run `25240914501` は `workflow_run` / `success` で、Release `external-events-latest` の asset は `events.sqlite` / `event_signals.sqlite` が `2026-05-02T01:56:00Z`、`manifest.json` が `2026-05-02T01:56:01Z` に更新されていることを確認した。公開 manifest の `generated_at_utc` は `2026-05-02T01:55:59Z`、`source_commit_sha` は `54d87dedcf181cf4f6fbf3a031eea4544e96efc9`。直近の upstream data workflow はニュース更新 `25240772698` が `success`、Ticketjam 更新 `25204910399` が `success`、会場公式更新 `25205394079` が `success` で、即時の手動再公開は不要と判断した
- Ticketjam 補完評価レポートの再生成タイミングを広げた。`data/ticketjam_supplement_report.json` / `.md` は `events.sqlite + starto_concert + kstyle_music` を baseline とするため、Ticketjam 更新後だけでなく、ニュース更新workflowと会場公式イベント更新workflowの後段でも `python -m scripts.build_ticketjam_supplement_report` を実行するようにした
- 他アプリ向けのイベントデータ契約を `docs/spec_data.md` に整理した。`events.sqlite` は会場公式日程、`event_signals.sqlite` の `starto_concert` / `kstyle_music` はニュース速報、`ticketjam_events` は二次流通参考として分けて扱い、同一日程の統合キーは `event_date + canonical venue_name + canonical artist_name`、同一日程がある場合は会場公式日程を優先する方針を正本化した。README も外部アプリ向けの配布単位と読み分けへ同期した
- 会場公式イベント更新の定期実行を週次から `3日ごと目安` へ変更した。`update_events_official.yml` は `cron: 0 4 */3 * *` に更新し、会場公式ビューの注記も `毎週` から `3日ごとを目安に` へ変更した。GitHub Actions cron では厳密72時間間隔を表現できないため、day-of-month step による運用とした
- `ヤンマースタジアム長居` の公式導線を再評価した。2026-03-11 時点で `https://www.nagai-park.jp/stadium/` とトップ `https://www.nagai-park.jp/` はともに HTTP 500 の WordPress fatal error を返し、代替の安定した月次 schedule 導線も確認できなかったため、公式 source 追加は引き続き保留、Ticketjam 補完継続と判断した
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
1. （なし）
2. （なし）
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
- [x] T-20260311-005: `ヤンマースタジアム長居` の会場公式 source を追加する（月次イベントカレンダーPDF）
- [x] T-20260502-001: 公式PDF由来タイトルの artist/category 補完漏れを点検する（例: `Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル～間奏編～`）

## Task Backlog（News Coverage and Normalization Audit）
- [x] T-20260512-001: K-Style の取得漏れ監査を実装する
  - 主成果物: `scripts/audit_kstyle_news_coverage.py`
  - 入力: K-Style recent news sitemap、K-Style検索結果（`■公演情報` / `■開催概要`）、K-Style musicカテゴリまたは newest ページ、既存 `data/event_signals.sqlite`
  - 監査対象: 取得頻度、取得入口、取得件数上限、parser抽出可否
  - 出力: `articles_scanned`、`candidate_articles`、`matched_existing_articles`、`missed_candidate_articles`、`missed_occurrences`、`miss_reason`、`recommended_frequency_hours`、`recommended_pages`、`recommended_sitemap_max_candidates`
  - 受け入れ条件: 既知のK-Style取得漏れ候補（例: FTISLAND追加公演、KARAファンミーティング、TREASURE特別公演、i-dle横浜公演、SEVENTEENドギョム＆スングァン日本公演）について、既存DB未収録であること、または現行parserで抽出できない理由がレポートに出る
- [x] T-20260512-002: イベント単位の正規化監査を実装する
  - 主成果物: `scripts/audit_event_normalization_candidates.py`
  - 入力: `data/events.sqlite`、`data/event_signals.sqlite`、`data/venue_registry.csv`、`data/venue_aliases.csv`、artist registry CSV群
  - 比較キー: `event_date + canonical venue_name + canonical artist_name`
  - 出力: `same_event_candidates`、`normalization_gap`、source別の根拠URL、公式日程との重複候補、ニュース/Ticketjam間の重複候補
  - 受け入れ条件: 同一日程を複数ソースが拾っている場合に、重複削除ではなく同一イベント候補として出力できる
  - 実行確認: `python -m scripts.audit_event_normalization_candidates --limit 50 --output-json tmp\event_normalization_audit.json --output-md tmp\event_normalization_audit.md` で、最新mainデータ上では同一イベント候補73グループ、正規化できない候補2365件を出力した
- [x] T-20260512-003: 会場名、アーティスト名、カテゴリ分類のメンテナンス候補を抽出する
  - 主成果物: `.agents/skills/dictionary_maintenance/scripts/audit_alias_candidates.py` の拡張、または同等の監査スクリプト
  - 会場監査: `raw_venue_name` が `venue_registry + venue_aliases` で解決できない候補、住所付き会場名、地域接頭辞付き会場名、会場名変更候補を出力する
  - アーティスト監査: `raw_artist_name` が artist registry CSV群で解決できない候補、短いaliasによる誤一致候補、曖昧一致候補を出力する
  - カテゴリ監査: `event_category=その他` だが音楽イベントの可能性が高い候補、`event_category=コンサート` だが展示会・物販・配信・受賞式・テレビ放送の可能性がある候補を出力する
  - 受け入れ条件: `T-20260502-001` の `Mrs. GREEN APPLE` 公式PDF由来タイトルのような artist/category 補完漏れを、カテゴリ監査またはartist監査の候補として検出できる
  - 実行確認: `python .agents\skills\dictionary_maintenance\scripts\audit_alias_candidates.py --top 30 --output-json tmp\dictionary_maintenance_audit.json --output-md tmp\dictionary_maintenance_audit.md` で、`Mrs. GREEN APPLE` のヤンマースタジアム長居PDF由来2日程をカテゴリ精査候補として検出した。監査レポート生成のみのため `lp_impact=none`
- [x] T-20260512-004: 監査レポートを統合し、Codex automation が読める入力形式に揃える
  - 主成果物: `data/event_signal_audit_report.json` と `data/event_signal_audit_report.md`、または生成先を明記した同等の成果物
  - 必須項目: `missed_articles`、`missed_occurrences`、`same_event_candidates`、`venue_alias_candidates`、`artist_alias_candidates`、`category_review_candidates`、`needs_review`。各候補行は `automation_bucket`、`lp_impact`、`needs_review_reason` を持ち、`summary` は `automation_bucket_counts`、`candidate_lp_impact_counts`、`lp_impact` を持つ
  - LP影響確認: 外部LPが `events.sqlite` / `event_signals.sqlite` / `manifest.json` を利用しているため、監査レポートは `summary.lp_impact` と候補ごとの `lp_impact` を含める。値は `none`、`display_count_change`、`category_change`、`duplicate_grouping_change`、`source_priority_change` のいずれか、または複数を出力する。監査スクリプト追加のみで配布DBやmanifestを変更しない場合は `summary.lp_impact=none` とする
  - 受け入れ条件: Codex automation が、レポートだけを読んで「自動反映可」「PR作成のみ」「人間確認が必要」を分けられる
  - 実行確認: `python -m scripts.build_event_signal_audit_report --kstyle-json tmp\kstyle_audit_known.json --normalization-json tmp\event_normalization_audit.json --dictionary-json tmp\dictionary_maintenance_audit.json --output-json data\event_signal_audit_report.json --output-md data\event_signal_audit_report.md --limit 50 --dictionary-top 30` で統合レポートを生成した。`lp_impact=none`
- [x] T-20260512-005: Codex automation の dry-run 運用を追加する
  - 主成果物: Codex automation 用の実行プロンプトまたは運用手順
  - 処理内容: 監査レポート生成、低リスク修正案の作成、verify、PR作成までを行う。初期状態では自動マージしない
  - 受け入れ条件: 生成された修正案が、変更対象ファイル、根拠、verify結果、`needs_review_reason` を含む
  - 実行確認: `docs/event_signal_audit_automation.md` に dry-run prompt、入力、許可変更、禁止変更、レポート再生成コマンド、verify、PR本文契約、LP影響の扱い、完了条件を記載した。自動マージは初期運用で禁止する。
- [x] T-20260512-006: 限定条件付き自動マージの可否を実装前に判定する
  - 主成果物: 自動マージ許可条件と禁止条件のチェックリスト
  - 自動マージ許可候補: 監査レポートのみ、alias追加のみ、テスト追加のみ、K-Style parserの狭い形式対応のみ
  - 自動マージ禁止候補: DBスキーマ変更、会場正式名変更、`venue_id` / `artist_id` 変更、新しい外部サービス依存、parser全体の大幅再設計
  - 受け入れ条件: `docs/spec_update_pipeline.md` の Codex automation 条件と実際のチェックリストが一致している
  - 実行確認: `docs/event_signal_audit_automation.md` に `Auto-merge Gate Checklist` を追加し、許可候補、禁止候補、必須証跡、分類、JSON出力契約を定義した。初期運用では自動マージ候補でも `merge_action=do_not_merge` とする。

## Task Backlog（Local Development Environment Maintenance）
- [x] T-20260512-007: Windows ローカルの Python / uv 実行環境を修復する
  - 背景: 2026-05-12 の監査実装時に、`uv run` が通常キャッシュ初期化エラー、`.venv` の存在しない Python 参照、`AppData\Roaming\uv\python` のアクセス拒否で失敗した。そのため一時回避として、バンドルPythonに `.venv\Lib\site-packages` を `PYTHONPATH` で追加して検証した。
  - 主成果物: ローカルで `uv run` が標準verifyコマンドとして使える状態。必要に応じて壊れた `.venv` の再作成、uvキャッシュ/管理Python配置の修復、`.uv-cache/` のignore確認、Windows向けverify手順の短い記録を行う。
  - 非目標: 依存ライブラリの追加・更新、CI設定変更、アプリ本体の仕様変更はこのタスクに含めない。
  - 受け入れ条件: `uv run python -c "import requests, bs4"` が uv キャッシュ初期化エラーや Python 検出エラーなしで終了する。
  - 受け入れ条件: `uv run python -m pytest tests\test_kstyle_source.py` が uv 環境エラーではなく pytest collection まで進む。既存の artist 解決 assertion failure が残る場合は、環境修復タスクではなく別タスクとして扱う。
  - 実行確認: 実環境実行の `uv run python -c "import requests, bs4"` は成功。`uv run python -m pytest tests\test_kstyle_source.py` は15件collectionして実行し、既存の `JIHO&EDEN` / `NINE.i` assertion failure のみ残った。sandbox内だけで発生する uv cache 初期化エラーは、実環境の標準verifyコマンド失敗としては扱わない。

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
- ヤンマースタジアム長居 再評価メモ:
  - 2026-03-11 再確認時点でも `https://www.nagai-park.jp/` / `https://www.nagai-park.jp/stadium/` は HTTP 500 の WordPress fatal error
  - `nagai-park.jp` 配下の公開導線では、スタジアム固有の安定した月次イベント一覧や PDF 導線を確認できず
  - 公式 source は引き続き保留し、`ticketjam_watch=1` の補完運用を継続する
- 2026-05-02 ヤンマースタジアム長居 公式移管メモ:
  - 旧 `www.nagai-park.jp` は新 `https://nagaipark.com/` へ移行済み
  - `https://nagaipark.com/news/` の月次 `イベントカレンダー` PDF から、`ヤンマースタジアム長居` の公開予定を取得できることを確認した
  - `update_events_data --only yanmar_stadium_nagai` で `11件 fetched`。内訳には `Mrs. GREEN APPLE` 2日程、`back number` 2日程、陸上・ラグビー等の公開予定が含まれる
  - `back number` は `artist_name_resolved=back number`, `event_category=コンサート` へ補完された。当初 `Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル～間奏編～` は音楽イベントキーワードを含まないため `artist_name_resolved` が空、`event_category=その他` のまま残ったが、2026-05-12 の補完条件追加後は `artist_name_resolved=Mrs. GREEN APPLE`, `event_category=コンサート` へ補完される

## Remaining Task Triage (ASCII)
Now:
- （なし）

Next:
- （なし）

After Next:
- （なし）

Later:
- （なし）

統合メモ:
- T-20260306-002〜005 を1エピック「辞書整備バッチ（抽出→反映→計測）」として運用する
- T-20260306-010〜016 を1エピック「Ticketjam 会場基準再設計（1000+ + 種別3区分 + GUI整合）」として段階導入する
- T-20260309-002〜007 を1エピック「Ticketjam 補完スパイク（大阪）」として運用する
- T-20260311-001〜004 を1エピック「Ticketjam 補完運用（評価自動化 + 公式候補棚卸し + 公式移管）」として運用する
- T-20260512-001〜006 を1エピック「ニュース取得漏れ監査 + 正規化メンテナンス + Codex automation gate」として運用する
- T-20260512-007 はローカル実行環境の保守タスクであり、イベント取得仕様や公開データ契約の変更とは分けて扱う

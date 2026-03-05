# DECISIONS（market-stats-viewer）

> 目的：横断の決定事項を短く残す（仕様ではない。仕様の唯一の正は `docs/spec_*.md`）

## Decisions

- D-20260206-001 | アーキテクチャは「Public GitHub + GitHub Actionsでデータ生成→commit + Streamlitで表示」 | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260206-002 | データソースは観光庁の推移表Excelを優先（MVP） | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-003 | 全国（00）は推移表由来を使わず、01〜47の合算で生成する | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-004 | 表示は単一ページ（Streamlit）で「表＋グラフ」をMVPとする | status: spec_done | spec_link: docs/spec_app.md
- D-20260206-005 | 共有は make_release_zip.py によるアンカーZIP（VERSION/MANIFEST同梱）を唯一手段とする | status: spec_done | spec_link: AGENTS.md
- D-20260206-006 | make_release_zip.py の include パターンを fnmatch 前提で `scripts/**` / `docs/**` に統一し、同梱漏れ（scripts/docs）が再発しない形にする | status: spec_done | spec_link: make_release_zip.py
- D-20260206-007 | 更新スクリプト実行を `python -m scripts.update_data` に統一し、`scripts` をパッケージ化して import 破綻を回避する | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260206-008 | D-20260206-005（アンカーZIP運用）を AGENTS.md 基準の運用へ移行して完了扱い（spec_done）とする | status: spec_done | spec_link: AGENTS.md
- D-20260206-009 | openpyxl での推移表パースは `read_only=False` を採用し、セル参照型パースの性能劣化を回避する | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260209-001 | グラフを折れ線から縦棒へ変更し、チャートモード（積み上げ/同月比較）と指標・年選択を追加する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-002 | 時系列チャートに表示内容切替（国内+海外積み上げ / 全体 / 国内 / 海外）を追加する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-003 | 地域区分に地方を追加し、地方選択時は都道府県（01〜47）の月次合算で表示する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-004 | 期間指定UIを単一の年月選択から開始/終了の年・月分離に変更する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-005 | Excelエクスポートを「データ＋Excelネイティブグラフ（時系列/年別同月比較）」に拡張する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-006 | Excel出力の補助表重なりを防ぐため、年別補助表の開始行を動的決定し重なり検知ガードを入れる | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-007 | Excel出力の2チャートで軸IDを分離し、軸表示が不安定にならないようにする | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-008 | Excel出力チャートの可読性向上として凡例配置・軸表示/目盛り・グリッド・レイアウト調整を行う | status: spec_done | spec_link: docs/spec_app.md
- D-20260210-001 | グラフに「値の種類（月次 / 年計推移=表記月起点の直近12か月ローリング）」切替を追加し、時系列・年別同月比較・Excelグラフに同一反映する。年計推移では先頭11か月を非表示とする | status: spec_done | spec_link: docs/spec_app.md
- D-20260211-001 | 統計種類セレクタを追加し、宿泊旅行統計調査と旅行・観光消費動向調査をUIで切替可能にする | status: spec_done | spec_link: docs/spec_app.md
- D-20260211-002 | 旅行・観光消費動向調査は観光庁ページの集計表Excelを取得し、T06の宿泊数(8区分)別延べ泊数を全国で可視化する | status: spec_done | spec_link: docs/spec_tcd_data.md
- D-20260211-003 | `meta_tcd.json` で処理済みURL/hashを保持し、差分なし時は更新処理をno-opにする | status: spec_done | spec_link: docs/spec_tcd_update_pipeline.md
- D-20260211-004 | GitHub Actionsの更新ジョブは `python -m scripts.update_data` の後に `python -m scripts.update_tcd_data` を順次実行する | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260215-001 | 運用ルールの正本を `AGENTS.md` に統一し、`START_HERE.md` を廃止する | status: spec_done | spec_link: AGENTS.md
- D-20260215-002 | 意思決定ログの正本ファイル名を `docs/context/DECISIONS.md` に統一する | status: spec_done | spec_link: docs/context/DECISIONS.md
- D-20260215-003 | Docs階層は読込順ではなく責務（`AGENTS/README/spec/context/archive`）で固定し、`START_HERE.md` / `THREAD_START.md` は常設しない | status: spec_done | spec_link: AGENTS.md

- D-20260215-004 | 常設コンテキストの正本を `docs/context/` に統一し、`docs/DECISIONS.md` は互換リダイレクトとして維持する | status: spec_done | spec_link: docs/context/DECISIONS.md

- D-20260218-001 | 宿泊統計に全国・宿泊施設種別の客室稼働率（4-2 月別）を追加し、延べ宿泊者数と切替表示する | status: spec_done | spec_link: docs/spec_app.md
- D-20260218-002 | 宿泊施設種別稼働率ビューに都道府県切替・年/月分離フィルタ・年度比較グラフを追加する | status: spec_done | spec_link: docs/spec_app.md
- D-20260223-001 | イベント情報の都道府県フィルタを横並びトグル（複数選択）へ変更し、会場候補の連動時に候補外選択を自動解除する。未選択時は従来どおり全件対象とする | status: spec_done | spec_link: docs/spec_app.md
- D-20260223-002 | イベント情報の期間フィルタを日単位から月単位へ変更し、開始/終了の年・月を分離選択に統一する。都道府県トグルは都道府県コード順で表示する | status: spec_done | spec_link: docs/spec_app.md
- D-20260223-003 | イベント情報に種別フィルタ（すべて/コンサート/野球/その他）を追加し、title・performers・description のキーワードで自動分類して絞り込めるようにする | status: spec_done | spec_link: docs/spec_app.md
- D-20260223-004 | イベント情報の種別を実質2カテゴリ（野球 / コンサート（その他含む））に再編し、野球以外はコンサートへ分類する。フィルタUIは「すべて」を含む3択とする | status: spec_done | spec_link: docs/spec_app.md
- D-20260223-005 | 追加候補会場の第一段としてベルーナドームを有効化する。あわせて belluna_dome_schedule を現行HTML構造（月別 event-item）対応へ修正し、取得0件を解消する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-006 | 幕張メッセを有効化し、makuhari_messe_schedule を実装する。月別ページ（month=YYYYMM）とページング（page=N）を巡回してイベント取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-007 | 福岡PayPayドームを有効化し、fukuoka_paypay_dome_schedule を実装する。年次イベントページ（/stadium/event_schedule/{year}/）の dt/dd 構造から日付・タイトル・時刻を抽出する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-008 | Kアリーナ横浜を新規追加し、k_arena_yokohama_schedule を実装する。/schedule/ と /schedule/page/{n}/ の一覧から日付・タイトル・時刻を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-009 | 札幌ドームを新規追加し、sapporo_dome_schedule を実装する。/schedule/ のピックアップイベント要素から日付・タイトル・時刻を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-010 | ZOZOマリンスタジアムを新規追加し、zozo_marine_stadium_schedule を実装する。/event/schedule/ から日別ページ（/event/daily/YYYYMMDD.html）を巡回して日付・タイトル・開始時刻を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-011 | ぴあアリーナMMを新規追加し、pia_arena_mm_schedule を実装する。月別一覧（/event@p1=YYYY&p2=MM.html）から日付・タイトル・詳細URLを取得し、詳細ページの「公演時間」から開始時刻を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-012 | ポートメッセなごやを新規追加し、portmesse_nagoya_events を実装する。/events/ のイベント一覧（mc-events）から開始日・終了日・タイトル・URLを抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-013 | Asueアリーナ大阪を新規追加し、asue_arena_osaka_events を実装する。/osaka_arena/events/index.html から arena_events 詳細URLを収集し、詳細ページから日付・タイトルを抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-014 | 日産スタジアムを新規追加し、nissan_stadium_calendar を実装する。/calendar/ から detail.php を収集し、詳細ページの表（行事名・期日・開始）を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-015 | MUFGスタジアムを新規追加し、mufg_stadium_schedule を実装する。月別スケジュール（/schedule/YYYY/MM/）から詳細ページを巡回し、日付・タイトル・開始時刻を抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-016 | マリンメッセ福岡を新規追加し、marine_messe_fukuoka_event を実装する。/messe/event/ のイベント表から開始日・終了日・タイトル・開始時刻・URLを抽出して取得する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-017 | event_signals のノイズ低減として、starto_concert は `live?ct=concert` 一覧＋公演詳細SCHEDULE抽出へ切替、kstyle_music は本文 `■公演情報`（`■開催概要` 含む）セクション抽出へ切替し、日本公演のみ採用する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260223-018 | 全国イベント速報（ニュース）は掲載日ではなくイベント日で期間フィルタする。event_signals 取得時に `labels_json` へ `event_start_date/event_end_date` を格納し、UIの `score` 閾値フィルタは撤去して会場公式ビューに寄せる | status: applied | spec_link: docs/spec_app.md
- D-20260224-001 | 全国イベント速報（ニュース）の期間フィルタを会場公式同様に月単位（開始/終了の年・月分離）へ変更し、表示をイベント日昇順に統一する。STARTO/Kstyle は `labels_json` に `artist_name/venue_name/event_info` を保持して表示項目を揃える | status: applied | spec_link: docs/spec_app.md
- D-20260225-001 | 会場公式イベントのアーティスト補完を強化し、辞書は `seed + jp.seed + manual` を統合利用する。補完は `title` に加えて `description` も参照し、`event_uid` 優先で適用する。`update_events_data` 実行後に `events_artist_inferred.csv` を自動再生成する | status: applied | spec_link: docs/spec_app.md
- D-20260225-002 | 会場公式イベントの種別を `すべて / コンサート / 野球 / その他` に分離し、カテゴリ判定は「野球優先、次にアーティスト名あり/音楽キーワードでコンサート、それ以外はその他」とする。アーティスト名は辞書 canonical 名へ正規化して判定・検索に利用する | status: applied | spec_link: docs/spec_app.md
- D-20260225-003 | アーティスト辞書seedのWikidata更新を月次workflowで定期実行する。seed生成は実データ差分がない行の `updated_at` を保持してno-opを担保し、manual辞書は更新対象外のまま優先利用する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260225-004 | GitHub Actions の会場公式イベント更新を `update_data.yml` から分離し、`update_events_official.yml` を新設する。core統計更新と失敗影響範囲を分離し、events側は `update_events_data --skip-artist-inference` と `build_events_artist_inferred` を順次実行する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260225-005 | 会場公式コンサート抽出の精度改善として、短い曖昧alias（例: ベン/たま/ナビ）を補完対象から除外し、`performers == title` は未確定扱いにする。カテゴリ判定は非音楽キーワード（就活/展示会/スポーツフェスティバル等）を優先して `その他` へ振り分ける | status: applied | spec_link: docs/spec_app.md
- D-20260225-006 | 外部連携（BCL）向け配布は GitHub Release assets（tag: `external-events-latest`）を正とし、`events.sqlite` / `event_signals.sqlite` / `manifest.json` を workflow_run で自動上書き公開する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260227-001 | イベント速報（ニュース）の artist/venue は辞書正規化を保存時に適用し、原文は `raw_*` として保持する。会場は `venue_id` 固定で `venue_registry` を正本、別名は `venue_aliases` 管理とし、名称変更時は旧名を alias へ移送する。Wikidata定期更新はアーティストのみ継続し、会場は手動レビュー運用とする | status: applied | spec_link: docs/spec_data.md
- D-20260227-002 | BCL連携向けに `events.sqlite` 内で解決済みアーティスト名を完結させる。`events` テーブルへ `artist_name_resolved` / `artist_confidence` を追加し、`build_events_artist_inferred` 実行時に source値・辞書正規化・推論結果を統合同期する | status: applied | spec_link: docs/spec_data.md
- D-20260303-001 | 二次流通由来の参考情報を会場公式/ニュースと分離して扱うため、`event_signals` に `ticketjam_events` を追加する。公開sitemap→イベントJSON-LDから `イベント日/会場/アーティスト/イベント名` が揃うレコードのみ採用し、UIは「全国イベント参考（二次流通）」として別枠表示する | status: applied | spec_link: docs/spec_app.md
- D-20260303-002 | `ticketjam_events` の運用を「未来開催のMusicEventのみ」「初回はbootstrap取得、以後は増分巡回（新規+更新）」へ変更する。差分巡回では `prune_missing=false` を採用し、代わりに過去開催は更新時に削除する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260304-001 | event_signals の更新workflowをニュース系と Ticketjam 系で分離する。`update_signals.yml` は `starto_concert,kstyle_music` のみ、`update_signals_ticketjam.yml` は `ticketjam_events` のみを処理し、Release assets 公開の `workflow_run` トリガーは両workflowを監視する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260304-002 | `ticketjam_events` のコンサート抽出を `MusicEvent` 限定から「`Event` / `MusicEvent` + パンくず `categorie_groups` が `live_domestic/live_international`」へ変更し、増分巡回の既定上限を `max_sitemaps=120` / `max_event_urls=400` に引き上げる | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260304-003 | `ticketjam_events` のライブ精度を上げるため、音楽系 `categories` slug 限定・非ライブ系キーワード除外・`male/female-artist` の曖昧カテゴリに対するライブ系キーワード必須を追加する。あわせて `prune_nonconforming=true` で現行ルールに合わない既存行を更新時に削除する | status: applied | spec_link: docs/spec_update_pipeline.md
- D-20260305-001 | `ticketjam_events` は「初回のみ bootstrap full（網羅取得）」と「以後は日次の増分新規取り込み」を分離運用する。`--ticketjam-bootstrap-full` で `last_signature` をリセットして `bootstrap_max_*`（既定: 8000/50000）を適用し、通常運用は `upsert_existing=false` で新規中心に取り込む | status: applied | spec_link: docs/spec_update_pipeline.md

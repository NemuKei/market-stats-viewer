# PR #21 続行記録（2026-09-22）

## 追加続行の最新検証（main c1236cf）

開始PR head `09300a713974dd9bce9af9f1adc5b693d482dbb6`。最新main `c1236cf37870b26993969e776dd625d7a087161c` を同じbranchへ通常mergeし、最新DB/LP/候補の更新を保持。競合なし。以降の旧記録は前回baseの履歴。

### A・B・C

点検exit 0、ID衝突・孤立なし。116台帳、19県登録、公式有効32、watch12、Ticketjam75（68有効）、容量不明4。元台帳IDを削除・再採番せず、2行の公式/予定表URLと2行の別名だけを今回追加訂正した。collector有効化なし。

- [運営者ホール案内](https://www.nespa.or.jp/sports-plaza/hall/)・[主催者案内](https://www.nespa.or.jp/sports-plaza/hall/organizer/)・[予定表](https://www.nespa.or.jp/sports-plaza/hall/event-schedule/concert.html)から名称・住所・運営者・最大10,000人を確認。クロコくんホールを既存 `nihon_gaishi_hall` / 日本ガイシホールへ対応。クロコくんアリーナは別施設として別名へ含めない。施設利用休止2026/8/6〜11/30は駐車場規制と区別して記録し、休止を理由に対象除外しない。
- [朱鷺メッセ施設案内](https://www.tokimesse.com/sponsor/guide/)・[会社情報](https://www.tokimesse.com/about/)・[アクセス](https://www.tokimesse.com/visitor/access/)で運営者・万代島6番1号・展示ホールのシアター10,000人を確認。中黒/コロンの表記を既存 `toki_messe` の別名に追加。別の小ホールや会議室を同一の大型会場として吸収しない。
- AIMYON fixture全36公演・15会場のうち保留6公演を解消、全36が台帳対応。愛知4公演の開演時刻を運営者の表示予定表でも逆照合。公演取込・公開は未実施。
- 沖縄は市条例第2条の位置がaccess住所と一致することをweb閲覧で確認。ただし直接HTTP取得は失敗し、設備案内との不一致理由は未確認。address=nullと両根拠・住所相違の保留を維持し、取得失敗を成功へ書き換えない。
- 全47県の128観測を削らず2観測追加し130。114 pending、14追加確認待ち、1運営者/表示一覧確認、1住所相違。全国審査は未完了。scope `2a7324412902b9a0ccfa7ec07e971d3f49bccf9eee55b18a1aab0ad0778805aa`、8分割、最大86,244 bytes。snapshotは定期巡回実績ではない。

本文hash・取得日時・読取範囲はSOURCE_CHECKS / CENSUS_REVIEW_QUEUE。野口五郎の運営者本文も再取得・再読し、fixtureを今回のbase/scopeへ作り直した。

### D：中止・延期だけの無公開取込案

局所的にconflict保留を外す方法は旧開催予定の復活を招くため採らず、既存の公式抑止仕様へ限定して接続した。一般訂正のsource所有権・旧UIDの一括移行は今回導入しない。

`add_suppression` は実候補または信頼済みLPに対して状態だけが中止/延期へ変わる場合に限る。別IDの公式状態行を追加し旧行を保持。同時刻の旧公演だけを抑止し、既知の別時刻を保持する。Ticketjamの候補はconflictのまま、検証済み状態eventを最新判断の `official_suppression` に保存。根拠とUID等が一致する状態行だけが保留を通過する。後続判断、古いsnapshot、別根拠/別公演への書換えは通過しない。

既存LPのkeyはTicketjam keyへ転用せず、config案の内部監査項目に残す。一般の日時・会場・title等の訂正はconfig=nullで保留を維持。復帰・rollbackと互換条件は `docs/spec_event_status.md` が正本。source priority・公開field・DB schema・既存カテゴリの変更なし。

### G：再現と生成検証

テスト先行: 状態取込4ケースは未実装時4 failed / 否定ケース4 passed。状態根拠の不一致拒否7ケースは7 failed。会場旧称/別名1ケースは1 failed。実装後に全repo **289 passed / 70 subtests passed**、変更対象ruff・差分検査成功。R1〜R3の再発防止テストを含む。

4通り（中止/延期 × Ticketjam/既存LP）を一時DBから実LP生成・manifest validatorまで実行。旧19:00行・下位source行を残し、21:00公演を保持。状態行は初回1件、同じ案の再入力0件。古いsource再入力でも復活しない。別日/時刻/title/終了日への変更混入は拒否。実公演の新しい中止判断を作った試験ではない。

最新main保存LPは1,142件。最新DBコピーから再生成して1,144件。前回台帳追加のIG地域保留解除2件とTOYOTA表示名/key変更2件だけが差分で、共通keyの内容変更0。今回の2会場別名訂正による追加の既存LP変化0。時刻分割31公演/30組、抑止1は最新mainと同数（前回baseの抑止2という履歴値を流用しない）。候補1,153、期日到来816、選択60、残り756。既存履歴への自動解消書込みなし。

同じ公式11/1野口五郎公演を新baseで無公開取込試験。初回1件/再実行0件、1,145件。既存1,144件を全行保持し、17:00・長崎県・公式URLとmanifest/validatorを確認。config/DB/LP原本へ適用していない。

| 今回の一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqlite | 1,282,048 | `cb1cdfc0f6bd285f91fb154a31bf2e317aba78befe892348169d9eedb4dbaccf` |
| event_signals.sqlite | 4,194,304 | `8b63d49d6bfe70df168fd5106811c320c0b3590ea46f712356c34351b73b0253` |
| baseline-lp.json | 2,234,585 | `0cc65fb4a916767c0e5db61172b25f6aadd7e54dcad3ccf5f37aea2549951810` |
| lp_events.json | 2,236,368 | `e6f5aa7f27c9c485e7df2161e25aaf8e38fa5f8dd366a4ac921caf00fd349d47` |

入力SHA256:

- `venue_registry.csv`: `4c7376396c4303f677666e50be19705e5ef489cdd641b68ebaa0a6e5f93ec1f6`
- `venue_aliases.csv`: `5b24acc177aa3410cd04d49a07b1bb87aa9d46e1fc426c1a4c0ebf944142e754`
- `venue_web_discovery_config.json`: `8bddf7c1e295321027ad415ff3580596f183356325c20a340158652cc4520f01`
- `ticketjam_venue_pages.csv`: `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c`

上記は生成時刻に依存する一時物のhashで、公開assetではない。最終PR headへ結び付けた再試験・manifestはPR本文に記録する。

### E・F・H：残る境界

`lp_impact=present in preview`。全国対象、容量不明、旧行、3経路を保持。一般訂正、全会場審査・全予定表/発表元/SNS、Cloud/Actions/旧端末の単一writer、実使用量/遅延、定期Chat→Work起動→承認待ち→再実行、Release/実LPは未完了。前回の接続確認結果を超えるCloud実行実績は得ていない。現在の対話操作を定期成功へ読み替えない。

本番公開・権限変更・旧端末停止・定期タスク有効化は未実施。新しいPR/branch/子タスクを作らず、同じPR #21に差分を残す。`sync-needed`: 本番適用前の最新base再検証、Cloud経路受入、切替承認と旧writer停止確認、公開hash/実LP追跡。

## 前回続行の記録（main 70989a8、履歴）

同じPR・branchで続行。全国監視の本番受入は未完了。9/21のR1〜R3修正を維持し、root AGENTSとREADMEを再読して、最新mainの更新を取り込んだ。新しいPR・branch・子タスク・定期タスクは作っていない。

## A：最新データと変更範囲

開始head `12fcdad2bb1881c69847f9b8922d9ffbcb64e5be`。main `70989a8f8e36ebb49d5ed46ab0422644dfd1581e` を通常mergeし、最新のDB・LP・候補・履歴・公式config更新を保持した。競合なし。force、stash、ours/theirsは使用していない。

点検exit 0、ID衝突・孤立なし。台帳116、公式取得有効32、速報watch12、Ticketjam75（有効68）、登録19県、容量不明4。元107会場の行を保持し9会場を辞書用に追加。collector・watch・定期タスクの有効化はしていない。

| 入力 | SHA256 |
|---|---|
| venue_registry.csv | `f513e398cb51f73f4a08007e2654b8327c205e910bdb4bd86dca6d350f1b63a1` |
| venue_aliases.csv | `8f5ae6f2e6f1fef30c3e34861a29cb94a925d76cf17fc73ec03c09434249b714` |
| venue_web_discovery_config.json | `8bddf7c1e295321027ad415ff3580596f183356325c20a340158652cc4520f01` |
| ticketjam_venue_pages.csv | `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c` |

## B・C：施設審査と公式告知

全国47県128件の県・名称別観測を保持。114 pending、12施設同一性確認後の追加確認待ち、1運営者・表示予定表確認済み、1公式内住所相違。128は審査済み対象の分母ではない。SAGAスタジアムを新たに観測し、HAPPINESS ARENAの英語・日本語の両観測は残したまま同じIDに対応づけた。

| 追加ID / 施設 | 本文で確認した規模・同一性 | 残る確認 |
|---|---|---|
| ig_arena / IGアリーナ | 運営者発表の17,000人（立ち見含む）、住所、2025年開業。既存別名IDと一致 | 表示中9/10〜10/3大会以外の月・個別競技 |
| toyota_arena_tokyo / TOYOTA ARENA TOKYO | 公式施設概要の約10,000人、青海一丁目3番1号、運営会社 | 2026年9月表示全行以外の月。設営・PRIVATEを公演にしない |
| saga_arena / SAGAアリーナ | 運営者のメインアリーナ約8,400席、住所・指定管理者 | 専用月表。公園の屋外施設PDFと区別 |
| saga_stadium / SAGAスタジアム | 運営者の観客席約15,000、内メインスタンド約8,400 | 月次PDF本文 |
| happiness_arena / HAPPINESS ARENA | 複合施設のアリーナ約6,000席、所在地・運営者 | 表示一覧2026年7月〜2027年4月の各詳細。11/1の1件のみ詳細確認 |
| peace_stadium_nagasaki / PEACE STADIUM Connected by SoftBank | 同施設のスタジアム約20,000席。アリーナ・ホテルと別 | 全競技日程・各詳細 |
| wakayama_big_whale / 和歌山ビッグホエール | 運営者の最大8,500人、手平2丁目1-1、運営者 | 9月までの月次PDF本文。ビッグウエーブ等と別 |
| okinawa_arena / 沖縄サントリーアリーナ | 設備案内のセンターステージ約10,000人、運営者 | accessの山内1丁目16-1と設備案内の山内4丁目1番5号が相違。住所はnullで両根拠を保持。予定表本文取得不十分 |
| portmesse_nagoya_hall1 / ポートメッセなごや 第1展示館 | 9/21に読んだ運営者の館別根拠を再利用。施設全体と別ID | 総公演収容数、館別貸止確定日、全予定表。容量は空欄で対象保持 |

根拠URL・取得日時・取得本文hash・確認範囲は `CENSUS_REVIEW_QUEUE.json` / `SOURCE_CHECKS.json`。住所相違を推測で解消せず、運営会社事務所の住所を会場へ転用しない。ポートメッセの既存施設全体ID/保存DB行は維持し、館名が明記された今後の入力だけ専用IDへ対応づける。容量不明を除外理由にしない。

- SEKAI NO OWARIの既存fixture23公演・11会場は全23公演が台帳に対応。公演の取込・公開承認とは別。
- 沖縄の会場公式リンクから[あいみょん全国ツアー公式](https://www.aimyong.net/feature/tour2027)を読み、前半・後半すべての36公演・15会場をfacts-only fixtureへ保存。PC/モバイルの重複を除き、OPENとSTARTを分離。30公演が対応、6公演はクロコくんホール（旧日本ガイシホール）4公演・朱鷺メッセ2公演として保留。旧称/新称と運営者の追加突合が残る。保留公演も削除しない。
- 同ホームのMISIA公式入口リンクも確認したが、ツアー全日程の読取・反映は未実施。SNS投稿の過去fetch_failedを成功に変更していない。全国の発表元一覧は未完成。
- 8分割snapshotは47県・116会場・128観測、最大83,368 bytes。scope版 `1da53ddacfec467b899dd6364aabd3e6c1cfc04de1b1c84144b17cfec6e2d15a`。実運用state未接続で前回成功はnull。

## D：新規公演の取込案

`national_event_handoff --prepare-import` を追加した。現在のconfig、信頼済みLP、提案、独立した判断を再検証し、原本を変更せず追加後config案と入力hashを出力する。同内容の再入力はunchanged。別ID・不明時刻・重複した期間も保留し、既知の昼夜の時刻は分ける。Ticketjam候補は発見経路によらず元履歴のvalidatorを通し、今回の候補だけを昇格案へ含める。

テスト先行の結果は、未実装の取込案16 failed、CLI 1 failed、異なるstreamからの既存Ticketjam追認2 failed / 1 passed、別名入力/地域接頭辞の衝突2 failed。実装後は成功。既存R1〜R3も再検証した。

日時訂正・中止・延期と既存LPの変更は `source_correction_requires_migration` として停止し、config案をnullにする。下書き・元key・conflict履歴は保持する。下位sourceへの追加では、旧sourceの行やURL由来の旧UIDが消えない。元sourceの所有権・旧行の抑止/移行を安全に接続する実装が残る。現時点の対応範囲を訂正取込完了とは呼ばない。

## G：全テスト・実DBコピー・実公演の無公開試験

```sh
uv run --frozen python -m pytest -q
uv run --frozen ruff check scripts/national_event_handoff.py tests/test_national_event_handoff.py tests/test_national_venue_identity.py
python -m scripts.audit_national_event_coverage
```

**276 passed / 70 subtests passed**。全repoのpytestを実行した。既存lockを使用し、依存定義変更なし。ruff、JSON読込、BOM・差分も確認。これをCloud定期経路・Release・実LPの成功とは扱わない。

最新DBコピーと現行review stateから既存 `load_lp_records` → `build_discovery_bundle` → `prepare_batch(max_candidates=60)` を実行。保存LPは1,132件、追加台帳で再生成したLPは1,134件。候補1,162、期日到来787、選択60、残り727。既存一致を履歴へ書く `--resolve-covered` は使っていない。

LP差分を全行比較した結果:

- IGアリーナの所在地が解決し、既存KstyleのTREASURE 8/1・8/2の2公演が地域保留から掲載可能になる。地域保留数16→14。
- KARA 7/4・7/5の2公演は「東京・TOYOTA ARENA TOKYO」→「TOYOTA ARENA TOKYO」の正規化で表示名・event_keyが変わる。元DB行・日付・内容は維持。
- ほかの既存公演の内容変更なし。時刻分割31公演/30組、抑止2は維持。

[会場運営者の11/1野口五郎公演](https://www.nagasakistadiumcity.com/event/50333/)を本文で確認し、17:00開演（16:00開場）・HAPPINESS ARENA・長崎県の提案と判断を `fixtures/noguchi_20261101_*.json` に保存した。判断は今回の対話作業によるもので、Work Cloudが自動起動して検証した記録ではない。

新しいCLIを実行してconfig案を作り、既存 `VenueWebDiscoverySource` に読ませ、対象1件だけを一時DBへupsert。初回1・再実行0。既存LPの全行を保持して1,135件となり、公式URL・17:00・長崎県を確認。既存manifest builderとvalidator成功。本番config/DB/LPへ書いていない。

| 一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqliteコピー | 1,282,048 | `0d6d989eec8514ac24d0ceb3f220247f23f463601cd782ecdc3f36099df00eda` |
| 1件追加後event_signals.sqliteコピー | 4,194,304 | `ddbf652466dec0a10e21ab0125c3842a0358194e423d595691c9e35a0486ee65` |
| 追加前再生成LP | 2,220,933 | `46e612d544f16f34c708b0847222b3e6c5ec3230a873b213ccbfb7869d76c61c` |
| 1件追加後LP | 2,222,716 | `4c2aa59cfabed926509072cd86e940276cc3e42493bfcac557b9bcfa384990d4` |

ファイル全体hashは生成時刻に依存する。上記は今回の一時検証物。最終PR headに結び付けたmanifestと再テストはPR本文に記録し、同じcommitへ循環して埋め込まない。公開assetのhashではない。

`lp_impact=present in preview`：台帳追加で+2公演、表示名/derived key変更2公演、試験公演はさらに+1。実際に配布するLPは変更していない。旧derived keyを参照するconsumerへの影響は本番適用時の確認対象。DB schema・source priority・公開field・カテゴリ・Release構成を維持。

## E・F・H：接続と承認条件

日次巡回、公平性、失敗再試行、同一filesystem排他はテスト済み。Cloud/Actions/旧端末間の共有排他、実使用量・最大遅延は未検証。

接続済み操作と既存定期タスクを読み取り確認。既存の移設試験は引き続き無効・読取専用。会場監視の既存タスクも変更していない。公開された操作にはGitHubとChat定期操作があるが、Work Cloudのトリガー設定・実行結果を確認する操作は今回も発見できなかった。製品全体の非対応とは断定しない。定期Chat→提出→Work起動→承認待ち→再実行は未実測。

未完了: Bの全国審査、Cの全予定表・全国発表元・SNS、Dの訂正/中止延期の元source移行、E/Fの実Cloud経路・単一writer、Hの切替許可・旧writer停止確認・公開hash・実LP追跡。非公開タスクID、prompt、運用記録、端末設定、raw logは公開repoへ置かない。

本番公開・権限変更・旧端末停止は未実施。承認条件を緩めず、PR #21上でレビュー可能な差分として残す。

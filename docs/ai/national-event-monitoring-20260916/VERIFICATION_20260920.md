# PR #21 続行の検証記録（2026-09-20）

全国監視の完成・Cloud移設・本番公開は未完了。Aの点検結果を修正し、Bの調査を広げ、C〜Gを無公開で検証した。同じPR・同じbranchで継続し、新しいタスク・branch・worktreeは作っていない。

## 目的と今回の変更境界

利用側の成果は、全国のドーム級・アリーナ級・スタジアム級について、会場公式・速報・Ticketjam補完から公式確認した日程をLPへ届けること。今回の成功条件は、準備済みコードを原本で再実行し、誤った施設対応を訂正し、全国の未確認事項とオフライン受入の試験結果を再開可能に残すこと。

局所修正だけでは三経路の受渡しが欠けるため、既存validator・取込・LP生成を再利用する受入処理と巡回状態を追加した。全面的なcollector再設計や新規外部サービスは導入していない。data差分はwatch対応・表示名・公式URLだけ。既存DB、LP、manifest、公開field、source priority、依存定義、workflow、認証・権限、定期タスク、旧端末は変更していない。

`lp_impact=none`：最新mainのDBから再生成したLPのevents配列は既存1,183件と一致（初回検証は1,170件）。URL/watch訂正は将来の探索先・会場照合に影響するため、後日の本番取込では改めて検証する。`sync-needed`：全国台帳審査、発表元審査、定期Chat→Work受入、writer切替、公開後のRelease/利用側照合。SideBizへの反映は行っていない。

## A：実行場所・原本・同一性

- Cloud作業領域でrepo clone、GitHub接続でPR読取に成功。Python 3.12.14 / Git 2.51.1。旧PCで実行したという意味ではない。
- 引継ぎhead `24fe83fd53c059ec04b0b2293c379fd3f7a223c0` に、最初のmain `fd70e2c2b19b1e5f2bc1787deb21ad9cb5afa282` を通常merge。競合の強制採用・stash・force pushは使っていない。以後の最新main再確認はPR本文とGit履歴に残す。
- 原本auditの初回はexit 1：台帳の `mufg_stadium=味の素スタジアム` とwatchの `mufg_stadium=国立競技場` が衝突。保存DBの同ID64行は全て味の素公式URL。国立の `national_stadium` は別実体として維持する。
- 訂正後auditはexit 0、衝突/孤立IDなし。104台帳 / 公式有効32 / watch12 / Ticketjam75（有効68）/13県/容量不明3。これは取得成功・全国網羅率ではない。
- 国立watchを `national_stadium` に訂正。Ticketjamページ6816の既存IDは変えず表示名を味の素へ合わせ、国立ページ6834と分離。4会場の参照URLを運営者公式へ訂正。回帰テストは修正前に失敗、修正後に成功した。

原本3入力SHA256（9月20日の設定訂正前→後）:

| ファイル | 訂正前 | 訂正後 |
|---|---|---|
| venue_registry.csv | `f12729dbd6bd096390e92d11c1892aed0f781cca75609ce3b5c81f67ff015d72` | `4280f348f850f2d5f183f1f7216dabc2e0616f3d23ff8c5ef2a16486c16bf2ea` |
| venue_web_discovery_config.json | `7c7258d3faa4e53668693685d575856ef21f5111d87d79d08bde34bb00775d1e` | `8f3b441e430749796f399c3c884512263deedcf0a34176ee614a664feca69e5b` |
| ticketjam_venue_pages.csv | `092d93cce9e425d882262203c8cf743c917de766d9f6dedafd41f52782bdd892` | `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c` |

## B・C：全国調査と読み取り

`CENSUS_REVIEW_QUEUE.json` は47県124件の県/名称別観測。B.LEAGUEの55アリーナ掲載、J1/J2/J3の全60クラブの公式プロフィール、引継ぎの運営者候補、公式全国ツアー、NPB本拠地一覧を突合した。別名や新設予定が混ざるため、施設数や審査済みの分母へ読み替えない。サッカー入場可能数はコンサート収容数に読み替えず、不明はnullと `missing_fields` に残した。大館のニプロハチ公ドームは公式の屋根修繕による一部利用制限を記録し、一般的な閉館や個別公演中止を推定していない。

根拠の入口: [B.LEAGUE](https://www.bleague.jp/new-bleague/club/)、[J.LEAGUEクラブ](https://www.jleague.jp/club/)、[NPB本拠地](https://npb.jp/stadium/franchise.html)、[和歌山を含む公式ツアー](https://sp.super-beaver.com/live_information/detail/6056)、[ニプロハチ公ドーム](https://jukaidome.com/)。個別のURL・観測時刻・本文hashはJSONへ保存。原文全文は収録していない。

登録済み13県も対象から外さず、104会場の既存公式URLを取得した。`REGISTRY_SOURCE_CHECKS.json` は本文取得87、本文未読4、取得失敗13。**予定表の全公開範囲を確認した件数ではない**。画像/PDF、403等を新規公演なしにしない。追加16入口の結果は `SOURCE_CHECKS.json`。公式サイトからリンクされるSNSでも第三者出演者等の可能性があり、本人性未審査のリンクを分けた。IGアリーナとSEKAI NO OWARIの公式アカウントの本文取得は失敗、他の多くは投稿未試行。

読取snapshotは8分割、最大79,261 bytes。scope版 `2bb9af1d4ad7ba48c38028d37811672087cea1a1200590d5e036e0f0f0dabe57`。全47県、既存104会場、候補124件、保存公式URLを保持する。現在の運用stateは未接続なので前回成功を捏造せずnull。生成された一覧は正本ではない。

Bの残件は自治体・施設運営者との追加突合、施設実体/別名、住所・容量根拠、休館/廃止/新設状況の審査。全県に候補があることは全国台帳完成ではない。Cの残件は予定表範囲の実閲覧、全国の発表元リスト、別名探索の継続状態、SNS読取の実測。既存STARTO/Kstyleは保持した。

## D・E・F：オフラインで確認したこと

`national_event_handoff` はdata-only提案を検証し、独立Work判断を既存公式event形式へ渡す。古いbase/scope/key、未知会場、追加コードfield、重複JSON key、256KiB超入力、提案と根拠の不一致、SNS/二次流通単独の公式昇格を拒否する。提案PRの通常ファイル限定チェックも試験した。実GitHub差分へ接続した常駐の受入はまだない。

`national_event_state` はJST日次単位、最古未確認の優先、確認済み/失敗/未巡回、再開位置、進捗なし停止、内容hashとローカル排他、同一変更の三経路統合、昼夜公演の区別を試験した。通知/反映時刻は未実施ならnull。別Cloud worker/Actions/旧端末をまたぐ排他成功ではない。

合成候補から独立したWork判断、一時config、既存source、一時SQLite、LP、manifest、公開validatorまで接続した試験が成功。これは合成データの無公開試験であり、実公式確認・実運用のconfig取込を行った記録ではない。

既存のGitHub操作と定期実行の利用可能な操作を確認した。対話中の読取成功は確認できたが、定期Chatからの提出とWork自動起動を証明する結果は得られていない。既存の無効・読取専用の移設試験を無断で書込試験に変更していない。追加タスク作成、既存タスク変更、workflow dispatch、通知送信は未実施。非公開のタスクID・prompt・運用記録は本資料へ転記しない。

## G：再現コマンドと結果

既存lockから依存を準備。依存定義の変更なし。

```sh
uv run --frozen python -m pytest \
  tests/test_ticketjam_publication.py tests/test_ticketjam_review_state.py \
  tests/test_prepare_ticketjam_review.py tests/test_ticketjam_official_checks.py \
  tests/test_validate_external_events.py tests/test_ticketjam_context_conflict.py \
  tests/test_national_event_coverage.py tests/test_national_venue_identity.py \
  tests/test_national_event_handoff.py tests/test_entity_aliases.py \
  tests/test_build_lp_events.py tests/test_venue_web_discovery_source.py \
  tests/test_ticketjam_discovery.py -q
```

結果: **144 passed, 28 subtests passed**。加えて新規コードのruff、構文、JSON/文字コード/差分点検を実施。全repoの全テスト・実ブラウザLP検証を成功扱いしない。

[SEKAI NO OWARI公式の全国ツアー](https://sekainoowari.jp/info/2026/09/18/7918/)を23公演全てfixtureに残した。15公演は既存IDに対応、8公演は会場対応未確定として受入停止（広島・福井・ポートメッセ第1展示館・静岡各2）。施設群と第1展示館を推測で同一化しない。OPEN/STARTは別、正確な発表UTC不明はnull。実公演をDB/LPへ取り込んでいない。

現行DBのコピーを一時領域で使用し、`build_lp_events`、`prepare_ticketjam_review --max-candidates 60`（`--resolve-covered`なし）、既存manifest生成、`validate_external_events.validate_package` を実行した。LP1,170件のevents配列は現行LPと完全一致。候補planは期日到来1,193、選択60、残り1,133。DBコピーのhashは元DBと一致。生成時刻によりLP全体hashは既存LPと異なる。

初回生成の入力と出力hash（base `760184db84163843bd287048462d27b362b4187f`、本番配布物ではない）:

| 対象 | bytes | SHA256 |
|---|---:|---|
| events.sqliteコピー | 1,282,048 | `b8b38b3f6a1fd903a9b3966836ba36f320d22f4926d06963ba35b1ecd74d352b` |
| event_signals.sqliteコピー | 4,194,304 | `476f8215f79783b3edc3e712e56a5e838b6309ed9d5d787b048a684c2e5d5728` |
| 再生成lp_events.json | 2,283,998 | `c7d86dce345c5c7d11d69178e501413c178ec904500ac8a8558230f4bd518583` |

最終headの検証SHAと最新baseへの追随結果はPR本文へ記録する。検証記録自身を含むcommitのSHAを同じファイルへ循環して埋め込まない。

### main更新後の再検証

作業中にmainへ `33a4192c1525701eaf01f68aeea52c81d1ba75af`（別の公式確認結果）が追加されたため、同じbranchへ通常mergeした。競合なし。mainのDB/LP/確認履歴を維持し、PR固有のdata差分は引き続き3設定の計7行訂正だけ。読取snapshotも再生成し、追加された保存公式URLを反映した。

- 144 tests / 28 subtestsを再実行して成功。
- LP再生成は1,183件、最新mainのevents配列と一致。内訳は会場公式579、venue_web_discovery438、STARTO101、Kstyle65。開始時刻による分割32件/30組、地域保留15件、中止延期等による抑止1件。Ticketjam由来の要再確認保留1件も消さず維持。
- 再確認planは期日到来902、選択60、残り842。過去の1,193を現在の残件として使わない。既存一致の自動書込は0、`--resolve-covered`なし。
- 設定訂正後の `venue_web_discovery_config.json` hashは `4c224585e40f9bae55768667316ce0bbcd04ddb5e21a5d29282618d054da5366`。他2設定のhashは上表のまま。scope対象版も同じだが保存公式URLを含む分割のhashはindexを更新した。
- ロック依存を使わない直接 `python -m scripts.national_event_handoff` はrequests未導入で失敗したため、再現コマンドを既存lockを使う `uv run --frozen` に訂正して実行成功を確認した。

再生成物hash（検証head `c2fbc7a6bc72773e72b29a6acd9108203faf4cfc`、公開なし）:

| 対象 | bytes | SHA256 |
|---|---:|---|
| events.sqliteコピー | 1,282,048 | `b8b38b3f6a1fd903a9b3966836ba36f320d22f4926d06963ba35b1ecd74d352b` |
| event_signals.sqliteコピー | 4,194,304 | `373595d03ef47437edec7a0ddb86b3e6bce4e5b4c82d59eb029c25620d2e470b` |
| 再生成lp_events.json | 2,324,147 | `905ecc3313f1d20012038c889093d0b75d642c20f1096287436e4d94b0de5de4` |

manifest/公開validatorが成功し、コピーDBが元DBと同じであることも再確認した。main更新で増えた13件はこのPRによる新規取り込みではない。

## H：未実施と次の受入

mainへの取込、実config apply、Release、SideBiz取込、利用側の実LP確認、本番Chat登録・Work自動起動、権限変更、旧端末writer停止は実施していない。検証済みのローカルmanifestを公開済みと表現しない。

次はBの全国台帳審査を進め、Cの監視先と未取得を確定する。Fの無人経路の実測結果、共有writerの実装・競合試験、既存writer停止の確認、切替の承認範囲が揃うまではHに進まない。旧設定を保持する復帰手順、最新baseでの再生成、公開段階ごとのhashと失敗再開を確認する。現状の排他はローカルのみであり、既存Actionsの競合解決方法もCloud切替前の残課題。

# PR #21 レビュー修正・続行記録（2026-09-21）

全国監視の本番受入は未完了。同じPR・同じbranchで、[ハンドオフレビュー](https://github.com/NemuKei/market-stats-viewer/pull/21#pullrequestreview-5260662904) のR1〜R3を先に再現・修正した。新しいPR・branch・子タスク・定期タスクは作成していない。

## レビュー指摘の再現と修正

実repoの関数を呼ぶpytestで再現した。レビューに添付されたAST切出しスクリプトの実行結果ではない。

| 指摘 | 修正前の回帰テスト | 修正内容と確認範囲 |
|---|---|---|
| R1 | 5 failed / 1 passed | 日次容量2・対象3・先頭2の継続失敗で3番目へ進まないことを再現。日付・scope版をまたぐ最終試行を履歴から導き、未試行を優先。成功時刻は失敗で進めない。JST翌日から再試行。全件が収まる回、同日再開、scope変更、旧v1履歴、重複・過去日の拒否、残数・遅延を確認 |
| R2 | 5 failed / 3 passed | Ticketjam旧19:00→公式18:30と日付訂正で、旧候補のconfirmed検証に落ちることを再現。元履歴にはconflict、訂正後は別の公式下書き。日時変更・中止・延期、旧履歴保持、元key/fingerprint、変更前config fingerprintを確認。古い候補・別origin・根拠不一致・未知会場は引き続き停止 |
| R3 | 6 failed / 6 passed | 提案・Work・既存Ticketjamの3入口でUTC日付比較を再現。JST暦日へ統一。UTC14:59/15:00、23:59/翌00:00（JST23:59/翌00:00、08:59/09:00）で前日拒否・当日以降受理を確認 |

R2は下書きの受渡し修正。元の誤候補をconfirmedに書き換えず、既存conflictによる派生行の掲載保留も維持する。訂正後下書きを直接configへappendする取込処理は未実装。`config_review_status=not_checked` は審査成功ではない。

レビューで別途挙がった、Ticketjam以外の既存LP公演の訂正も接続した。Workが信頼済みbaseのLPを読み、実event_key、行全体fingerprint、変更前値を照合する。元keyをnullにせず、入力LPのfingerprintとともにoriginへ残す。時刻・日付・中止・延期、古いbase/行/変更前値、重複keyを試験した。snapshotの内容hashだけで取得元を認証したことにはならない。取得元の確認と元sourceへの取込はWorkの残条件。

## A：最新baseと実データ

開始head `295d1d2172916c99c2dd040271998e357209f01e` にmain `151e02a5a9389c25063c58e69ec013f6dd1054a8` を通常merge。競合なし。mainのDB・LP・候補・履歴・公式config更新を保持した。force、stash、ours/theirsは使っていない。

点検はexit 0、衝突・孤立IDなし。台帳107、公式取得有効32、速報watch12、Ticketjam75（有効68）、登録15県、容量不明3。元の104会場と全カテゴリ・保存IDを維持し、運営者で確認した3会場を辞書用として追加した。自動取得の有効化は行っていない。味の素の既存ID・保存行と国立watchの回帰テストも成功。

| 入力 | SHA256 |
|---|---|
| venue_registry.csv | `6eb78e507770eed62e86feefd7d5cc60bab5727492a6f4311f5a9126d4869934` |
| venue_aliases.csv | `a462025609d1431ded5cee347544f1f278296d2faea302e9ce83c166bbe152d4` |
| venue_web_discovery_config.json | `9ee69e7e98e2632c8374205d23384443b74897a9255fef9d2caa22c4f49af45e` |
| ticketjam_venue_pages.csv | `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c` |

## B・C：運営者確認と残る全国審査

調査待ち一覧は47県127件の県・名称別観測。122件はpending、4件は施設同一性確認後の追加確認待ち、1件は運営者情報と表示中の予定表を確認済み。**全国台帳の完成や127施設の網羅を意味しない**。容量やcollector未対応で除外していない。

| 対象 | 確認と反映 | 残件 |
|---|---|---|
| 広島グリーンアリーナ | [運営者](https://h-jigyoudan.or.jp/sports-center/center-facility/)で大アリーナ最大約10,000人・固定約4,400席、住所・運営者を確認。新ID追加 | 9・10月月間PDF本文、年間表。小アリーナと統合しない |
| サンドーム福井 | [運営者の施設概要](https://sundome.sankan.jp/about-us-h/)の9,000席、住所・運営者を確認。新ID追加。[公開一覧](https://sundome.sankan.jp/eventinfo/)の4催事6日分を読取 | 公開一覧は全将来期間や非公開行事の保証ではない |
| エコパアリーナ | [公式施設概要](https://www.ecopa.jp/facility/arena/)で正式名・最大10,000人・所在地を確認。既存IDへ静岡アリーナ等の別名を追加 | 全月・個別詳細の照合 |
| エコパスタジアム | [公式詳細](https://www.ecopa.jp/facility/stadium/)の50,889席、正式名・所在地を確認。アリーナとは別IDで追加 | 全月・個別詳細の照合 |
| ポートメッセ第1展示館 | [館別概要](https://portmesse.com/facility/tenjikan01)、[施設概要](https://portmesse.com/outline)、[貸止告知](https://portmesse.com/20145)を読取。2026年の大会利用と一般貸止を保持 | 総公演収容数、館別確定日、親施設IDからの移行。施設全体の15,000を転用せず、2027年公演を中止としない |

実ツアーfixtureの23公演・11会場を保持。会場対応は15→21公演、未解決はポートメッセ第1展示館の2公演。残る2件を推測で既存施設IDへ統合せず、受入停止を維持する。DB取込・公開はしていない。

[LDH公式ツアー](https://www.ldh-liveschedule.jp/sys/tour/40198/)も全12公演を読み、会場台帳への逆照合を記録した。STARTO公演一覧・SEKAI NO OWARI公式入口を再確認。既存STARTO/Kstyleを維持。広島の公式サイトからSNSリンクの本人性を確認したが、投稿取得はInternal Errorでfetch_failed。過去のIG/SEKAIの投稿取得失敗も成功に変更していない。全国の発表元一覧は未完成。

8分割snapshotは全47県・107会場・127観測を含み、最大81,325 bytes。scope版 `e8f8150c1dc73e81f8ecec46767c0bac4752031b0406fb18f3c42793f3e4f870`。実運用stateは未接続なので前回成功はnull。過去の104公式URL取得記録を107件の当日取得実績には読み替えない。

## D〜F・H：実装と実測の境界

- 提案→公式下書き、旧候補conflict履歴、既存config置換の共通guard、信頼済みLPの元公演照合をオフライン実装・試験した。Workによる本人性・本文確認を自動で行ったことにはならない。実config/DBへ取り込む接続は未完了。
- 日次巡回の公平性・再試行・最大経過時間は合成テスト済み。全国の実運用所要時間・使用量・遅延は未計測。同一filesystemの排他はCloud/Actions/旧端末の共有排他ではない。
- 既存のGitHub・定期実行操作を再確認。既存の移設試験は無効・読取専用で、書込試験へ変更していない。今回公開されている操作からWork Cloudのトリガー設定・実行結果を確認する経路を見つけられず、定期Chat→提出→Work自動起動→承認待ち→再実行を実測していない。製品全体の非対応とは断定しない。
- 本番公開・権限変更・旧端末停止は未実施。無人経路の受入、単一writerの競合試験、切替許可、旧writer停止確認、Git/Release/実LPのhash追跡が揃うまでHは未達。
- 非公開タスクID、prompt、運用記録、端末設定は公開repoへ保存していない。

## G：再現可能な無公開検証

```sh
uv run --frozen python -m pytest \
  tests/test_national_event_handoff.py tests/test_national_event_state.py \
  tests/test_ticketjam_review_state.py tests/test_ticketjam_publication.py \
  tests/test_prepare_ticketjam_review.py tests/test_ticketjam_official_checks.py \
  tests/test_validate_external_events.py tests/test_ticketjam_context_conflict.py \
  tests/test_national_event_coverage.py tests/test_national_venue_identity.py \
  tests/test_entity_aliases.py tests/test_build_lp_events.py \
  tests/test_venue_web_discovery_source.py tests/test_ticketjam_discovery.py -q
```

結果: **181 passed, 28 subtests passed**。既存lock使用、依存定義変更なし。変更Pythonのruff、JSON読込、BOM/差分、secret markerも点検。全repo全テスト、定期実行、Release、実LPの成功とは別。

最新mainのDBコピーから `build_lp_events`、`prepare_ticketjam_review --max-candidates 60`（`--resolve-covered`なし）、manifest生成、公開validatorを実行。LPは1,149件、現行LPのevents配列と一致。会場公式579、venue_web_discovery414、STARTO91、Kstyle65。開始時刻分割32件/31組、地域保留16、抑止2。候補1,183、期日到来810、選択60、残り750。既存一致の書込0。前日の1,183掲載件数へ戻していない。

| 一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqliteコピー | 1,282,048 | `b8b38b3f6a1fd903a9b3966836ba36f320d22f4926d06963ba35b1ecd74d352b` |
| event_signals.sqliteコピー | 4,194,304 | `f38cfb0e117c1eae09259044a34ceb45634d5031e232a66cba68c9490260c176` |
| 再生成lp_events.json | 2,253,115 | `9dafc9057b2c2ed3b37ef1aa7438681932694759c06fc2e9adf3c3dd7ff2230e` |

生成時刻によりLPのファイル全体hashは再実行ごとに変わる。上表は今回の一時生成物。最終PR headをmanifestへ結び付けた再検証SHA・hashはPR本文へ記録し、循環して同じcommit内へ埋め込まない。公開assetのhashではない。

`lp_impact=none`（今回の再生成結果）：現行events配列は一致。将来の会場解決・地域・統合には台帳追加/別名追加が影響し得るため、本番取込前に再生成を必須とする。`sync-needed`：Bの全国実体審査、Cの予定表・発表元、Dの承認された取込接続、E/FのCloud受入と単一writer、Hの承認後の公開・利用側検証。既存ID・DB schema・公開field・source priority・Release構成は維持する。

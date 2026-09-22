# PR #21 続行記録（2026-09-22）

## 15会場追加・予定表本文確認の検証（最新）

開始head `ecd07827042b46a40ad276fff630b035aaa08bb5`、tree `39854c37f38833ec19131b9f7cca23ce62553013`。main `c1236cf37870b26993969e776dd625d7a087161c`。同じPR/branchで継続し、root AGENTS・既存A〜H条件・R1〜R3の修正を保持した。対象は全国のドーム/アリーナ/スタジアムと既存カテゴリのまま。

今回の成果は、未審査会場の公式入口と施設同一性、予定表の読取範囲を補い、3経路のsnapshotと既存の提案/検証/生成経路を同じ変更として確認すること。台帳・別名・調査記録・派生一覧・fixtureのみ変更。原本DB/runtime config/LP、公開field、優先順位、workflow、権限は変更しない。

### A・B：追加と審査の範囲

原本audit exit 0、160台帳・47都道府県・公式有効32/watch12/Ticketjam75（68有効）。容量不明13、ID衝突/孤立/scope alias衝突なし。開始headの145台帳行と別名全行はbytes単位のprefix一致。全国132観測のID/名称/元evidenceをすべて保持し、15観測を新台帳へ接続、既登録11観測の審査を前進。既存住所/容量の異なる尺度はprior_facility_observationsに残した。

現在の内訳はpending 61、operator_identity_verified_schedule_pending 47、identity_verified_schedule_pending 22、operator_and_visible_schedule_reviewed 1、operator_verified_address_conflict 1。審査を進めた26件にもmissing_fieldsを残す。132を全国網羅率の分母とせず、未確認・改修・容量不明を除外しない。

| 追加会場 | 台帳規模の根拠・留保 |
|---|---|
| 明治神宮野球場 | 公式施設案内29,943人。動的月間表は見出しのみ取得 |
| エディオンピースウイング広島 | 指定管理者の開業案内約28,520席。現行席種変更は追加照合 |
| メルカリスタジアム | 公式40,003人。正式名カシマ・メルスタを別名へ |
| ミクニワールドスタジアム北九州 | 総収容数未確認。日程の見出し/本文矛盾を保留 |
| サンプロ アルウィン | 座席16,000＋立見4,000。公園全体を別名にしない |
| デンカビッグスワンスタジアム | 約42,300人。別球場・補助競技場を統合しない |
| えがお健康スタジアム | 運営者案内3万人。再開/休止告知の詳細画像は未読 |
| アオーレ長岡 | アリーナ最大5,000。予約窓口と管理主体の権限は追加確認 |
| ゼビオアリーナ仙台 | 最大7,200、総座席4,660。過去一覧から現行月へ要確認 |
| EBARA WAVE アリーナおおた | メイン4,012席。旧名大田区総合体育館を別名へ。群馬の太田と区別 |
| アリーナ立川立飛 | 定員3,275。ドーム立川立飛は別施設 |
| エスフォルタアリーナ八王子 | 観客席2,700は部分値、全体収容数未確認のまま |
| ホワイトリング | 市のメイン観客席5,008（運営者約5,000）。工事予定経過だけで完了としない |
| おおきにアリーナ舞洲 | メイン7,056席。ホームのサンプル告知は実催事と扱わない |
| 横浜武道館 | アリーナ約3,000、別室の武道場500を合算しない |

すべてis_enabled=0/ticketjam_watch=0、official_fetch_candidate=1。既存collectorを有効化せず、規模不明も監視候補へ残した。千葉ポート/フクダ/日産等の容量尺度の差、ノエビア公式本文取得失敗は記録し、無言の採用値変更を避けた。日産の台風告知は対象施設/催事別で、スタジアム全休止とはしない。

### C：閲覧範囲と失敗を分離

PDFはrequestsで取得し、抽出文字と描画画像の全ページを照合した（6件10ページ）。青森10月2頁、郡山ボンズ10月1頁、石川10月1頁、三重サン10月2頁、盛岡タカヤ10月2頁、JIT小瀬9月2頁。URL・取得時刻・raw body hash・pages_read・読み取った範囲をCENSUS_REVIEW_QUEUE.jsonに保存し、raw本文/画像はrepoに入れない。

- 青森/郡山/石川は施設予約の範囲を含む。連続した予約日や利用時間を実試合/公演の日時にしない。
- 三重はメイン催事と教室・屋外の別会場を区別。8/20時点の予定なので変更の確認を残す。
- 盛岡はアリーナ予定・卓球/トレーニングを区別。別施設「盛岡体育館」の休館をタカヤへ移さない。
- JIT小瀬は本体/補助競技場の個人利用可否。利用不可を公演あり、空きを公演なしとは判定しない。

HTMLは各schedule_reviewsに範囲を記録。ピースウイング/ビッグスワン/横浜武道館の9月本文を確認し、現地試合とパブリックビューイング、準備撤収と催事、武道場とアリーナを分離。メルカリはtitle6月/本文9月、ミクニは見出し9/30/本文8/26の不一致を未解決として保持。他の予定表は見えた一部・入口のみを明記した。全月/全件を確認済みとはしない。

HTTP成功でも空本文（照葉等）、別サイトへの転送（旧武道館候補URL）、別施設（熊本の運動公園）を公式施設確認成功とはしない。失敗URLと再確認先を保持。公式ページ上のSNSリンクは候補として保存し、投稿本文の取得は未実施。アーティスト公式/ニュース/SNSとTicketjam補完の既存経路・全国ツアーfixturesも保持した。

3経路の8分割snapshotを更新。最大127,393 bytes、scope `bf374f3801b30e38b9037c1a120188db86e79b8e16231cd2d19c8495b2c7b997`。これは読取用一覧であり定期巡回状態の成功更新ではない。

### D〜G：実行した検証

- `uv run --frozen python -m pytest -q`: **309 passed / 70 subtests passed、51.26秒、exit 0**。R1〜R3、日時訂正/中止延期、時刻分割、再試行/排他、全国ツアーの既存回帰を含む。今回は調査/辞書の追加で実装挙動を変えておらず、新しいテストコードは追加していない。
- dictionary-maintenanceの既存read-only audit exit 0。signals 1,408 / official 1,236行。17時/1部/TOYOTA他など未解決候補は引き続き審査対象とし、機械的な別名登録をしない。
- 新しい正規名/別名の全表記を実lookupで検証し、隣接ドーム・別野球場・公園全体・別体育館・群馬太田の5例を誤統合しないことを確認。
- 開始headの原本7ファイル（3DB・LP・Web config・Ticketjam pages/state）がbytes一致。保存manifestは前後とも存在せず、一時生成のみ。元145台帳/別名全行をprefix一致で保持。
- コピーDBから再生成LPは1,144件。前回再生成のevents配列全行と一致し、今回15会場の追加による表示差分0。main保存1,142件との差は既存のIG +2、TOYOTA 2公演の表示名/key差のみ。時刻分割31件/30組、抑止1、地域保留14。
- 実公演の既存fixture（長崎11/1野口五郎17:00）を新scopeへ更新。提案→判断→取込案→一時DBは初回1/再実行0、LP1,145件。既存1,144件を全行保持し、日付/時刻/県/公式URL/manifest validatorを確認。原本へ適用していない。
- Ticketjam候補1,153、期日到来816、既存上限60/残756。補完候補を公式確認済みへ昇格させない。source priorityは既存の公式優先を維持。

| 一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqlite | 1,282,048 | `cb1cdfc0f6bd285f91fb154a31bf2e317aba78befe892348169d9eedb4dbaccf` |
| event_signals.sqlite | 4,194,304 | `56e463241c8314ff6bc8f6ce1eacf36ffb9b5f5580051b43641c41e219901a9f` |
| baseline-lp.json | 2,234,585 | `59753188feb34eb4fa6faef1fb16bbcc470ab3d33259fb05f97ff838795fe31e` |
| lp_events.json | 2,236,368 | `be4644744351e4681fae1c8b5e2cb935a28c7252634069fde7069a73c9cd4a95` |

入力SHA256:

- `venue_registry.csv`: `e444cb05e6217e33c6e66641569fd9a755fa4fcf6c83f78a6700024f66ab472d`
- `venue_aliases.csv`: `95eebe4d62fe2129c88537bbb988de582a1770508ea5fa64b7fcb06656fc37e0`
- `venue_web_discovery_config.json`: `8bddf7c1e295321027ad415ff3580596f183356325c20a340158652cc4520f01`
- `ticketjam_venue_pages.csv`: `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c`
- `CENSUS_REVIEW_QUEUE.json`: `4f5bd876d4ef367878150f8b93bf697c4fdeed5e51120e98a4671423c8965bbb`

最終PR headの再テスト、remote tree、manifest commit/hashはPR本文へ追記する。生成時刻付き一時物のhashを公開assetのhashとして扱わない。

### E・F・H：未実施と次の条件

利用可能な既存Chatタスクをread-onlyで再確認したが、Work Cloudの定期実行トリガー/結果を確認できる操作は見つからず、定期経路の成功は未検証。私的タスク設定/ID/promptは公開repoへ保存しない。新規タスク、既存タスクの変更・手動起動も行っていない。

Bの未審査61と追加確認69、Cの他月/全件/全国発表元/SNS本文、Dの承認された取込と実体変更/連続訂正、E/Fの定期提出→Work起動→承認待ち→再実行、単一writer・実使用量・最大遅延、Hの切替承認・旧writer停止確認・公開hashと実LP追跡は残る。全国台帳も予定表監視も完了ではない。

`lp_impact=none for this registry increment`（既存events全行一致）。未公開・未移設で、Release/SideBiz/権限/旧端末は未変更。`sync-needed`: 残る施設/予定表/公式発表元審査、実Cloud受入と単一writer、最新baseの再検証、Hの承認と公開経路の実確認。

## 全国22会場追加の検証（履歴）

開始head `6bc3b8153959daaeb2b20907189b4fc2a25ecc47`、tree `41c1dd35b9bb418ab7cbc1f751b8f5702c0c5801`。main `c1236cf37870b26993969e776dd625d7a087161c` を再fetchし変化なし。root AGENTS・README・指定ハンドオフレビューを読み、既存R1〜R3修正を保持。同じPR/branch、子タスクなし。

利用側の目標は全国の公式確認済み催事を3経路からLPへ届けること。今回は未登録府県の施設同一性・公式入口を台帳へ補い、全県読取一覧と既存生成経路まで検証する単位とした。変更対象は台帳/別名/調査記録/派生snapshot/実公演fixture。公演の原本DB、runtime確認済みconfig、保存LP/manifest、workflow、公開field、source priority、権限は変更しない。

### A・B：全県に登録を広げ、未審査も保持

原本audit exit 0: 145台帳、47都道府県、公式有効32/watch12/Ticketjam75（68有効）、容量不明11。ID衝突・孤立・scope alias衝突なし。元123台帳行と全別名行はbytes単位のprefix一致で保持。131観測のID/名称/元evidenceを全件保持し、21観測へ運営者・県の施設確認を追記、三重県営サンアリーナを新規観測として追加した（132観測）。元の収容数/住所/用途/出典は `prior_facility_observations` に保持し、異なる定員の尺度を黙って上書きしない。

件数内訳: pending 87、operator_identity_verified_schedule_pending 30、identity_verified_schedule_pending 13、operator_and_visible_schedule_reviewed 1、operator_verified_address_conflict 1。登録が47県にあることと、全国施設の網羅審査完了は別。これらの観測数を網羅率の分母にしない。既存県の施設・野球場・展示会・音楽以外のカテゴリも調査対象のまま。

| 都道府県 | 追加会場 | 採用した規模と主な留保 |
|---|---|---|
| 青森 | カクヒログループスーパーアリーナ | Bリーグ時約3,500人。人数閾値で除外しない |
| 岩手 | 盛岡タカヤアリーナ | 総収容数不明。観覧席3,098を全体最大数としない |
| 山形 | NDソフトスタジアム山形 | 21,174人。公園全体名・工事中の新スタジアムをaliasにしない |
| 福島 | 宝来屋ボンズアリーナ | 最大5,013席。季節別の木曜定休と長期休止を区別 |
| 茨城 | アダストリアみとアリーナ | 5,000人。2026年3月改修後の席数3,638を確認、サブを加算しない |
| 栃木 | カンセキスタジアムとちぎ | 約25,000人。第2陸上競技場と別 |
| 群馬 | オープンハウスアリーナ太田 | 総収容数不明。VIP席を全体数に転用しない |
| 富山 | 富山県総合運動公園陸上競技場 | 芝生含む約25,000人。新武道館と別 |
| 石川 | いしかわ総合スポーツセンター | メイン5,019席。サブを加算しない |
| 山梨 | JITリサイクルインクスタジアム | Jリーグ入場可能数15,853を保持。総最大数は追加確認 |
| 岐阜 | ヒマラヤスタジアム岐阜 | 26,109人。2026/4/1愛称変更を県発表で確認 |
| 三重 | 三重県営サンアリーナ | メイン最大11,000人。AGF鈴鹿体育館候補を置換・削除しない |
| 京都 | サンガスタジアム by KYOCERA | 約21,600人。将来の京都アリーナと別 |
| 奈良 | ロートアリーナ奈良 | 総収容数不明。7/2再開後も2階席の一部制限。ロートフィールドと別 |
| 鳥取 | Axisバードスタジアム | 16,033人。概要リンクが別グラウンドへ遷移する箇所を採用しない |
| 島根 | バンダイナムコアリーナ松江 | 改修後の総収容数不明。9/1愛称変更、7/1〜10/7全館一般利用休止 |
| 岡山 | JFE晴れの国スタジアム | 約20,000人。公園住所と競技場詳細住所を併記 |
| 山口 | 維新みらいふスタジアム | Jリーグ入場可能数15,115。芝生等を含む最大数は追加確認 |
| 高知 | GIKENスタジアム | 県の施設案内25,000人。運営者HTTP取得失敗、現行運営者と稼働状況は保留 |
| 大分 | クラサスドーム大分 | 可動席含む40,000人。野球場のクラサススタジアムとは別 |
| 宮崎 | いちご宮崎新富サッカー場 | 公式概要5,354人。Jリーグ入場可能数1,819は別尺度で保持 |
| 鹿児島 | 西原商会アリーナ | 最大約5,700席。メイン休止2026年7月〜2028年9月、他室は利用可能 |

詳細の住所・法人・別名・本文hash・取得日時・URL・不足項目は `CENSUS_REVIEW_QUEUE.json`。全22会場の collector は無効、Ticketjam watchは0のまま。定員・休館・未対応を除外条件にしていない。高知の県による施設本文確認を、運営者の現行指定管理確認へ昇格させていない。

松江の根拠は[9/1名称変更](https://www.so-tai.jp/cgi-bin/rus7/news/view.cgi?d=227)と[利用休止](https://www.so-tai.jp/cgi-bin/rus7/news/view.cgi?d=223)。鹿児島は[メイン休止](https://nishihara-shokai-arena.jp/emergency/13165)と[10/22〜23の全館休館](https://nishihara-shokai-arena.jp/emergency/13366)を分離した。休止中の一般利用とリニューアル行事、他室のイベントを一括抑止しない。施設調査から個別催事の中止判断を自動作成していない。

### C：読めた範囲と失敗を分離

栃木・京都は2026年9月のHTML予定表、岡山は9月の施設別一覧、群馬は9/24・26の試合表示、大分は9/22〜10/1の公園一覧、岐阜は10/12見学会表示、鹿児島は9月の表示範囲を読んだ。公園全体の表を特定施設のイベント一覧と同一視せず、他施設・準備・予約・駐車場行を区別する。これらを今回新たにDBへ取り込んでいない。

青森/岩手/福島/石川/三重/山梨等のPDF予定表はリンク確認までで本文未読。山形の施設選択後、富山の個別予定表、動的カレンダー、他月、全主催者・全国発表元・SNS本文は未完了。松江の大会一覧は記事なし表示だが、イベントなし/予約なしとしない。高知のHTTP取得失敗を4試行分、宮崎の初回失敗を1試行分保持（宮崎は再試行成功）。read-scopesの実巡回状態はunvisitedのまま、対話内調査を定期実行結果へ加算しない。

8分割snapshot、最大 94306 bytes、scope `f3e2c15b669cd20a1a3b7995d87d5ac39811af79e12a37637d2c66b77c7e1551`。登録145行と審査待ち観測を同じ正本から参照。3経路・STARTO/Kstyle・Ticketjam補完と全国ツアーfixture（SEKAI 23、あいみょん36）は保持。

### D〜G：同じ生成経路で再検証

- `uv run --frozen python -m pytest -q`: **309 passed, 70 subtests passed**、exit 0。R1の巡回偏り、R2のTicketjam訂正、R3のJST日付、日時訂正・中止/延期・既存6focusedを含む。今回の変更は辞書/調査データで、製品コード・テストの追加変更なし。
- 既存 `audit_alias_candidates.py --top 20` もexit 0（signals 1,408 / official events 1,236）。上位表示には「17時」「1部」等の会場以外の抽出値、「TOYOTA ARENA TOKYO 他」、他施設名等が残る。調査根拠なしでaliasへ登録せず、未解決のまま継続審査とする。
- 追加22会場と別名の42表記を実lookupで検証。公園全体/ロートフィールド/クラサススタジアム/長良川球場の4例が隣接する別施設へ吸収されないことを確認。
- 最新main DBのコピーから再生成LP1,144件。開始headで生成済みの1,144件とevents配列全行一致（カテゴリ・key・時刻・source・容量等も同じ）。今回22会場追加による既存LPの差分は0。main保存LP1,142件との既存差はIG +2、TOYOTA 2公演の表示名/key変更のまま。
- 現行値は時刻分割31公演/30組、抑止1、地域保留14。Ticketjam候補1,153、期日到来816、選択60、残り756。未確認候補を掲載へ昇格させていない。
- 既存[11/1野口五郎の公式根拠](https://www.nagasakistadiumcity.com/event/50333/)を再利用し、scopeを更新した提案/判断fixtureを再作成。一時DB追加は初回1件/再実行0件。LP1,145件、既存1,144件を全行保持、17:00・長崎県・公式URL・manifest validatorを確認。定期Work Cloud受入の試験ではない。

| 一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqlite | 1,282,048 | `cb1cdfc0f6bd285f91fb154a31bf2e317aba78befe892348169d9eedb4dbaccf` |
| event_signals.sqlite | 4,194,304 | `6c35821da41afeefa356f61c7780479799a66d23dc858548fee03c9321232885` |
| baseline-lp.json | 2,234,585 | `87fe6f6a980c2ad771722a10951c8277c1b1b94534f604b2d0e9b390501ba5b7` |
| lp_events.json | 2,236,368 | `8f04dead1767cf0f5f8a20d46eb8bf5ac3a54e1f81f05236dcc612313a6cf604` |

入力SHA256:

- `venue_registry.csv`: `1042eac1284fed2840c3d58cfd72e83f0fd1acb6cb1f559a9e6dc881c37a408b`
- `venue_aliases.csv`: `64eb672895761830b3768a6f857474ef1c7712d3c3785369cb0d2b57d762ef9b`
- `venue_web_discovery_config.json`: `8bddf7c1e295321027ad415ff3580596f183356325c20a340158652cc4520f01`
- `ticketjam_venue_pages.csv`: `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c`
- `CENSUS_REVIEW_QUEUE.json`: `cb5b57af453760e82cb877552b018778c0866c53eb6d6437154a6b110d89f20f`

最終PR headでの再実行、manifestのcommit/hash、remote tree照合結果はPR本文へ記録する。生成時刻に依存する一時物のhashを公開assetのhashとして扱わない。

### E・F・H：今回も成功を主張しない項目

全国台帳Bの未審査87観測と各missing_fields、CのPDF/動的表示/全予定表・全国発表元・SNS、Dの承認された本番取込と実体変更・連続訂正、E/Fの定期Chat提出→Work Cloud起動→承認待ち→再実行、単一writer、実使用量・最大遅延は未完了。利用可能な操作の再確認でも定期Work Cloud起動/結果を確認できず、現在のPR操作をその証拠にしない。新しい定期タスクを作らず、既存タスクも変更・手動起動していない。

`lp_impact=none for this registry increment`（開始headの既存表示と一致）。PR全体の追加/訂正preview影響と本番反映は別に評価する。未公開・未移設、原本DB/config/LP/manifest・Release・SideBiz・権限・旧端末は未変更。`sync-needed`: 最新baseの再照合、未完了施設/発表元の審査、実Cloud受入と単一writer、Hの切替承認・旧writer停止確認、公開hash/実LP追跡。

## 会場7件追加・日時訂正の検証（履歴）

開始head `c3d6b60c6997e73a28448512ed08258f91b3f3c2`、main `c1236cf37870b26993969e776dd625d7a087161c`。最新fetchでも同じmainのためmergeなし。同じPR/branch、子タスクなし。root AGENTS、引き継ぎ、関連specに従い、source→一時DB→LP→manifestを検証。本番の公開・権限・旧端末・既存タスク・runtime config/DBは変更していない。

### A〜C：全国対象の保持と運営者確認

点検exit 0。123台帳・25県登録、公式有効32/watch12/Ticketjam75（68有効）、容量不明7。ID衝突・孤立なし。元116会場を全件保持。全47県の130観測を保持してエムウェーブを追加し131観測。108 pending、12 identity_verified_schedule_pending、9 operator_identity_verified_schedule_pending、1 operator_and_visible_schedule_reviewed、1 operator_verified_address_conflict。全国完成ではない。

| 追加会場 | 運営者本文で確認した規模 | 状況・残る確認 |
|---|---|---|
| ニプロハチ公ドーム（秋田） | アリーナ使用時15,000人、固定観覧席5,040人 | 屋根膜工事による全グラウンド競技の制限を保持。個別中止は推定しない |
| ビッグハット（長野） | 全体人数不明。面積・ステージ部分席数は人数へ転用しない | 2027年4月上旬〜10月末の休館予定。隣接施設の通常開館と区別 |
| エムウェーブ（長野） | 20,000人、常設約6,500席 | 9/18現在の見えている予定のみ。冬季別ページ・後続月は未確認 |
| アスティとくしま（徳島） | 多目的ホール最大5,000人 | 9月と隣接10月の表示範囲を読取。全月・時刻は未確認 |
| 愛媛県武道館（愛媛） | 全体人数不明。1階988、2階2,896の部分席数を記録 | 9月行事一覧と主/副道場の別を確認。全月・時刻は未確認 |
| グランメッセ熊本（熊本） | 全体人数不明。8,000㎡は面積、770/1,318はDゾーン席数 | 9月表示の中止・延期告知を保持。個別本文・全月は未確認 |
| 滋賀ダイハツアリーナ（滋賀） | メインアリーナ約5,018席 | 指定管理者根拠は2022年挨拶。現行指定期間・全予定表は未照合 |

住所・運営者・別名・出典URL・取得日時・本文hash・取得状態・予定表の確認範囲は `CENSUS_REVIEW_QUEUE.json` へ記録。raw本文はrepoへ入れない。主な出典は [ニプロ概要](https://jukaidome.com/summary/)、[ビッグハット](https://www.nagano-mwave.co.jp/bighat/)、[エムウェーブ概要](https://www.nagano-mwave.co.jp/m_wave/about/)、[アスティ概要](https://www.asty-tokushima.jp/about/)、[愛媛施設案内](https://ehime-spa.jp/budoukan/architecture/)、[熊本施設案内](https://www.grandmesse.jp/kiji0031/index.html)、[滋賀施設案内](https://shiga-arena.jp/gallery)。容量未確認でも除外せず、collector有効化はしない。スポーツ・展示会等の既存カテゴリを維持。

8分割、最大86244 bytes、scope `2b402730a0dfba750bf2733bfeee9c4386f61cc00267aec91e1e8f85191347f1`。取得済み本文と定期巡回の成功は別であり、実状態はunvisitedのまま。SEKAI 23公演・あいみょん36公演の全国fixtureも全件対応を再テスト。

### D：日時訂正と再現テスト

既存の状態抑止経路を残し、日時だけの訂正を別IDの `add_correction` へ接続。単なる新行追加では旧sourceが残るため、Workの信頼済みDBと現行LPを再現して対象sourceだけを退役させる限定修正とした。任意のsource置換や物理削除は導入しない。内部proof・互換・移行・復帰は `spec_event_status.md` が正本。

- Ticketjam / 実LP起点それぞれで、時刻・日付・終了日・前倒しの8ケースを一時DB→LP→manifestまで確認。中止/延期の既存4ケースも維持。元候補conflict・旧DB/config行・別時刻の公演を保持し、初回1件・再入力0件。
- 日時訂正4ケースは未実装時のテスト失敗を確認して実装。後日の90日窓で訂正行だけが落ち、旧19時が再表示される2ケースも失敗を観測し修正。訂正証跡は期間外でも読み、旧行退役後に表示期間を適用する。
- 古いDB/LP版、根拠改変、未審査の別UIDによる旧日時、訂正先の別公演、共有の時刻不明source、連続訂正、不正proofを停止。取得時刻のみの更新と、古い対象行が期間外になったケースは許容。
- CLIで本物の一時SQLiteを読み、入力不変と90日窓を確認。訂正非対応のdisplay/reviewed生成を停止。future_onlyでも訂正証跡を捨てない。
- 終了時刻・無効化を混ぜた訂正、会場/出演者/title変更、状態との混在、一般の実体変更は対応範囲外。退役計画の本番適用・実公演日時訂正は未実施。合成検証を実公演の訂正成功と扱わない。

### G：実施した全体検証と表示差分

`uv run --frozen python -m pytest -q`: **309 passed, 70 subtests passed**。R1〜R3および指定6 focusedを含む。変更Pythonのruff check、diff check成功。最終PR headへの再試験とmanifestのcommit/hashはPR本文へ記録する。

最新main保存LP1,142→再生成1,144。差は前回からのIGの地域保留解除2公演とTOYOTAの表示名/key変更2公演のみ、共通key内容変更0。今回7会場追加による追加の既存LP差分0。時刻分割31公演/30組、抑止1、地域保留14。候補1,153・期限到来816・選択60・残り756。

[野口五郎11/1公演](https://www.nagasakistadiumcity.com/event/50333/)の本文を再取得し、日付・17:00・HAPPINESS ARENAを確認。新scopeでfixtureを再作成。最新DBコピーへの追加は初回1件・再実行0件、LP1,145件。既存1,144件を全行保持し、公式URL/長崎県/時刻/manifest/validatorを確認。これは対話内の無公開試験であり、定期Work Cloud経路ではない。

| 一時検証物 | bytes | SHA256 |
|---|---:|---|
| events.sqlite | 1,282,048 | `cb1cdfc0f6bd285f91fb154a31bf2e317aba78befe892348169d9eedb4dbaccf` |
| event_signals.sqlite | 4,194,304 | `dc4cbd5d5a8b918ca7e5c778255d3f45417c20859c8e252ef5fdc0ad616f2ad7` |
| baseline-lp.json | 2,234,585 | `b41a750473f8bd8857569dfdb624723b379e7bf8a3683ae575ef710c522fba06` |
| lp_events.json | 2,236,368 | `57d14a0b150565e56ad44a4984d464a10316abcc87ece765349e89d90450f5fa` |

入力SHA256:

- `venue_registry.csv`: `46f460f975bb7a95652429caad6f9c1bc5fb1b4e0eb334d2f9e07c05d8094419`
- `venue_aliases.csv`: `bd206141a0533b726a5ef822a4d86e918d4e1f37ce2122e8df0bf8c2a1852843`
- `venue_web_discovery_config.json`: `8bddf7c1e295321027ad415ff3580596f183356325c20a340158652cc4520f01`
- `ticketjam_venue_pages.csv`: `6ae738a0a0b447f9ac7b7a96de1cb2ddb574890c65839b72bb5b889501c9ef0c`

生成時刻に依存する一時物であり、Release assetではない。公開していない。最終headへ固定した再検証hashはPR本文を参照。

### E・F・H：未実施・未完了

`lp_impact=present in preview`。3系統の提案・受入・取込案・DB/LP生成へのコード接続は試験したが、全会場/予定表/全国発表元/SNSの審査、実Cloudの起動・定期提出・承認待ち・再実行、Cloud/Actions/旧端末の単一writer、実使用量と遅延、Release/実LP追跡は未完了。前回を超えるCloudトリガー操作・結果は得ていない。自動化を成功扱いせず、既存タスク・公開権限・旧端末設定を変えない。

次の再開はBの未審査108観測と各会場missing_fields、Cの全予定表/発表元を続け、Dの実体変更/連続訂正とE/Fの実経路を検証する。Hの切替許可・旧writer停止確認・公開hash追跡より先に本番へ進めない。`sync-needed`: 最新base再照合、承認されたruntime取込、Cloud受入と単一writer実測、Release/実LP。

## 前回追加続行の検証（main c1236cf、履歴）

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

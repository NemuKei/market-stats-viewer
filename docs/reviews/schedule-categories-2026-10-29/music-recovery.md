# 今回戻せた音楽と残る音楽分類の除外（全行）

比較元はPR #36の22fb22a。題名や日程は変更せず、判定だけを比較する。件数は日程レコード数。

## 保存日程：未分類→コンサート全14行

| ID | 日付 | 題名 |
|---|---|---|
| evt_55a415811e72422f9a2d2628db316198 | 2026-02-07 | 第76回さっぽろ雪まつり17thKPF（K-POP FESTIVAL）2026 |
| evt_bed6c3682fb643de93cfe26b5956b0d8 | 2026-02-11 | HOKKAIDO MUSIC FESTIVAL2026雪まつりSPECIAL! |
| evt_df005ebe10f44e19922421bc20748d87 | 2026-02-18 | MVサイバー衣装お披露目！「BRAVE GROOVE」リリース記念 iLiFE!単独公演 |
| evt_a7fa82a2bd8f44d99fbedbfef047fd81 | 2026-04-03 | CENTRAL MUSIC & ENTERTAINMENT FESTIVAL 2026 『CENTRAL STAGE』 =LOVE / 乃木坂46 / FRUITS ZIPPER / モーニング娘。'26 ※乃木坂46は16名前後のメンバーでの出演を予定しております。 |
| evt_b49d6569aadb4eeeb57e6f5598f77d51 | 2026-04-03 | beat crazy Presents Special Gig「B.C. ONLY +1 2026」 |
| evt_d7e307469632445ca63af9967777cac0 | 2026-04-04 | CENTRAL MUSIC & ENTERTAINMENT FESTIVAL 2026 『CENTRAL STAGE』 amazarashi / ORANGE RANGE / 結束バンド / 凛として時雨 |
| evt_323d33963c7b492cb1cfa98b5b375a20 | 2026-04-05 | CENTRAL MUSIC & ENTERTAINMENT FESTIVAL 2026 『CENTRAL STAGE』 ちゃんみな / HANA / 優里 |
| evt_5030c36b47de43b4903e55a9b61bc4ba | 2026-04-07 | beat crazy Presents Special Gig「B.C. ONLY +1 2026」 |
| evt_2c632f52d46a47f3b8aae245c58a1f28 | 2026-04-08 | beat crazy Presents Special Gig「B.C. ONLY +1 2026」 |
| evt_6617fab186394cc6beec073cb44fcf4f | 2026-04-11 | ambitious Zepp Sapporo単独公演-5th Anniversary PartY- |
| evt_cfe3ab20afa84e41b3450ea8ed1f7c9b | 2026-04-12 | 第9回大阪府職場・一般吹奏楽フェスティバル |
| evt_924513e265d4483eaced91568307881e | 2026-04-14 | キミノウィルス 【キミノウィルス単独公演】桜蘭ノ刻 -朧郷- |
| evt_c322717a2cfd4faab7311a9369af75ef | 2026-05-02 | アイドル音楽フェス The ONE ～一音一生～ |
| evt_5b598f41f8af44bd89e64bceecb0008e | 2026-05-10 | Kiramune Music Festival 2026 |

今回の追加によりコンサートから外れる行：0行。

## DB：前回予測の未分類→コンサート全9行

| ID | 日付 | 題名 |
|---|---|---|
| pia_arena_mm:event/6653.html | 2026-07-11 | FNC BAND KINGDOM 2026 |
| pia_arena_mm:event/6655.html | 2026-07-12 | FNC BAND KINGDOM 2026 |
| zepp_haneda:https://www.zepp.co.jp/hall/haneda/schedule/single/?rid=158073 | 2026-07-14 | 日本工学院ミュージックカレッジ presentsCROSS SPARK |
| festival_hall:https://www.festivalhall.jp/events/6543/ | 2026-08-31 | 大阪芸術大学サマーミュージックフェスティバル2026 |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=159485 | 2026-10-17 | kurayamisaka tte, doko? #8「Zepp DiverCity単独公演編」 |
| zepp_namba:https://www.zepp.co.jp/hall/namba/schedule/single/?rid=159273 | 2026-11-01 | J:COM Presents 高校軽音フェスティバル2026 |
| zepp_sapporo:https://www.zepp.co.jp/hall/sapporo/schedule/single/?rid=167860 | 2026-12-03 | NORTHERN LIGHTS CHRISTMAS GIG at Zepp Sapporo |
| fukuoka_paypay_dome:https://fukuokamusic-fes.com/2027/index.html#d=2027-01-30#t=10:20 | 2027-01-30 | FUKUOKA MUSIC FES.2027 supported by Trunk |
| fukuoka_paypay_dome:https://fukuokamusic-fes.com/2027/index.html#d=2027-01-31#t=10:20 | 2027-01-31 | FUKUOKA MUSIC FES.2027 supported by Trunk |

今回の追加によりコンサートから外れる行：0行。

## 元の保存済みDB分類からコンサートを外す全72行

前回レビューから新たに外した行ではない。既存の誤分類修正・材料不足の判定により残る除外69＋3行を、全件再掲する。DBそのものは変更していない。

| ID | 日付 | 題名 | 今回 | 根拠 |
|---|---|---|---|---|
| zepp_sapporo:https://www.zepp.co.jp/hall/sapporo/schedule/single/?rid=152839 | 2026-07-18 | 全国のZeppをリアルピースがジャック！『リアフェスin全Zepp』 | 未分類 | insufficient_evidence |
| mufg_stadium:/schedule/2026/0725_15800.php | 2026-07-25 | BOOSTランニングフェスタ（ナイト） in 味の素スタジアム | その他 | non_music_keyword:ランニング |
| festival_hall:https://www.festivalhall.jp/events/6298/ | 2026-07-30 | 地主薫バレエ団公演「パキータ」「ラ・シルフィード」 | 未分類 | insufficient_evidence |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20260819 | 2026-08-19 | 満腹ドーム！ジンギスカンフェスト | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/5984/ | 2026-08-20 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=157167 | 2026-08-20 | 史上最大の極寿司炎～超Zeppin～ | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/5997/ | 2026-08-21 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/5998/ | 2026-08-22 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/5999/ | 2026-08-22 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6000/ | 2026-08-23 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6001/ | 2026-08-24 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6686/ | 2026-08-24 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| vantelin_dome_nagoya:h:ef1254f9dae4e59f | 2026-08-24 | NTPグループ 創業70周年記念 わくわくフェスタ | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6003/ | 2026-08-26 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6004/ | 2026-08-27 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6005/ | 2026-08-27 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6006/ | 2026-08-28 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6007/ | 2026-08-29 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6008/ | 2026-08-29 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| osaka_jo_hall:https://www.sukusuku.com/event/ss2026/#d=2026-08-29#t=10:30 | 2026-08-29 | おかあさんといっしょスペシャルステージ2026　おおさか公演 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6009/ | 2026-08-30 | 2026年劇団☆新感線46周年興行・夏公演 SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！～蒸気の黒ダイヤ、あるいは狂気の島 ～』 | 未分類 | insufficient_evidence |
| osaka_jo_hall:https://www.sukusuku.com/event/ss2026/#d=2026-08-30#t=10:30 | 2026-08-30 | おかあさんといっしょスペシャルステージ2026　おおさか公演 | 未分類 | insufficient_evidence |
| zepp_osaka_bayside:https://www.zepp.co.jp/hall/osakabayside/schedule/single/?rid=152927 | 2026-08-30 | リアフェスin全Zepp | 未分類 | insufficient_evidence |
| pia_arena_mm:event/6981.html | 2026-08-31 | ぴあ Presents エンタメ業界研究フェス VOL.2 | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=163595 | 2026-08-31 | ブザフェス~10th Anniversary year~ | 未分類 | insufficient_evidence |
| zepp_osaka_bayside:https://www.zepp.co.jp/hall/osakabayside/schedule/single/?rid=160511 | 2026-09-05 | BM-ECHOES FESTIVAL 2026 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6379/ | 2026-09-12 | 大阪クラシック 2026 第60公演 | 未分類 | insufficient_evidence |
| pia_arena_mm:event/6946.html | 2026-09-13 | シャインポスト シャインポスト BRiGHT STARS FESTIVAL 2026 "The Girls Beyond the Rainbow" | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=153699 | 2026-09-13 | 『リアフェスin全Zepp』 | 未分類 | insufficient_evidence |
| tdc_hall:https://taskhavefun.net/contents/1085432#d=2026-09-21#t=17:00 | 2026-09-21 | TASK THE SHOW at Kanadevia Hall ー衝動の夜,衝動の衝突ー | 未分類 | insufficient_evidence |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20260926 | 2026-09-26 | SBI MUSIC CIRCUS HOKKAIDO 第一部 | 未分類 | insufficient_evidence |
| pia_arena_mm:event/7173.html | 2026-10-10 | STARフェス | 未分類 | insufficient_evidence |
| pia_arena_mm:event/7175.html | 2026-10-11 | STARフェス | 未分類 | insufficient_evidence |
| nissan_stadium:https://www.nissan-stadium.jp/calendar/detail.php?id6a86b20b64c58 | 2026-10-12 | YOKOHAMAスポーツ・レクリエーションフェスティバル2026 | 未分類 | insufficient_evidence |
| tokyo_dome:https://www.tokyo-dome.co.jp/dome/baseball/parkday/#d=2026-10-17 | 2026-10-17 | TOKYO DOME PARK DAY | 未分類 | insufficient_evidence |
| zepp_namba:https://www.zepp.co.jp/hall/namba/schedule/single/?rid=168307 | 2026-10-25 | みんがるSP in Zepp Namba | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6779/ | 2026-10-31 | 法村友井バレエ団 公演『リーズの結婚』（La Fille mal gardée） | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=156378 | 2026-11-01 | SHELTER 35th Anniversary Finale " ZeppがSHELTERになります " DAY1 | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=156379 | 2026-11-02 | SHELTER 35th Anniversary Finale " ZeppがSHELTERになります " DAY2 | 未分類 | insufficient_evidence |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20261103 | 2026-11-03 | みんなのピックルボール IN PREMIST DOME | 未分類 | insufficient_evidence |
| mufg_stadium:/schedule/2026/1114_16273.php | 2026-11-14 | 京王駅伝フェスティバル 2026 | 未分類 | insufficient_evidence |
| osaka_jo_hall:h:6c56cba3d32d90e6 | 2026-11-21 | 第45回全日本小学生バンドフェスティバル(フロア部門) ・第39回全日本マーチングコンテスト(中学生の部) | 未分類 | insufficient_evidence |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20261121 | 2026-11-21 | コープさっぽろ 食べる・たいせつフェスティバル2026 | 未分類 | insufficient_evidence |
| vantelin_dome_nagoya:h:2f405ea27b90bb8b | 2026-11-21 | 中日ドラゴンズ ファンフェスタ2026 | 未分類 | insufficient_evidence |
| vantelin_dome_nagoya:https://dragons.jp/special/fanfesta/2026/#d=2026-11-21#t=13:00 | 2026-11-21 | 中日ドラゴンズ ファンフェスタ2026 | 未分類 | insufficient_evidence |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20261122 | 2026-11-22 | 北海道最大のハンドメイドフェスティバル サッポロ モノ ヴィレッジ 2026 秋 | その他 | non_music_keyword:ハンドメイド |
| vantelin_dome_nagoya:https://dragons.jp/special/fanfesta/2025/#d=2026-11-22#t=13:00 | 2026-11-22 | 中日ドラゴンズ ファンフェスタ2025 | 未分類 | insufficient_evidence |
| zepp_namba:https://www.zepp.co.jp/hall/namba/schedule/single/?rid=159402 | 2026-11-22 | Music Splash!! | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6822/ | 2026-11-24 | 第54回 天王寺楽所 雅亮会 雅楽公演会「江戸幕府と天王寺舞楽」 | 未分類 | insufficient_evidence |
| mufg_stadium:/schedule/2026/1128_16282.php | 2026-11-28 | BOOSTランニングフェスタ in 味の素スタジアム | その他 | non_music_keyword:ランニング |
| sapporo_dome:https://www.sapporo-dome.co.jp/schedule/detail?date=20261211 | 2026-12-11 | プレコン！～ときめき巡る、大人の縁結びフェス～ | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6784/ | 2026-12-27 | 第4回 「玉響」 還暦記念公演 | 未分類 | insufficient_evidence |
| yokohama_arena:/event/detail/%E3%83%88%E3%82%A4%E3%83%AD%E3%83%95%E3%82%A7%E3%82%B92027 | 2027-01-09 | トイロフェス2027 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6861/ | 2027-02-25 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6862/ | 2027-02-27 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6863/ | 2027-02-27 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6864/ | 2027-02-28 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6865/ | 2027-03-01 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6866/ | 2027-03-02 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6867/ | 2027-03-04 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6868/ | 2027-03-04 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6869/ | 2027-03-05 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6870/ | 2027-03-06 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6871/ | 2027-03-06 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6872/ | 2027-03-07 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6873/ | 2027-03-09 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6874/ | 2027-03-10 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6875/ | 2027-03-11 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| festival_hall:https://www.festivalhall.jp/events/6876/ | 2027-03-11 | 2026年劇団☆新感線46周年興行・冬公演 いのうえ歌舞伎 『髑髏城の七人 LAST STAND』 | 未分類 | insufficient_evidence |
| zepp_divercity:https://www.zepp.co.jp/hall/divercity/schedule/single/?rid=163429 | 2027-03-22 | この街を出て、Zepp東名阪。 | 未分類 | insufficient_evidence |
| zepp_haneda:https://www.zepp.co.jp/hall/haneda/schedule/single/?rid=163772 | 2027-03-26 | ナナクロニクル Zepp Haneda 公演 | 未分類 | insufficient_evidence |
| zepp_osaka_bayside:https://www.zepp.co.jp/hall/osakabayside/schedule/single/?rid=162516 | 2027-03-27 | この街を出て、Zepp東名阪。 | 未分類 | insufficient_evidence |

# 保存日程の分類候補（公開未反映）

対象は保存日程1,017レコード。公演数・実開催は意味しない。分類だけを見直し、ID、題名、日付、会場、時刻、原観測・補足は変更しない。

| 分類 | 旧 | 新 |
|---|---:|---:|
| コンサート | 0 | 563 |
| 野球 | 0 | 64 |
| その他 | 0 | 30 |
| 未分類 | 1017 | 360 |

変更 657件。全行の旧→新と最初に一致したルールは [category-diff.csv](category-diff.csv)、集計・分類ごと10件の例は [summary.json](summary.json)。

ルールの出典は公開済み題名のみ。artist_name・説明・会場名を推測で補わない。未分類は根拠不足であり、音楽公演でないという判定ではない。候補は人の抜き取りレビュー後に採用する。

## 抜き取り例（分類ごと先頭10件）

### その他

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-02 | イベント マイナビ就活直前フェア幕張会場 | non_music_keyword:就活 |
| 2026-02-21 | NTTジャパンラグビー リーグワン 2025-26 ディビジョン3 クリタウォーターガッシュ昭島vsマツダスカイアクティブズ広島 | sports_match:ラグビー |
| 2026-02-28 | NTTジャパンラグビー リーグワン 2025-26ディビジョン2 日野レッドドルフィンズvsレッドハリケーンズ大阪 | sports_match:ラグビー |
| 2026-03-01 | NTTジャパンラグビー リーグワン 2025-26 ディビジョン3 クリタウォーターガッシュ昭島vsルリーロ福岡 | sports_match:ラグビー |
| 2026-03-02 | イベント マイナビ就職EXPO幕張会場 | non_music_keyword:就職 |
| 2026-03-04 | イベント 八千代松陰高等学校 第46回 卒業証書授与式 | non_music_keyword:授与式 |
| 2026-03-07 | NTTジャパンラグビー リーグワン 2025-26ディビジョン2 日野レッドドルフィンズvsグリーンロケッツ東葛 | sports_match:ラグビー |
| 2026-03-07 | りそなグループB.LEAGUE 2025-26 SEASON ウエインズトヨタ神奈川 presents 24節 横浜ビー・コルセアーズ vs レバンガ北海道 | sports_match:b.league |
| 2026-03-07 | 朝日新聞 スポーツフェスティバル | non_music_keyword:スポーツフェスティバル |
| 2026-03-08 | そよぎフラクタル 梵そよぎ 1st EXPO『0rigin』 そよぎフラクタル 梵そよぎ 1st EXPO『0rigin』 | non_music_keyword:expo |

### コンサート

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-01 | DEEN LIVE JOY-Break27〜ROCK IN CITY〜 | concert_keyword:live |
| 2026-02-01 | FRUITS ZIPPER SPECIAL LIVE 2026「ENERGY」 | concert_keyword:live |
| 2026-02-01 | SCANDAL TOUR 2026 『SCANDALの対バンツアー』 | concert_keyword:ツアー |
| 2026-02-01 | SUPER BEAVER 20th Anniversary 「都会のラクダ TOUR 2026 〜 ラクダトゥインクルー 〜」 SUPER BEAVER | concert_keyword:tour |
| 2026-02-01 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |
| 2026-02-01 | ジュニア STAR to FESTIVAL 2026 | concert_keyword:festival |
| 2026-02-01 | 高嶋ちさ子 12人のヴァイオリニスト コンサートツアー 2025～2026 | concert_keyword:コンサート |
| 2026-02-02 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |
| 2026-02-02 | 花いろは 7thワンマンライブ「君と咲かせた世界」 | concert_keyword:ライブ |
| 2026-02-03 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |

### 未分類

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-01 | ONE N' ONLY「ドタバタ!? SWAGとひとつ屋根の下で⋯」 | insufficient_evidence |
| 2026-02-01 | RejetFes.2026 Answer | insufficient_evidence |
| 2026-02-01 | 『sound stock Vol.7 × iCON DOLL LOUNGE 2026 【part.1】』 | insufficient_evidence |
| 2026-02-01 | タイマン舞台〜芸人与太郎 せーの！鼻水がダラダラダラ〜 | insufficient_evidence |
| 2026-02-01 | 学びリンク 通信制高校 合同相談会 | insufficient_evidence |
| 2026-02-02 | #らぶこん vol.57-はやて生誕祭 Doll’s Funeral Féte- | insufficient_evidence |
| 2026-02-02 | RIP SLYME / KICK THE CAN CREW RIP SLYME presents BACK to BACK | insufficient_evidence |
| 2026-02-02 | マーキュロ主催『グラン・ギニュルー』Vol.28 | insufficient_evidence |
| 2026-02-03 | RIP SLYME / Creepy Nuts RIP SLYME presents BACK to BACK | insufficient_evidence |
| 2026-02-04 | autechre japan twentytwentysix | insufficient_evidence |

### 野球

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-03-03 | 2026 WBC東京プール presented by ディップ 強化試合 オリックス・バファローズvs韓国 | baseball_team_matchup:オリックス |
| 2026-03-03 | 2026 WBC東京プール presented by ディップ 強化試合 阪神タイガースvs日本 | baseball_team_matchup:阪神 |
| 2026-03-04 | オープン戦 オリックスvs広島 | baseball_keyword:オープン戦 |
| 2026-03-05 | 2026 ワールドベースボールクラシック™ 東京プール presented by ディップ | baseball_keyword:ベースボール |
| 2026-03-06 | 2026 ワールドベースボールクラシック™ 東京プール presented by ディップ | baseball_keyword:ベースボール |
| 2026-03-06 | オープン戦 オリックスvs巨人 | baseball_keyword:オープン戦 |
| 2026-03-07 | 2026 ワールドベースボールクラシック™ 東京プール presented by ディップ | baseball_keyword:ベースボール |
| 2026-03-07 | オープン戦 オリックスvs巨人 | baseball_keyword:オープン戦 |
| 2026-03-08 | 2026 ワールドベースボールクラシック™ 東京プール presented by ディップ | baseball_keyword:ベースボール |
| 2026-03-08 | オープン戦 オリックスvsソフトバンク | baseball_keyword:オープン戦 |

## 入力と再現

入力は `data/public_schedule_days.json`（SHA d926a67b855720dfd7ccbb165f1e2caeeb813c632f62cc44a41b2a4764d13303）。baseline・原観測provenance・元台帳のSHAは不変。出力候補は `public_schedule_days.preview.json`、SHA e92a63a38eb3d4a3e1344752214e72add2a8cd7e244f1180fea42d82de56495b。元のprivate観測を再取得・再構築したとは扱わない。分類は新しい共通ルールから導いた公開上の派生値で、ルール自体のSHAもsummaryに残す。

```sh
uv run python -m scripts.prepare_schedule_categories \
  --source-dir data \
  --expected-public-sha256 d926a67b855720dfd7ccbb165f1e2caeeb813c632f62cc44a41b2a4764d13303 \
  --output-root /private/tmp/new-schedule-category-review
```

出力はGit外の新規directoryだけ。既存出力・入力を上書きしない。新規の保存日程は `build_archival_schedule_days` でも同じ関数を使う。通常取得・アーティスト推定・Streamlitの画面も共通関数を使う。既存DBや公開資産をこのPRで再分類しない。

## 本番への順番と承認

1. 両repoのコード・候補差分をレビュー。分類変更の対象は本件の保存日程だけとし、未分類360件の推定補完は行わない。
2. ユーザー承認後、上流の候補を `data/public_schedule_days.json` に採用する別のデータ変更を作り、検証・マージする。このPRはそのデータを変更しない。
3. 上流で更新済みのpublic packageとbaselineを含むRelease/manifestを配布する（Release・dispatchの承認が必要）。古いprivate資産のprojectionを直接再exportすると固定未分類版に戻るため、本件のreviewed category producerを経由した候補を採用する。元private観測のSHAは変えず、新しいpublic SHAで区別する。
4. SideBiz側は実Releaseのサイズ/SHAとpreviewの一致を検査し、新しいpinsで再採用候補を再検証する。通常のsourceが進んだ場合は最新snapshotから候補とrequestを作り直し、再レビューする。
5. 公開差し替えの承認後にSideBizのconfig更新と明示readoptionを行う。通常runの保持検査を緩めない。

現状はreview候補のみ。mainマージ、Release更新、dispatch、本番差し替えは未実施。

## ルール変更の範囲

根拠不足のfallbackだけを「その他」から「未分類」にする。明示的な野球語・チーム対戦、音楽語・既知artist、非音楽語の従来の分類は回帰試験で維持する。例外として、J2/B.LEAGUEなどの試合表示をartist_nameの有無より先に「その他」とし、「都市対抗野球大会」の「対」を対戦判定してしまう順序を直して「野球」にする。Streamlitの二重定義を削除し共通関数と「未分類」のフィルターを使う。これは意図したR07の変更で、既存DB/配布JSONの一括書換えではない。

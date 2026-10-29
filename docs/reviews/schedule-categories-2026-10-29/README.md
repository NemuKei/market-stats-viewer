# 保存日程の分類候補（レビュー用・公開未反映）

対象は保存日程1,017レコード。公演数・実開催は意味しない。分類だけを見直し、ID、題名、日付、会場、時刻、原観測・補足は変更しない。

| 分類 | 公開中 | 前回候補（22fb22a） | 今回候補 |
|---|---:|---:|---:|
| コンサート | 0 | 538 | 552 |
| 野球 | 0 | 62 | 62 |
| その他 | 0 | 51 | 51 |
| 未分類 | 1017 | 366 | 352 |

公開中から665行の分類が変わる。前回候補からは未分類→コンサート14行のみ。全1,017行の旧公開→今回と理由は [category-diff.csv](category-diff.csv)、各分類10例は [summary.json](summary.json)。前回との全差分、戻した音楽全例と残る除外全行は [music-recovery.json](music-recovery.json)／[一覧](music-recovery.md)。

## 今回の音楽語と安全側の判定

「単独公演」「音楽フェス」「ミュージック」「軽音」「吹奏楽」、単語としてのgig/band、語境界を検査したmusic fes/music festival、music & entertainment festival、k-pop festivalを追加した。festival直後の開催年は許す。gigantic/bandwidthや会場名だけでは当てない。追加語が漫才・演劇・ミュージカル等と衝突する場合も未分類。既存の音楽語と非音楽語・スポーツの衝突、EXPO・党大会・卒業式の保留と誤判定9行の試験は維持する。

Music Splash、SBI MUSIC CIRCUS、Music Juiceなどは、単なるmusic単語だけの推測を避けて未分類のまま。アーティスト名だけの題名も推測で補完しない。今回の件数は目標値ではなく実測。

## 分類ごと10例

### その他

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-02 | イベント マイナビ就活直前フェア幕張会場 | non_music_keyword:就活 |
| 2026-02-07 | ＦＣ東京×鹿島アントラーズ | sports_match:fc東京 |
| 2026-02-08 | 東京ヴェルディ×水戸ホーリーホック | sports_match:東京ヴェルディ |
| 2026-02-14 | ＦＣ東京×浦和レッズ | sports_match:fc東京 |
| 2026-02-21 | NTTジャパンラグビー リーグワン 2025-26 ディビジョン3 クリタウォーターガッシュ昭島vsマツダスカイアクティブズ広島 | sports_match:ラグビー |
| 2026-02-21 | 東京ヴェルディ×FC町田ゼルビア | sports_match:東京ヴェルディ |
| 2026-02-28 | NTTジャパンラグビー リーグワン 2025-26ディビジョン2 日野レッドドルフィンズvsレッドハリケーンズ大阪 | sports_match:ラグビー |
| 2026-02-28 | ＦＣ東京×柏レイソル | sports_match:fc東京 |
| 2026-03-01 | NTTジャパンラグビー リーグワン 2025-26 ディビジョン3 クリタウォーターガッシュ昭島vsルリーロ福岡 | sports_match:ラグビー |
| 2026-03-04 | イベント 八千代松陰高等学校 第46回 卒業証書授与式 | non_music_keyword:授与式 |

### コンサート

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-01 | DEEN LIVE JOY-Break27〜ROCK IN CITY〜 | concert_keyword:live |
| 2026-02-01 | FRUITS ZIPPER SPECIAL LIVE 2026「ENERGY」 | concert_keyword:live |
| 2026-02-01 | SCANDAL TOUR 2026 『SCANDALの対バンツアー』 | concert_keyword:ツアー |
| 2026-02-01 | SUPER BEAVER 20th Anniversary 「都会のラクダ TOUR 2026 〜 ラクダトゥインクルー 〜」 SUPER BEAVER | concert_keyword:tour |
| 2026-02-01 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |
| 2026-02-01 | 高嶋ちさ子 12人のヴァイオリニスト コンサートツアー 2025～2026 | concert_keyword:コンサート |
| 2026-02-02 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |
| 2026-02-02 | 花いろは 7thワンマンライブ「君と咲かせた世界」 | concert_keyword:ライブ |
| 2026-02-03 | なにわ男子 1st DOME LIVE ‘VoyAGE’ | concert_keyword:live |
| 2026-02-04 | CUTIE STREET OFFICIAL FAN CLUB TOUR 2026 WINTER きゅーてすとのつどい | concert_keyword:tour |

### 未分類

| 日付 | 題名 | 判定根拠 |
|---|---|---|
| 2026-02-01 | ONE N' ONLY「ドタバタ!? SWAGとひとつ屋根の下で⋯」 | insufficient_evidence |
| 2026-02-01 | RejetFes.2026 Answer | insufficient_evidence |
| 2026-02-01 | 『sound stock Vol.7 × iCON DOLL LOUNGE 2026 【part.1】』 | insufficient_evidence |
| 2026-02-01 | ジュニア STAR to FESTIVAL 2026 | insufficient_evidence |
| 2026-02-01 | タイマン舞台〜芸人与太郎 せーの！鼻水がダラダラダラ〜 | insufficient_evidence |
| 2026-02-01 | 学びリンク 通信制高校 合同相談会 | insufficient_evidence |
| 2026-02-02 | #らぶこん vol.57-はやて生誕祭 Doll’s Funeral Féte- | insufficient_evidence |
| 2026-02-02 | RIP SLYME / KICK THE CAN CREW RIP SLYME presents BACK to BACK | insufficient_evidence |
| 2026-02-02 | マーキュロ主催『グラン・ギニュルー』Vol.28 | insufficient_evidence |
| 2026-02-03 | RIP SLYME / Creepy Nuts RIP SLYME presents BACK to BACK | insufficient_evidence |

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

## DB全2,196行への影響

DBをread-onlyで読み、保存済み分類→今回の予測を比較した。元DBのbytes SHAも前後で一致。全差分は [db-impact.json](db-impact.json)。

| 保存済み→今回 | 件数 |
|---|---:|
| その他 -> 未分類 | 396 |
| その他 -> コンサート | 25 |
| コンサート -> 未分類 | 69 |
| コンサート -> その他 | 3 |
| 野球 -> その他 | 2 |
| その他 -> 野球 | 7 |

合計502行が変化。前回予測からは未分類→コンサート9行のみ。保存済みコンサートからの変更は72行（未分類69・その他3）。前回の80行から8行をコンサートへ戻し、さらに保存済みその他の1行をコンサートへ戻した。前回から新たに音楽を外す行は0。残る72行は music-recovery資料へ全件掲載。

2026-10-29の質問UIで「修正を優先し、80行も差分で確認」を選択した方針を維持する。今回は取りこぼし改善だけを追加し、DBの書換えはしない。

## 入力と再現

入力は `data/public_schedule_days.json`（SHA `d926a67b855720dfd7ccbb165f1e2caeeb813c632f62cc44a41b2a4764d13303`）。baseline・観測provenance・元台帳SHAは不変。出力候補は `public_schedule_days.preview.json`（SHA `9d3eb7a4d9c648d09068846b04414a9f1a79cbe800ce3320a4d2b09714ff44e4`）。分類は公開済み題名からの派生値で、private原本を再構築したとは扱わない。ルールSHAはsummaryに記録。

```sh
uv run python -m scripts.prepare_schedule_categories \
  --source-dir data \
  --expected-public-sha256 d926a67b855720dfd7ccbb165f1e2caeeb813c632f62cc44a41b2a4764d13303 \
  --output-root /private/tmp/new-schedule-category-review
uv run python -m scripts.audit_event_category_impact \
  --database data/events.sqlite --output /private/tmp/db-impact.json
```

出力はGit外の新規directory。DBはmode=roで読み、実行前後のbytes SHAも照合する。通常取得・保存日程・Streamlitが同じ分類関数を使う。

## 本番への順番と承認

1. 両repoのコード・全差分をレビューし、マージ承認を得る。本件は候補の準備のみで、データ採用・設定変更・Release配布の承認を含まない。
2. ユーザー承認後、SideBizを一時停止する。上流の配布workflowもメンテナンス中は一時停止し、既に実行中の配布が終わったか承認範囲でcancelしたことを確認する（停止/再開も承認が必要）。
   正式なworkflow名は **Publish external events assets**、ファイルは `.github/workflows/publish_external_events_assets.yml`。以下は承認後に使うコマンド例で、今回実行していない。

   ```sh
   gh workflow disable publish_external_events_assets.yml --repo NemuKei/market-stats-viewer
   gh run list --workflow publish_external_events_assets.yml --repo NemuKei/market-stats-viewer --limit 10
   ```

   disableは実行中runを止めない。開始済みrunが完了したことを確認するか、個別承認したrunだけを `gh run cancel RUN_ID --repo NemuKei/market-stats-viewer` で止める。データと変数を揃えて検証した後の再開は次のとおり。再開とRelease配布も個別承認の範囲で行う。

   ```sh
   gh workflow enable publish_external_events_assets.yml --repo NemuKei/market-stats-viewer
   ```

   enableだけでは配布は実行されない。承認済みの配布実行または次の正常更新後に、実Releaseとmanifestの新SHAを確認する。workflow dispatchにも別途承認が必要。

3. **候補データの採用と次のrepository variables 3点の更新を、配布を停止した1つのメンテナンス操作として実施する。** データだけ先に切り替えて配布しない。変数変更はrepo設定の変更なので、Keiichiさんの明示承認が必要。このPRでは実行しない。
   - PUBLIC_SCHEDULE_DAYS_SHA256: 採用するpublic_schedule_days.jsonのbytes SHA-256
   - PUBLIC_SCHEDULE_BASELINE_SHA256: 不変のpublic_schedule_baseline.jsonのbytes SHA-256
   - PUBLIC_SCHEDULE_APPROVAL_SHA256: 採用するday ID集合（sorted/unique）のcanonical JSON SHA-256
4. 下の計算とpackage検査でファイル・3変数が一致することを確認し、承認範囲で上流の配布workflowを再開して新package+manifestをReleaseへ配布する。古いprivate資産を直接再exportせず、レビュー済み分類派生producerの候補を採用する。
5. SideBizは実Releaseのサイズ/SHAを検証し、最新runtimeからcandidate/requestを作り直してレビューする。公開差し替えの承認後、新config・承認済みrequestをmainに揃える。**PUBLICATION_PAUSED=trueのまま**再採用入力4点付き手動runを実行する。通常の定時/手動runは停止を維持する。
6. 再採用runでは市場統計JSON・鮮度表示・静的ページも更新して公開するため、その同時更新も承認と確認の対象に含める。新head・本番JSON・過去フィルターを確認し、再開承認後にSideBizの一時停止を解除する。失敗時は旧package/3変数と旧pins/runtimeの組を停止中に復旧する。

### 設定値の計算（読み取りのみ）

候補を採用する時点の実ファイルで再計算する。以下はレビュー候補と既存baselineでの例。出力値を設定に反映する操作は別途承認後。

```sh
python - <<'PYCODE'
import hashlib, json
from pathlib import Path
public = Path("docs/reviews/schedule-categories-2026-10-29/public_schedule_days.preview.json")
baseline = Path("data/public_schedule_baseline.json")
payload = json.loads(public.read_bytes())
uids = sorted({row["event_uid"] for row in payload["events"]})
approval = hashlib.sha256(json.dumps(uids, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
assert approval == payload["provenance"]["approval_set_sha256"]
print("PUBLIC_SCHEDULE_DAYS_SHA256=" + hashlib.sha256(public.read_bytes()).hexdigest())
print("PUBLIC_SCHEDULE_BASELINE_SHA256=" + hashlib.sha256(baseline.read_bytes()).hexdigest())
print("PUBLIC_SCHEDULE_APPROVAL_SHA256=" + approval)
PYCODE
```

配布を再開する前にdata・変数の両方を揃える。Git commitとGitHub variablesは原子的に更新できないため、配布停止で中間状態を外へ出さない。この準備ではmainマージ、dispatch、Release・repo設定・公開データの変更をしていない。


## 前回との差分資料の再生成

前回はcommit `22fb22a` の `public_schedule_days.preview.json` と `db-impact.json`。それらをGit外のprevious-reviewへ取り出し、今回のreview directoryと比較する。`scripts.compare_category_reviews` は元DBのSHA・件数と保存日程のcategory以外の不変を確認し、戻った音楽・外れる音楽を全行列挙する。

```sh
uv run python -m scripts.compare_category_reviews \
  --previous-review /private/review/previous-review \
  --current-review docs/reviews/schedule-categories-2026-10-29 \
  --output /private/review/music-recovery.json
```

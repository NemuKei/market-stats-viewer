# 保存日程の個別分類候補（レビュー用）

2026-11-05時点の公開保存日程1,017行を対象に、公式の会場・アーティスト・主催者の本文で日付、会場、公演内容を照合した33行を「未分類」から「コンサート」へ訂正する候補。対象は大阪城ホールを含む14会場。[reviewed-corrections.json](reviewed-corrections.json) に全行のID、保存題名、日付、会場、旧・新分類、根拠URLと確認日を記録した。対象以外は変更しない。

| 分類 | 入力 | 候補 |
| --- | ---: | ---: |
| コンサート | 552 | 585 |
| 未分類 | 352 | 319 |
| その他 | 51 | 51 |
| 野球 | 62 | 62 |

これは会場・日付ごとの**保存日程**の種類を示す候補であり、実際の開催状況、公演回数、来場者数を追加で保証しない。artist_name、ID、日付、時刻、会場、原観測・provenance、baselineは変更しない。残る319行をすべて誤分類とみなさない。

## 保留した例

- 大阪城ホールのMr.Children 2026-05-30・31は、[主催者](https://kyodo-osaka.co.jp/news/detail/767)が30日の公演中断と31日の中止を公表しているため、この分類候補には含めていない。[振替公演の案内](https://kyodo-osaka.co.jp/search/detail/13408)もある。現在の保存日程が開催済みと受け取られないかは別途検討が必要。
- GMOアリーナさいたまの `LOVE JAZZ TIME 2026` 2026-04-18は、[会場公式](https://www.saitama-arena.co.jp/schedule/love-jazz-time-2026-2/)の開催場所が「けやきひろば」で、保存行の会場表示と異なる。音楽イベントであっても会場照合が必要なため保留する。
- プロレス、演劇、式典、証拠が足りない日程も一括では変えない。

## 候補の再現

入力 `data/public_schedule_days.json` のSHA-256は `9d3eb7a4d9c648d09068846b04414a9f1a79cbe800ce3320a4d2b09714ff44e4`。入力または行のID・題名・日付・会場・旧分類が異なる場合、処理は失敗する。重複ID、未登録ID、不完全な根拠も拒否する。公式本文の内容の真偽をプログラムが自動検証するわけではなく、目録とリンクの人による確認が必要。

```sh
uv run python -m scripts.prepare_schedule_categories \
  --source-dir data \
  --expected-public-sha256 9d3eb7a4d9c648d09068846b04414a9f1a79cbe800ce3320a4d2b09714ff44e4 \
  --reviewed-corrections docs/reviews/schedule-corrections-2026-11-05/reviewed-corrections.json \
  --output-root /path/outside/git/new-review-directory
```

出力は新規ディレクトリに限り、公開はしない。`public_schedule_days.json`、不変の `public_schedule_baseline.json`、目録のコピー、全IDの前後と理由を示す `category-diff.csv`、ハッシュ・件数を記録した `category-summary.json` を生成する。今回の候補SHA-256は `3118b39bc14dd4553d792246787e744159d5e60733c7a82a35716c64695970fe`、目録SHA-256は `5cb71211534f59442472a1e76e83f4ad13c67aec55a44fea09fe21dfbcc500f1`。

この目録は上記入力だけに結び付く。新しい公開資産を基準にする場合は最新の資産・ID・旧分類・公式情報・中止等を再確認し、新しい目録を作る。目録なしの従来モードは題名から全件を再計算するため、個別訂正を保持する目的でそのまま再実行しない。

## 通常行と採用時の注意

共通分類器は「フェアリーランド」「フェアウェイ」のような長いカタカナ語の一部を展示の「フェア」と誤認しない。展示フェアや音楽と展示・スポーツの衝突は従来どおり保守的に判定する。通常行のALI PROJECTは、出演者・他項目を変えずに次の分類同期で「その他」から「コンサート」になる。共通分類器は通常の公式イベント取得とStreamlitからも使われるため、コード採用が公開DBや表示に及ぶ時点を別途確認する。

保存日程は下流の通常更新では上書きできない。最新の実Release・manifest・runtime・履歴・policyを照合し、既存の正式な再採用手順で新しい候補とrequestを準備する。分類のみの再採用候補は通常行の同時変更を拒否するため、通常行の更新と保存日程の再採用は順序を調整し、後に実施する側は最新runtimeを基準に作り直す。配布停止・再開、上流データと3つのpin変更、Release配布、下流の正式再採用と本番反映は別々に承認・検証する。[従来の詳細手順](../schedule-categories-2026-10-29/README.md)も参照。保留中の候補を採用済みと扱わない。

# PROJECT_CONTEXT（market-stats-viewer）

最終更新: 2026-06-25

## Always Read Block

- このrepoの目的は、市場統計と大型イベント情報を、外部LPや需要判断に使える配布データとして安定提供すること。
- イベント情報の本質ゴールは、検知した大型イベントがLPのイベント一覧に自然に載ること。DB更新はそのための手段である。
- LP向けイベント表示は、重複統合済みの `data/lp_events.json` をデータ側で生成し、LP側は原則としてその一覧を読むだけにする。
- 同一イベントの表示source優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music > ticketjam_events` とする。
- Web検知でDB/LP掲載してよい根拠は、公式/準公式ページ本文に限る。検索結果、AI概要、一般ニュース、SNS単体、二次流通単体はDB更新根拠にしない。
- 本文抽出は `requests_bs4` を既定とし、`crawl4ai` はJS生成ページや複雑HTML向けのoptional fallback providerとして扱う。providerの出力そのものではなく、取得できた公式/準公式URLと本文根拠を採用根拠にする。
- 自動化方針は、人間が毎回候補を読む運用ではなく、Codex Automation が根拠、分類、変更、verify、LP影響を出して、DB/LP出力更新まで進めること。
- ローカル絶対パス、個人ログイン状態、ブラウザ履歴、端末固有キャッシュには依存しない。別端末でもrepo内のdocs、Skill、設定、検証コマンドで再現できることを優先する。

## Purpose

この文書は、複数の仕様判断、運用判断、automation 判断で再利用する上位文脈と判断原則を記録する。

個別仕様、テーブル、列、workflow 条件、コマンドは `docs/spec_*.md` に置く。日付付きで確定した個別判断は `docs/context/DECISIONS.md` に置く。次スレッドの再開地点と現在の作業順は `docs/context/STATUS.md` に置く。

## Source-of-Truth Routing

- `docs/context/PROJECT_CONTEXT.md`: 目的、成功条件、非目標、source-of-truth routing、判断原則、LP掲載優先を置く。
- `docs/context/DECISIONS.md`: 日付付きで確定した個別判断を置く。
- `docs/context/STATUS.md`: 次スレッドが最初に読む現在地を置く。
- `docs/spec_*.md`: 実装仕様、入出力契約、禁止条件、verify 条件を置く。
- `AGENTS.md`: repo-wide の運用ルール、Codex の読み順、Skill 利用、Git同期、repo固有の常時ルールを置く。

## Success Conditions

- `events.sqlite`、`event_signals.sqlite`、`lp_events.json`、`manifest.json`、Release asset の関係が明確である。
- LP表示用には `lp_events.json` が、同一イベントを `event_date + canonical venue_name + canonical artist_name` で統合し、最上位sourceを `display_source_id` として選ぶ。
- 下位sourceは削除せず、`supporting_sources` として根拠確認や監査に使える。
- Codex Automation は、公式/準公式根拠を確認した候補だけを `venue_web_discovery` として保存し、DB更新、LP出力再生成、manifest検証まで実行できる。
- source priority、DB schema、Release asset契約を変える場合は、docs/spec/DECISIONS とテストを同じ変更内で同期する。

## Judgment Principles

### Automation First

人間が毎回候補を読む運用ではなく、automation が根拠、分類、変更案、verify 結果、LP影響を出力し、人間確認は automation が安全に判断できない候補に限定する。

automation を進めるときは、処理対象、入力データ、分類条件、変更対象ファイル、verify コマンド、禁止変更、失敗時の出力を仕様または運用手順に明記する。人間確認を減らすために、確認作業を会話へ移すのではなく、automation の出力形式と gate 条件へ移す。

### Evidence Before Auto-Apply

自動反映は、候補分類だけではなく、反映根拠と verify 結果が揃っている場合に限る。

自動反映に必要な情報:

- どのデータを入力として使ったか
- どの候補を変更対象にしたか
- 変更対象外にした候補と理由
- どのファイルまたはDB行が変わったか
- LP側の表示件数、カテゴリ、集計値、同一イベントのまとまり、データ鮮度、配布 manifest への影響
- 実行した verify と結果

### Public Data Source Preference

市場統計とイベント情報では、公的公開統計または会場公式/準公式が確認できる公開スケジュールを優先する。

イベント情報を比較するときは、`events.sqlite` の会場公式日程、`event_signals.sqlite` の公式/準公式Web検知、ニュース速報、二次流通参考を同じ種類のデータとして扱わない。統合や重複判断では、`event_date + canonical venue_name + canonical artist_name` を基本の比較キーとする。

### Consumer Impact Is Part Of The Change

市場統計またはイベント情報に関わる変更では、repo内の表示だけでなく、LP側で利用するデータへの影響を確認する。

確認対象:

- `data/market_stats.sqlite`
- `data/events.sqlite`
- `data/event_signals.sqlite`
- `data/lp_events.json`
- `data/manifest.json`
- GitHub Release asset
- 関連 workflow
- 表示用のカテゴリ、期間、集計、正規化ロジック

影響がない場合も、`lp_impact=none` 相当の理由を残す。影響がある場合は、表示件数、カテゴリ、集計値、同一イベントのまとまり、データ鮮度、配布 manifest のどれが変わるかを分けて説明する。

## Non-Goals

- `PROJECT_CONTEXT.md` にタスク一覧や完了履歴を書かない。
- 個別仕様の入出力契約を `PROJECT_CONTEXT.md` に移さない。
- Google API固定やGoogle SERPスクレイピングを本番取得方式として採用しない。
- 検索結果、AI概要、一般ニュース、SNS単体、二次流通単体をDB更新根拠にしない。
- `venue_web_discovery` の実績評価前に、STARTO/Kstyle/Ticketjam を即廃止しない。
- automation が失敗した変更を、同じ処理内で根拠なく隠して修正しない。

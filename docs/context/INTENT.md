# INTENT（market-stats-viewer）

最終更新: 2026-05-21

## Purpose

この文書は、複数の仕様判断、運用判断、automation 判断で再利用する判断原則を記録する。

`INTENT.md` は、個別仕様、日付付き決定、進捗、タスク一覧の置き場ではない。実装に必要な具体的な入出力、テーブル、列、画面、コマンド、workflow 条件は `docs/spec_*.md` に置く。日付付きで確定した個別判断は `docs/context/DECISIONS.md` に置く。次スレッドの再開地点と現在の作業順は `docs/context/STATUS.md` に置く。

## Document Roles

- `docs/context/INTENT.md`: 判断原則を置く。対象は、今後 2 回以上使う見込みがあり、2 つ以上の仕様論点または運用論点にまたがる比較軸である。
- `docs/context/DECISIONS.md`: 日付付きで確定した個別判断を置く。個別の source 移行、workflow 変更、自動マージ条件の変更はここに記録する。
- `docs/context/STATUS.md`: 次スレッドが最初に読む現在地を置く。完了履歴、Doing、Next、未処理タスク、最新 verify 状態を扱う。
- `docs/spec_*.md`: 実装仕様を置く。データ契約、更新処理、画面仕様、automation の入出力契約、禁止条件、verify 条件を扱う。
- `AGENTS.md`: repo-wide の運用ルールを置く。Codex の読み順、Skill 利用、Git 同期、ブラウザ確認、repo 固有の常時ルールを扱う。

## Judgment Principles

### Automation First

この repo では、人間が毎回候補を読む運用ではなく、automation が根拠、分類、変更案、verify 結果、LP 影響を出力し、人間確認は automation が安全に判断できない候補に限定する方向を優先する。

automation を進めるときは、処理対象、入力データ、分類条件、変更対象ファイル、verify コマンド、禁止変更、失敗時の出力を仕様または運用手順に明記する。人間確認を減らすために、確認作業を会話へ移すのではなく、automation の出力形式と gate 条件へ移す。

比較する対象:

- 毎回人間が記事、候補、差分を読む運用
- automation が候補を分類し、許可条件を満たすものだけを反映し、残りを理由付きで人間確認へ回す運用

優先する対象:

- automation が根拠と verify 結果を出力できる場合は、automation による分類、反映、post-merge audit を優先する。
- source 優先順位変更、DB schema 変更、ID 変更、LP 表示契約変更、Release asset 更新条件変更のように、失敗時の影響が広い変更は、人間確認または別 task 化を優先する。

### Evidence Before Auto-Apply

自動反映は、候補分類だけではなく、反映根拠と verify 結果が揃っている場合に限る。

自動反映に必要な情報:

- どのデータを入力として使ったか
- どの候補を変更対象にしたか
- 変更対象外にした候補と理由
- どのファイルまたはDB行が変わったか
- LP 側の表示件数、カテゴリ、集計値、同一イベントのまとまり、データ鮮度、配布 manifest への影響
- 実行した verify と結果
- post-merge audit の結果、または post-merge audit を実行しない理由

### Public Data Source Preference

市場統計とイベント情報では、公的公開統計または会場公式が確認できる公開スケジュールを優先する。

イベント情報を比較するときは、`events.sqlite` の会場公式日程、`event_signals.sqlite` のニュース速報、`ticketjam_events` の二次流通参考を同じ種類のデータとして扱わない。統合や重複判断では、`event_date + canonical venue_name + canonical artist_name` を基本の比較キーとし、同一日程がある場合は会場公式日程を優先する。

### Consumer Impact Is Part Of The Change

市場統計またはイベント情報に関わる変更では、repo 内の表示だけでなく、LP 側で利用するデータへの影響を確認する。

確認対象:

- `data/market_stats.sqlite`
- `data/events.sqlite`
- `data/event_signals.sqlite`
- `data/manifest.json`
- GitHub Release asset
- 関連 workflow
- 表示用のカテゴリ、期間、集計、正規化ロジック

影響がない場合も、`lp_impact=none` 相当の理由を残す。影響がある場合は、表示件数、カテゴリ、集計値、同一イベントのまとまり、データ鮮度、配布 manifest のどれが変わるかを分けて説明する。

### Separate Judgment Principles From Decisions

`INTENT.md` は、日付付き決定を置く場所ではない。

例:

- 「人間確認を減らし、automation の gate と verify に寄せる」は判断原則なので `INTENT.md` に置く。
- 「2026-05-21 以降、イベント情報監査automationは低リスク候補を自動マージし、直後に Post-merge Audit を実行する」は個別決定なので `DECISIONS.md` に置く。
- 「K-Style の `backfill_article_urls` に確認済みURLを追加できる」は実装仕様と個別決定なので `docs/spec_update_pipeline.md` と `DECISIONS.md` に置く。

## Non-Goals

- `INTENT.md` にタスク一覧を書かない。
- `INTENT.md` に完了履歴を書かない。
- `INTENT.md` に個別仕様の入出力契約を移さない。
- `INTENT.md` を、人間確認なしで何でも自動変更できる許可文書として使わない。
- automation が失敗した変更を、同じ処理内で根拠なく隠して修正しない。失敗理由、影響範囲、次の修正対象を出力する。

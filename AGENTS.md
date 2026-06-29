# AGENTS.md

## Purpose

このファイルは `market-stats-viewer`（MSV）の作業入口である。
方針は **AGENTS-first, not AGENTS-only**。最初にここで読み順と安全境界を確認し、必要になった範囲だけ `PROJECT_CONTEXT`、`STATUS`、`DECISIONS`、`spec`、README を読む。

MSV の目的は、市場統計と大型イベント情報を、外部LPや需要判断に使える配布データとして安定提供すること。DB更新、JSON生成、Release asset、automation はこの目的のための手段であり、単独の成果ではない。

## Scope And Profile

- Profile: `AGENTS-first + retained optional PROJECT_CONTEXT`。
- `docs/context/PROJECT_CONTEXT.md` は deprecated ではなく、任意の upper premise layer として残す。目的、背景意図、判断原則、非目的、LP掲載優先の確認が必要なときに読む。
- `PROJECT_CONTEXT.md` は毎回の必読全文ではない。目的、source priority、LP影響、automation判断、仕様判断、docs governance に触れるときは `Always Read Block` を読む。
- SideBiz_HotelRM、公開LP反映、Cloudflare/Vite build、SideBiz側JSON取り込みはこのrepoの直接作業範囲ではない。必要な場合も別repo作業として明示する。

## Read Order

1. `AGENTS.md` を最初に読む。
2. 目的、source priority、LP影響、automation判断、仕様判断、docs governance に触れる場合だけ `docs/context/PROJECT_CONTEXT.md` の `Always Read Block` を読む。必要時だけ全文を読む。
3. 現在地、再開地点、backlog は `docs/context/STATUS.md` を読む。
4. 日付付きの固定判断や superseded 判断は `docs/context/DECISIONS.md` を読む。
5. 外部契約、データ契約、pipeline、UI挙動は該当する `docs/spec_*.md` を読む。
6. 実行手順、利用者向け概要、公開URLは `README.md` を読む。
7. `docs/handovers/**`、`docs/thread_logs/**`、archive 相当は参照専用。新規ルールを置かない。

読み広げる前に、何を確認するために読むのかを短く固定する。

## Source-Of-Truth Routing

- `AGENTS.md`: 作業入口、読み順、常時安全境界、Git/verify の最小ルール。
- `docs/context/PROJECT_CONTEXT.md`: MSV の upper premise。目的、成功条件、判断原則、非目的、source-of-truth routing、LP掲載優先。
- `docs/spec_data.md`: `events.sqlite`、`event_signals.sqlite`、`lp_events.json`、`manifest.json`、外部アプリ向けデータ契約、source priority の詳細契約。
- `docs/spec_update_pipeline.md`: update scripts、workflow、provider、command、Release asset publish、automation 実行条件の詳細契約。
- `docs/event_signal_audit_automation.md`: イベント監査automationの入力、許可変更、禁止変更、evidence、verification、post-merge audit。
- `docs/context/DECISIONS.md`: 日付付きで確定した判断。古い判断は削除せず superseded として残す。
- `docs/context/STATUS.md`: 現在の re-entry、active/next、未解決リスク。完了履歴は補助情報。

具体的な spec または日付付き decision が `PROJECT_CONTEXT` の一般原則と矛盾する場合は、具体的な spec / decision を優先する。未解決のまま外部挙動へ影響する場合は、推測で進めず `DECISIONS` へ暫定記録するか利用者へ確認する。

## MSV Domain Rules

- データ取得元は公的公開統計、会場公式、公式/準公式ページ本文を優先する。
- LP向けイベント一覧は、重複統合済みの `data/lp_events.json` をデータ側で生成し、LP側は原則としてその一覧を読むだけにする。
- 同一イベントの表示source優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music > ticketjam_events`。この判断原則は `PROJECT_CONTEXT` に置き、詳細契約は `docs/spec_data.md` に置く。
- Web検知でDB/LP掲載してよい根拠は、公式/準公式ページ本文に限る。検索結果、AI概要、一般ニュース、SNS単体、二次流通単体はDB更新根拠にしない。
- provider名、コマンド、workflow、fallback 条件などの実装詳細は `docs/spec_update_pipeline.md` に置く。`PROJECT_CONTEXT` へ詳細手順を増やさない。
- 市場統計またはイベント情報に関わる変更では、LP側で利用するデータへの影響を必ず確認する。対象は `data/market_stats.sqlite`、`data/events.sqlite`、`data/event_signals.sqlite`、`data/lp_events.json`、`data/manifest.json`、Release asset、関連workflow、表示用のカテゴリ・期間・集計・正規化ロジック。
- 影響がない場合も `lp_impact=none` 相当の理由を残す。影響がある場合は、表示件数、カテゴリ、同一イベントのまとまり、データ鮮度、配布 manifest、source priority のどれが変わるかを分けて説明する。
- source priority、DB schema、Release asset契約、LP表示契約を変える場合は、同一変更内で `docs/spec_*.md`、`docs/context/DECISIONS.md`、必要な tests/verify を同期する。

## Docs Governance

- 会話内容だけを正本にしない。正本化する場合は対象ファイルを更新する。
- 同じルールを複数文書へ重複展開しない。重複が必要に見える場合は、1箇所を正本にし、他は短い参照にする。
- `PROJECT_CONTEXT.md` にタスク一覧、完了履歴、コマンド詳細、provider詳細、個別入出力契約を入れない。
- `STATUS.md` は先頭で current / re-entry / unresolved risk が短く読める状態を保つ。古い完了履歴を毎回読む前提にしない。
- `DECISIONS.md` は durable decision だけを追加する。短期メモ、実行ログ、単なる作業結果は `STATUS.md` か該当 spec に置く。
- `spec` 更新要否は、外部挙動、入出力契約、用語、受け入れ条件、非機能要件が変わるかで判定する。

## Skills And Agents

- repo固有Skillは `.agents/skills/` に置く。共有Skillは `~/.codex/skills` から使い、このrepoへ複製しない。
- docs配置、重複整理、正本化判断では `docs-governance` を使う。
- spec影響があるか不明な場合は `spec-governance` を使う。
- 完了、修正済み、通過済み、push済みを主張する前に `verification-before-completion` を使い、fresh evidence を取る。
- subagent は read-heavy な調査、レビュー、要約に限定して使う。write-heavy、shared/high-conflict files、final verify、commit/push 判断はメインスレッド側が保持する。

## Safety Boundaries

- 明示承認なしで行わない: `data/**` 更新、SQLite/JSON生成物更新、workflow dispatch、Release publish、live hook/config apply、DB schema変更、依存追加/更新、認証/secret/権限変更、SideBiz反映。
- 秘密情報、Cookie、token、個人情報、raw log 全文、端末固有cacheを repo 管理対象へ入れない。
- `.chatgpt/` はツール実行履歴や一時メタ情報として扱い、repo 管理対象にしない。
- `docs/ai/` に後続連携用の資産を置く場合も、secret/PII/raw log/巨大一時出力がないことを確認し、現在taskに関係するファイルだけを stage する。

## Verification And Git

- 変更は依頼範囲に対して必要最小限に保つ。無関係な refactor、整形、削除、rename を混ぜない。
- docs-only の最小verifyは、`git diff --check`、対象語句の `rg`、BOM確認、secret/credential/PII marker の簡易scan、`git status --short --branch`。
- コード、data、workflow、Release asset、LP表示契約に触れた場合は、該当 spec/README の focused tests、build、生成確認を追加する。
- verify が失敗した状態では通常の commit/push をしない。失敗内容、未解決点、次に見る箇所を報告する。
- stage するのは現在taskに関係する tracked files だけ。ユーザー由来や無関係の差分を戻さない、stageしない。
- 意味のある差分があり、verify が通り、ユーザーが止めていない場合は、`main` で commit し `origin/main` へ push する。push後に `git status --short --branch` を再確認する。

## Short Requests

- `見解だけ`: read-only。実装、commit、push をしない。
- `Docs整備して`: docs-only。実装ファイルや data 生成物を編集しない。
- `すすめて` / `次にすすめて` / `未着手つぶして` / `ゴールモード`: `STATUS.md` と必要な spec/decision を確認し、同じ verify set で閉じられる Goal Bundle 単位で進める。

## Closeout Fields

非自明な docs / governance / implementation では、最終報告に次を含める。

- 変更ファイル、理由、影響範囲
- LP/data/publish 境界への影響有無
- verification evidence
- commit hash / push state
- `sync-needed: yes | no`
- `capture-needed: yes | no`
- `SecondBrain reused: yes | no`
- GUI/UXに影響する場合は GUI確認箇所。内部/docs-only では GUI確認不要と理由

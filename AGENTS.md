# AGENTS.md

## Purpose

このファイルは `market-stats-viewer`（MSV）の作業入口である。方針は **AGENTS-first, not AGENTS-only**。ここで読み順と安全境界を確認し、必要な範囲だけ `PROJECT_CONTEXT`、`STATUS`、`DECISIONS`、`spec`、README へ進む。

MSV の目的は、市場統計と大型イベント情報を、外部LPや需要判断に使える配布データとして安定提供すること。DB更新、JSON生成、Release asset、automation はそのための手段であり、単独の成果ではない。

## Read Budget

- 最初に `AGENTS.md` を読む。
- `docs/context/PROJECT_CONTEXT.md` は retained optional upper premise layer。目的、source priority、LP影響、automation判断、仕様判断、docs governance に触れる場合だけ `Always Read Block` を読み、必要時だけ全文を読む。
- 現在地、再開地点、backlog は `docs/context/STATUS.md` を読む。
- 日付付きの固定判断や superseded 判断は `docs/context/DECISIONS.md` を読む。
- 外部契約、データ契約、pipeline、UI挙動は該当する `docs/spec_*.md` を読む。
- 実行手順、利用者向け概要、公開URLは `README.md` を読む。
- `docs/handovers/**`、`docs/thread_logs/**`、archive 相当は参照専用。新規ルールを置かない。
- 読み広げる前に、何を確認するために読むのかを短く固定する。

## Source Map

- `AGENTS.md`: 作業入口、読み順、常時安全境界、Git/verify の最小ルール。
- `docs/context/PROJECT_CONTEXT.md`: MSV の upper premise。目的、成功条件、判断原則、非目的、source-of-truth routing、LP掲載優先。
- `docs/context/STATUS.md`: current / re-entry / unresolved risk。完了履歴は補助情報。
- `docs/context/DECISIONS.md`: durable な日付付き判断。古い判断は削除せず superseded として残す。
- `docs/spec_data.md`: DB、JSON、manifest、外部アプリ向けデータ契約、source priority の詳細。
- `docs/spec_update_pipeline.md`: update scripts、workflow、provider、command、Release asset publish、automation 実行条件。
- `docs/event_signal_audit_automation.md`: イベント監査automationの入力、許可変更、禁止変更、evidence、verification、post-merge audit。

具体的な spec または日付付き decision が `PROJECT_CONTEXT` の一般原則と矛盾する場合は、具体的な spec / decision を優先する。未解決のまま外部挙動へ影響する場合は、推測で進めず `DECISIONS` へ暫定記録するか利用者へ確認する。

## Domain Guardrails

- SideBiz_HotelRM、公開LP反映、Cloudflare/Vite build、SideBiz側JSON取り込みはこのrepoの直接作業範囲ではない。必要な場合も別repo作業として明示する。
- データ取得元は公的公開統計、会場公式、公式/準公式ページ本文を優先する。Web検知でDB/LP掲載してよい根拠は公式/準公式ページ本文に限り、検索結果、AI概要、一般ニュース、SNS単体、二次流通単体はDB更新根拠にしない。
- LP向けイベント一覧は、重複統合済みの `data/lp_events.json` をデータ側で生成し、LP側は原則としてその一覧を読むだけにする。source priority の判断原則は `PROJECT_CONTEXT`、詳細契約は `docs/spec_data.md` を正本にする。
- 市場統計またはイベント情報に関わる変更では、LP側で利用するデータへの影響を必ず確認する。対象は `data/market_stats.sqlite`、`data/events.sqlite`、`data/event_signals.sqlite`、`data/lp_events.json`、`data/manifest.json`、Release asset、関連workflow、表示用のカテゴリ・期間・集計・正規化ロジック。
- 影響がない場合も `lp_impact=none` 相当の理由を残す。影響がある場合は、表示件数、カテゴリ、同一イベントのまとまり、データ鮮度、配布 manifest、source priority のどれが変わるかを分けて説明する。
- provider名、コマンド、workflow、fallback 条件などの実装詳細は `docs/spec_update_pipeline.md` に置く。source priority、DB schema、Release asset契約、LP表示契約を変える場合は、同一変更内で `docs/spec_*.md`、`docs/context/DECISIONS.md`、必要な tests/verify を同期する。

## Docs And Local Work

- 会話内容だけを正本にしない。正本化する場合は対象ファイルを更新する。
- 同じルールを複数文書へ重複展開しない。正本を1箇所に定め、他は短い参照にする。
- `PROJECT_CONTEXT.md` にタスク一覧、完了履歴、コマンド詳細、provider詳細、個別入出力契約を入れない。
- `spec` 更新要否は、外部挙動、入出力契約、用語、受け入れ条件、非機能要件が変わるかで判定する。
- repo固有Skillは `.agents/skills/` に置く。共有Skillは `~/.codex/skills` から使い、このrepoへ複製しない。
- docs配置、重複整理、正本化判断では `docs-governance`、spec影響が不明な場合は `spec-governance`、完了主張前には `verification-before-completion` を使う。
- subagent は read-heavy な調査、レビュー、要約に限定して使う。write-heavy、shared/high-conflict files、final verify、commit/push 判断はメインスレッド側が保持する。

## Safety Boundaries

- 明示承認なしで行わない: `data/**` 更新、SQLite/JSON生成物更新、workflow dispatch、Release publish、live hook/config apply、DB schema変更、依存追加/更新、認証/secret/権限変更、SideBiz反映。
- 秘密情報、Cookie、token、個人情報、raw log 全文、端末固有cacheを repo 管理対象へ入れない。
- `.chatgpt/` はツール実行履歴や一時メタ情報として扱い、repo 管理対象にしない。
- `docs/ai/` に後続連携用の資産を置く場合も、secret/PII/raw log/巨大一時出力がないことを確認し、現在taskに関係するファイルだけを stage する。

## Verify And Git

- 変更は依頼範囲に対して必要最小限に保つ。無関係な refactor、整形、削除、rename を混ぜない。
- docs-only の最小verifyは、`git diff --check`、対象語句の `rg`、BOM確認、secret/credential/PII marker の簡易scan、`git status --short --branch`。
- コード、data、workflow、Release asset、LP表示契約に触れた場合は、該当 spec/README の focused tests、build、生成確認を追加する。
- verify が失敗した状態では通常の commit/push をしない。失敗内容、未解決点、次に見る箇所を報告する。
- stage するのは現在taskに関係する tracked files だけ。ユーザー由来や無関係の差分を戻さない、stageしない。
- 意味のある差分があり、verify が通り、ユーザーが止めていない場合は、`main` で commit し `origin/main` へ push する。push後に `git status --short --branch` を再確認する。

## Request Semantics

- `見解だけ`: read-only。実装、commit、push をしない。
- `Docs整備して`: docs-only。実装ファイルや data 生成物を編集しない。
- `すすめて` / `次にすすめて` / `未着手つぶして` / `ゴールモード`: `STATUS.md` と必要な spec/decision を確認し、同じ verify set で閉じられる Goal Bundle 単位で進める。

## Closeout

非自明な docs / governance / implementation では、変更ファイル、理由、LP/data/publish 境界への影響、verification evidence、commit hash / push state、`sync-needed`、`capture-needed` を報告する。GUI/UX に影響する場合は確認箇所を示し、内部/docs-only では GUI確認不要の理由を示す。

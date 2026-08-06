<!-- agents-catalog-basis: repo-template-codex@8877297d; profile=solo-product; overlays=data-contract-and-migration,architecture-and-dependencies -->
# AGENTS.md

## Purpose

`market-stats-viewer`（MSV）は、市場統計と大型イベント情報を、外部LPや需要判断で安全に使える配布dataとして安定提供するrepoである。DB更新、JSON生成、Release asset、automationは手段であり、利用側で鮮度と意味を確認できるdata productが成果である。

方針はAGENTS-first, not AGENTS-onlyとする。root `AGENTS.md`を入口にし、追加文書は現在の問いと責務が一致するときだけ読む。

## Working Contract

- 変更前に、利用側の成果、今回の成功状態、変える対象、変えない対象、確認方法、LPへの影響を短く固定する。
- 既定は`main`上のlinear workflowとする。branch / worktree / child taskは、利用者が並列進行を明示した場合だけ増やす。
- source確認からDB、JSON / manifest、配布asset、利用側で観測できる結果までを1つのvertical sliceとして扱う。pipelineの途中だけを変えて完了にしない。
- 日常的で局所的な修正は直接進める。再発問題、複数境界をまたぐ変更、将来のdata contractを狭める変更では、局所patch、boundedな根本修正、大きな再設計を比較する。
- `PROJECT_CONTEXT`、`STATUS`、`DECISIONS`、task queueはoptional layerであり、存在するだけで毎回読まない。読み広げる前に、何を判断するためかを固定する。
- `見解だけ`はread-only、`Docs整備して`はdocs-only、`すすめて`系は同じ利用者可視成果とverify setで閉じられるbundleとして扱う。

## Source Map

- `AGENTS.md`: operational entrypoint、読込routing、常時安全境界、verification。
- `docs/context/PROJECT_CONTEXT.md`: 目的、成功条件、非目的、source priority、LP掲載優先。premise、LP影響、automation判断、docs governanceに触れる場合だけ`Always Read Block`から確認する。
- `docs/context/STATUS.md`: current state、re-entry、unresolved risk。
- `docs/context/DECISIONS.md`: durable decisionとsupersession history。
- `docs/spec_data.md`: DB、JSON、manifest、外部app向けdata contract、source priorityの詳細。
- `docs/spec_update_pipeline.md`: update script、workflow、provider、command、Release asset publish、automation実行条件。
- `docs/event_signal_audit_automation.md`: イベント監査automationの入力、許可・禁止変更、evidence、verification、post-merge audit。
- `README.md`: setup、実行手順、利用者向け概要、公開URL。
- `docs/handovers/**`、`docs/thread_logs/**`、archive相当は参照専用とし、新規ruleを置かない。

具体的なspecまたはactive decisionが一般原則と衝突する場合は、狭い責務の正本を優先する。外部挙動に影響する未解決事項は推測で進めず、利用者確認または新decisionへrouteする。

## Source And Product Guardrails

- data取得元は公的公開統計、会場公式、公式 / 準公式page本文を優先する。検索結果、AI概要、一般news、SNS単体、二次流通単体をDB更新やLP掲載の根拠にしない。
- LP向けイベント一覧は、重複統合済みの`data/lp_events.json`をdata側で生成し、LP側は原則その一覧を読むだけにする。
- 市場統計やイベント変更では、`data/market_stats.sqlite`、`data/events.sqlite`、`data/event_signals.sqlite`、`data/lp_events.json`、`data/manifest.json`、Release asset、workflow、category / period / aggregation / normalizationへの影響を確認する。
- 影響がない場合も`lp_impact=none`と理由を残す。影響がある場合は、表示件数、category、event統合、鮮度、manifest、source priorityのどれが変わるかを分ける。
- `SideBiz_HotelRM`のLP実装、Cloudflare / Vite build、SideBiz側JSON取込はこのrepoの直接範囲ではない。必要な場合は別repo作業として明示し、technical detailsを複製しない。

## Data, Architecture, And Dependencies

- DB schema、保存JSON、manifest、Release asset、URL、config、workflow入出力、LP表示契約をcontractとして扱う。意味またはshapeを変える場合はbefore / after、consumer、互換方針、forward migration、rollback、旧pathの削除条件を確認する。
- 既存dataを無断で削除、初期化、再解釈せず、適用済みの可能性があるmigrationを書き換えない。意味や新旧値が衝突する場合はsilent selectionしない。
- source priority、DB schema、Release asset、LP表示契約を変える場合は、同じ変更で該当`docs/spec_*.md`、必要なdecision、test / verifyを同期する。
- provider名、command、workflow、fallbackなどの実装詳細は`docs/spec_update_pipeline.md`へ置く。root、spec、script、automationに同じruleを複製しない。
- 責務は変更理由、lifecycle、外部境界、独立検証が異なる場合だけ分ける。新しいpackageや独自実装の前に、既存実装、dependency、current documentation、type、APIを確認する。

## Safety And Local Work

- 明示承認なしで行わない: `data/**`更新、SQLite / JSON生成物更新、workflow dispatch、Release publish、live hook / config apply、DB schema変更、dependency追加 / 更新、credential / secret / 権限変更、SideBiz反映。
- secret、Cookie、token、PII、raw log全文、端末固有cacheをrepo管理対象へ入れない。`.chatgpt/`はlocal-only metadataとして扱う。
- `.agents/skills/`にはrepo固有手順だけを置き、共有Skillを複製しない。docs配置には`docs-governance`、spec影響が不明な場合は`spec-governance`、GUI / UXには`frontend-skill`を必要時だけ使う。
- `docs/ai/`へ後続連携資産を置く場合も、secret / PII / raw log / 巨大一時出力がないことを確認し、現在taskのfileだけをstage対象にする。

## Verification And Closeout

- docs-onlyでは`git diff --check`、対象語句と参照path、BOM、secret / credential / PII marker、`git status --short --branch`を確認する。
- code、data、workflow、Release asset、LP表示契約に触れた場合は、該当spec / READMEのfocused test、build、生成物検証、consumer-facing smokeを追加する。
- 完了時は、変更、実行済み・未実行の検証、data / publish境界、`lp_impact`、必要な`sync-needed`、残存riskを報告する。

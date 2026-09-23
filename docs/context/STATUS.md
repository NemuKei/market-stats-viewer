# STATUS（market-stats-viewer）

最終更新: 2026-09-23

## Current / Re-entry

- 収集automation再構成のMSV実装（Task 1〜6）はlocal commit済み。Task 7の文書更新は作業ツリーで確認待ち。`main`からのpushは利用者確認待ちであり、GitHub Actionsの新経路、Release、SideBiz本番での動作は未確認。
- 次の利用者作業: Codex app automation `lp` を停止し、[automation prompt](../ai/plans/2026-09-23-automation-prompts.md) に従って `msv-venue-discovery` をMacBook Pro上に作成する。SideBizにはread-only連携用secret `RTR_READ_TOKEN` を登録する。
- MSVの新automationは `data/venue_discovery_inbox.json` だけを更新してpushする。`update_signals_venue_web_discovery.yml` がinboxを検証・適用し、DBとLPを更新する。成功した上流runから配布workflowがmanifestとReleaseを公開する。
- `watch_automation_freshness.yml` は毎日、inboxが存在しない場合または `run_at_utc` が3日より古い場合に失敗する。最初のlocal automation runとActions通知をpush後に確認する。
- 2026-09-23基準の `data/lp_events.json` は1,121件。収集源撤去の前後でevent集合は不変で、旧収集源由来の `supporting_sources` は除去済み。公開先への反映は別途確認する。

## Current Operating State

- MSVは市場統計と大型イベント情報のsource ownerであり、SideBiz側JSON、Cloudflare/Vite build、公開LPは別repoのownerである。
- LP向けイベント一覧は `data/lp_events.json` で重複統合し、表示source優先は `official_events > venue_web_discovery > starto_concert/kstyle_music` とする。通常生成は基準日から90日前までの保存済み過去イベントを含む。詳細契約は `docs/spec_data.md` を正とする。
- update command、provider、workflow、Release asset publish条件は `docs/spec_update_pipeline.md` を正とする。
- repo-local Skillは `dictionary-maintenance` と `venue-web-discovery` の2件に限定する。

## Verification / Remaining

- local code/dataの検証とcommitの詳細はGit履歴と [再構成計画](../ai/plans/2026-09-23-automation-restructure-plan.md) を参照する。
- push後は、inboxの初回pushによる適用workflow、freshness watch、Release 4 asset、SideBiz取込後の公開JSONとLP表示を順に確認する。
- SideBizの `RTR_READ_TOKEN` 登録とsync workflowは別repoの作業であり、MSV内では実施しない。

## References

- `AGENTS.md`
- `docs/context/PROJECT_CONTEXT.md`
- `docs/context/DECISIONS.md`
- `docs/spec_data.md`
- `docs/spec_update_pipeline.md`
- `docs/event_signal_audit_automation.md`

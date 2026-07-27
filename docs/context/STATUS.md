# STATUS（market-stats-viewer）

最終更新: 2026-07-28

## Current / Re-entry

- Active implementation / data update task: なし。Kstyle article `2280609` の日程修復、`fukuoka_paypay_dome` のcanonical移行に続き、`saitama_super_arena` の運用canonical会場名を「GMOアリーナさいたま」へ移行し、配布元DBと `data/lp_events.json` を同期した。
- Docs governance profile: Profile C。root `AGENTS.md` を作業入口とし、`PROJECT_CONTEXT.md`、`STATUS.md`、`DECISIONS.md` は責務が一致するときだけ読む optional layer とする。
- Next re-entry: 公開反映が必要なら、現行Release assetの内容とworkflow状態をlive確認し、Release更新を別承認で実行する。SideBiz反映と公開LP反映は別repo・別ownerとして扱う。
- 2026-07-26 の正式名称移行では `venue_id=fukuoka_paypay_dome` を維持し、旧「福岡PayPayドーム」と略称・英文表記をaliasへ移送した。適用判断は `D-20260726-001`、一般契約は `D-20260227-001` と該当specを正とする。
- 2026-07-28 のcanonical移行では `venue_id=saitama_super_arena` を維持し、旧「さいたまスーパーアリーナ」と略称・英文表記をaliasへ移送した。TicketJamのraw表記は取得元監査値として保持した。
- Unresolved risk: repo内の配布元データは新canonicalへ移行済みだが、現行Release assetと公開LPはこのtaskでは未更新・未公開のため、別途同期するまで旧asset表示が残る可能性がある。remoteはautomationで進むため、commit / push前にfresh fetchとdivergence確認が必要。

## Current Operating State

- MSVは市場統計と大型イベント情報のsource ownerであり、SideBiz側JSON、Cloudflare/Vite build、公開LPは別repoのownerである。
- LP-facing event dataは `data/lp_events.json` で重複統合し、表示source優先は `official_events > venue_web_discovery > starto_concert/kstyle_music > ticketjam_events` とする。詳細契約は `docs/spec_data.md` を正とする。
- update command、provider、workflow、Release asset publish条件は `docs/spec_update_pipeline.md` を正とする。
- TicketJam文字列はUTF-8 strict decodeと共通text-quality gateを使う。個別仕様と回復条件は `D-20260712-001` と該当specを正とする。
- 現時点のactive backlogはない。完了済みtaskの詳細、過去の件数、実測メモはGit履歴、`DECISIONS.md`、spec、生成レポートを参照し、STATUSへ再蓄積しない。

## Context / Skill Portfolio

- context lifecycleは利用者が採否、改訂、再検証、失効を明示した場合だけ `context-lifecycle` へrouteし、routine closeoutでは発火させない。
- repo-local Skillは `dictionary-maintenance` と `venue-web-discovery` の2件に限定する。
- `dictionary-maintenance` は辞書・カテゴリ監査のrepo固有scriptを所有し、folder名とSkill名を一致させる。
- `venue-web-discovery` は公式/準公式本文を根拠とする会場起点検知とLP-ready出力のrepo固有契約を所有する。
- cross-repo syncや一般的な仕様壁打ちはglobal ownerへ委譲し、repo-local Skillとして複製しない。旧本文はGit履歴に保持する。
- `CLAUDE.md` はroot `AGENTS.md`への薄い互換入口とし、Skill catalog、source priority、運用ruleを重複させない。
- SecondBrain / Memoryへの書込みは明示依頼または採用済みpolicyがある場合だけ行い、routine capture gateを置かない。

## Verification State

- 会場公式で、正式名称「みずほPayPayドーム福岡」、略称「みずほPayPayドーム / みずほPayPay」、英文表記 `MIZUHO PayPay Dome FUKUOKA` を確認した。
- `data/venue_registry.csv` と `data/venue_aliases.csv` は `venue_id=fukuoka_paypay_dome` を維持し、旧称・略称・英文名を新canonicalへ正規化する。
- `events.sqlite` は会場マスタ1行だけを変更し、全1,412 event行は不変、同venue_idへの27行の紐づきを保持した。`event_signals.sqlite` は旧canonicalの56行だけを変更し、内訳は `kstyle_music=1`、`ticketjam_events=39`、`venue_web_discovery=16`。raw表記、`first_seen_at_utc`、その他の行は不変。
- `venue_web_discovery_config.json` の対象confirmed event 16行を新canonicalへ更新し、全行の `event_id` が安定していることを確認した。Ticketjam会場表も同じvenue_idの代表名称だけを同期した。
- `saitama_super_arena` は `venue_registry.csv`、`venue_aliases.csv`、`ticketjam_venue_pages.csv`、VWD監視名を「GMOアリーナさいたま」へ同期し、旧名をaliasとして保持した。生成 `events.sqlite` は会場マスタ1行のみ、同venue_idの12 event行は不変とした。
- `event_signals.sqlite` はニュース系273 signalを再構築し、既存TicketJam 1行のcanonical `venue_name` を更新した。raw会場名「さいたまスーパーアリーナ」は監査用に保持した。
- `data/lp_events.json` は1,861件から1,849件へ再生成し、旧canonical表示5件を「GMOアリーナさいたま」へ移行した。旧canonical表示0件、event key重複0件、source priority契約は不変。
- `python -m scripts.build_lp_events` で `data/lp_events.json` を1,887件のまま再生成した。旧canonicalの表示50件を新正式名称へ置換し、対応する `event_key` 50件を再生成した。表示source内訳、カテゴリ、source priorityは不変で、`lp_impact=duplicate_grouping_change`。
- `PRAGMA integrity_check=ok`、対象56行のcontent hash一致、旧canonical表示0件、Stray Kids 2026-10-24の新canonical会場groupとsupporting sourceをread-only assertionで確認した。
- `dictionary-maintenance` のalias候補監査はUTF-8 modeで完走し、旧称・新正式名・略称・英文名は未解決候補に残らず、辞書監査自体の `lp_impact=none` を確認した。
- 今回のfocused testsは 10 passed。dictionary-maintenanceのalias監査は `lp_impact=none` で完走し、GMO会場名は未解決候補に残らなかった。
- temporary manifest生成で `events.sqlite`、`event_signals.sqlite`、`lp_events.json` のsizeとSHA-256を算出できることを確認した。tracked `data/manifest.json` は更新していない。
- Release asset、workflow dispatch、SideBiz、公開LPは未変更。`sync-needed=release_asset,sidebiz_public_lp`。

## Remaining Task Triage (ASCII)

Now:
- （なし）

Next:
- （なし）

After Next:
- （なし）

Later:
- （なし）

## References

- `AGENTS.md`
- `docs/context/PROJECT_CONTEXT.md`
- `docs/context/DECISIONS.md`
- `docs/spec_data.md`
- `docs/spec_update_pipeline.md`
- `docs/event_signal_audit_automation.md`
- `.agents/skills/README.md`

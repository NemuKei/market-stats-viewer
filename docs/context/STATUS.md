# STATUS（market-stats-viewer）

最終更新: 2026-07-26

## Current / Re-entry

- Active implementation / data update task: なし。Kstyle article `2280609` の parser 修正に続き、対象URLの既存5行を公式本文どおり7公演へ限定置換し、`data/lp_events.json` を再生成した。
- Docs governance profile: Profile C。root `AGENTS.md` を作業入口とし、`PROJECT_CONTEXT.md`、`STATUS.md`、`DECISIONS.md` は責務が一致するときだけ読む optional layer とする。
- Next re-entry: 公開反映が必要なら、現行Release assetの内容とworkflow状態をlive確認し、Release更新を別承認で実行する。SideBiz反映と公開LP反映は別repo・別ownerとして扱う。
- 2026-07-26 の限定修復では、Kstyle article `https://kstyle.com/article.ksn?articleNo=2280609` の最古 `first_seen_at_utc=2026-07-14T13:12:28Z` を保持した。source priority、schema、pipeline契約は変更していない。
- Unresolved risk: repo内の配布元データは修復済みだが、現行Release assetと公開LPはこのtaskでは未更新・未公開のため、別途同期するまで誤表示が残る可能性がある。remoteはautomationで進むため、commit / push前にfresh fetchとdivergence確認が必要。

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

- Kstyle article `2280609` のlive本文を修正後parserへ通し、7公演が `MUFGスタジアム 8/29-30`、`バンテリンドームナゴヤ 9/5-6`、`京セラドーム大阪 9/19-20`、`福岡PayPayドーム 10/24` に分かれることを確認した。
- 対象URLの既存5行をtransaction内で削除し、正しい7行を挿入した。全行で最古の `first_seen_at_utc` を保持し、書込み後に対象URLの行集合を再照合した。
- `MIZUHO PayPay Dome FUKUOKA` を既存の `福岡PayPayドーム` canonicalへ追加し、alias focused testは 4 passed、21 subtests passed。
- `dictionary-maintenance` のalias候補監査はUTF-8 modeで完走し、今回追加した会場表記は未解決候補に残らず、辞書単体の `lp_impact=none` を確認した。
- `python -m scripts.build_lp_events` で `data/lp_events.json` を 1,890件から1,887件へ再生成した。
- 2026-10-24 の京セラドーム大阪は YOASOBI のみとなり、Stray Kidsは福岡PayPayドームの既存official表示groupへ `kstyle_music` supporting sourceとして統合された。`lp_impact=display_count_change,duplicate_grouping_change`、source priorityは不変。
- `PRAGMA integrity_check=ok`、対象URLの7行完全一致、最古 `first_seen_at_utc` 保持、LP 1,887件、対象2会場の表示groupをread-only assertionで再確認した。
- focused testsは 27 passed、28 subtests passed。全test suiteは 56 passed、32 subtests passed。
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

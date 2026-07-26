# STATUS（market-stats-viewer）

最終更新: 2026-07-23

## Current / Re-entry

- Active implementation / data update task: Kstyle article `2280609` の「日付群 → 会場」形式で、前会場を次の日付群へ持ち越す parser 誤りはコードと回帰テストを修正済み。既存 `data/event_signals.sqlite` / `data/lp_events.json` の限定修復は `data/**` 更新の明示承認待ち。
- Docs governance profile: Profile C。root `AGENTS.md` を作業入口とし、`PROJECT_CONTEXT.md`、`STATUS.md`、`DECISIONS.md` は責務が一致するときだけ読む optional layer とする。
- Next re-entry: 明示承認後、Kstyle article `https://kstyle.com/article.ksn?articleNo=2280609` の行だけを公式本文どおり7公演へ限定置換し、`python -m scripts.build_lp_events` を再実行する。2026-10-24 の京セラドーム大阪は YOASOBI のみ、Stray Kids は福岡PayPayドームになることを確認する。Release asset更新、SideBiz反映、公開LP反映は別承認・別owner。
- 2026-07-26 にlocal `main`を `origin/main` へfast-forwardし、automation由来のdata更新19 commitsを `6b28819` まで取り込んだ。今回の parser 修正差分へ `data/**` は含めない。
- Unresolved risk: remoteはautomationで進むため、commit / push前にfresh fetchとdivergence確認が必要。現行の配布assetと公開LPには誤行が残っており、このtaskでは未更新・未公開。現在の数値・workflow run・Release asset freshnessは必要なtaskごとにlive確認する。

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

- `.\.venv\Scripts\python.exe -B -m pytest tests\test_kstyle_source.py -q --basetemp .tmp\pytest-kstyle-date-typo -p no:cacheprovider`: 20 passed、7 subtests passed。
- Kstyle article `2280609` のlive本文を修正後parserへ通し、7公演が `MUFGスタジアム 8/29-30`、`バンテリンドームナゴヤ 9/5-6`、`京セラドーム大阪 9/19-20`、`福岡PayPayドーム 10/24` に分かれることを確認した。
- 今回の変更対象は parser、回帰テスト、re-entry status。既存 `data/**`、Release asset、SideBiz、公開LPは未変更。承認後の想定 `lp_impact=display_count_change,duplicate_grouping_change`。
- `pwsh -NoProfile -File .\scripts\validate_skills.ps1`: repo-local Skill 2件 PASS。
- validatorはSkill name / folder不一致fixtureを拒否した。
- `scripts.build_event_signal_audit_report` から `dictionary-maintenance` のaudit moduleを新pathでloadできた。
- changed Python 3 filesはread-only AST parseを通過した。
- `.\.venv\Scripts\python.exe -B -m pytest tests -q --basetemp <writable-temp> -p no:cacheprovider`: 55 passed、31 subtests passed。
- retired Skill名と旧dictionary pathはcurrent guidance / executable pathから除外し、履歴はsuperseded decisionとGit履歴に保持する。
- 対象はgovernance、Skill package rename、validator、rename追随のinternal loader pathに限定する。data algorithm、`data/**`、workflow実行、Release、SideBiz、公開物は変更せず、`lp_impact=none`、GUI確認不要。

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

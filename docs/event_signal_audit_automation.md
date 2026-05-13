# Event Signal Audit Automation

## Purpose

この文書は、Codex automation がイベント情報監査を dry-run で実行するための手順書である。

対象は、会場公式以外のイベント情報に関する取得漏れ、イベント単位の正規化、会場名・アーティスト名・カテゴリ分類のメンテナンス候補である。

初期運用では、自動マージは行わない。Codex automation は、監査レポート生成、低リスク修正案の作成、verify、PR作成までを行う。

## Inputs

必須入力:

- `data/event_signal_audit_report.json`
- `data/event_signal_audit_report.md`
- `docs/spec_update_pipeline.md`
- `docs/context/STATUS.md`
- `docs/context/DECISIONS.md`

必要に応じて読む入力:

- `data/events.sqlite`
- `data/event_signals.sqlite`
- `data/venue_registry.csv`
- `data/venue_aliases.csv`
- `data/artist_registry.seed.csv`
- `data/artist_registry.jp.seed.csv`
- `data/artist_registry.manual.csv`
- `.agents/skills/dictionary_maintenance/scripts/audit_alias_candidates.py`
- `scripts/audit_kstyle_news_coverage.py`
- `scripts/audit_event_normalization_candidates.py`
- `scripts/build_event_signal_audit_report.py`
- `tests/test_kstyle_source.py`

## Dry-run Prompt

Codex automation には次のプロンプトを使う。

```text
market-stats-viewer のイベント情報監査レポートを確認し、dry-run として低リスク修正案を作成してください。

必ず最初に以下を読んでください。
- AGENTS.md
- docs/context/STATUS.md
- docs/context/DECISIONS.md
- docs/spec_update_pipeline.md
- docs/event_signal_audit_automation.md
- data/event_signal_audit_report.json

実行目的:
- data/event_signal_audit_report.json の候補を読み、automation_bucket ごとに処理を分ける。
- report_only は監査結果の要約だけを作る。
- pr_candidate は低リスク修正案を作る。
- human_review は修正せず、理由と確認対象をまとめる。

許可する変更:
- data/event_signal_audit_report.json
- data/event_signal_audit_report.md
- data/venue_aliases.csv への低リスク alias 追加案
- data/artist_registry.manual.csv への低リスク manual entry 追加案
- tests/test_kstyle_source.py など、既存挙動を固定するための狭いテスト追加
- scripts/signals/sources/kstyle.py の狭い parser 形式対応
- docs/context/STATUS.md の実行結果更新

禁止する変更:
- events.sqlite / event_signals.sqlite の大規模再生成
- data/manifest.json の更新
- Release asset の更新
- DBスキーマ変更
- venue_id / artist_id の変更
- venue_registry.csv の正式会場名変更
- 新しい外部サービス依存の追加
- parser全体の大幅再設計
- LP側の表示契約を変える変更
- 自動マージ

必須出力:
- 変更対象ファイル一覧
- 候補ごとの根拠
- 実施したverifyコマンドと結果
- lp_impact
- needs_review_reason
- 自動反映可、PR作成のみ、人間確認が必要、の分類

最終状態:
- verifyが通った場合でもPR作成までに留める。
- 自動マージはしない。
- needs_review_reason が1件でも残る場合、その候補は修正しない。
```

## Execution Steps

1. `git status --short` を確認する。
2. `data/event_signal_audit_report.json` を読む。
3. `summary.lp_impact` が `none` であること、または候補ごとの `candidate_lp_impact_counts` が説明されていることを確認する。
4. `automation_bucket_counts` を確認し、候補を次の3区分に分ける。
   - `report_only`: 修正しない。レポートの要約対象とする。
   - `pr_candidate`: 低リスク修正案の対象にしてよい。
   - `human_review`: 修正しない。根拠と確認観点だけを出す。
5. `needs_review` を確認する。
6. `needs_review_reason` が残る候補は、人間確認対象として扱う。
7. 低リスク修正案を作る場合、変更範囲を1種類に絞る。
   - alias追加だけ
   - manual artist追加だけ
   - K-Style parserの狭い形式対応だけ
   - テスト追加だけ
8. 修正後に監査レポートを再生成する。
9. verifyを実行する。
10. PRを作る場合は、PR本文に `lp_impact`、変更対象、根拠、verify結果、残った `needs_review_reason` を書く。
11. 初期運用ではマージしない。

## Report Regeneration Commands

K-Style実サイト監査を含める場合:

```powershell
uv run python -m scripts.audit_kstyle_news_coverage --pages 2 --sitemap-max-candidates 10 --max-detail-fetch 5 --output-json tmp\kstyle_audit_known.json --output-md tmp\kstyle_audit_known.md
```

イベント単位の正規化監査:

```powershell
uv run python -m scripts.audit_event_normalization_candidates --limit 50 --output-json tmp\event_normalization_audit.json --output-md tmp\event_normalization_audit.md
```

辞書・カテゴリ監査:

```powershell
uv run python .agents\skills\dictionary_maintenance\scripts\audit_alias_candidates.py --top 30 --output-json tmp\dictionary_maintenance_audit.json --output-md tmp\dictionary_maintenance_audit.md
```

統合監査レポート:

```powershell
uv run python -m scripts.build_event_signal_audit_report --kstyle-json tmp\kstyle_audit_known.json --normalization-json tmp\event_normalization_audit.json --dictionary-json tmp\dictionary_maintenance_audit.json --output-json data\event_signal_audit_report.json --output-md data\event_signal_audit_report.md --limit 50 --dictionary-top 30
```

ネットワークを使わない dry-run の場合:

```powershell
uv run python -m scripts.build_event_signal_audit_report --output-json data\event_signal_audit_report.json --output-md data\event_signal_audit_report.md --limit 50 --dictionary-top 30
```

この場合、K-Style取得漏れ監査は `component_status.kstyle_coverage=skipped` になる。

## Verify Commands

最小verify:

```powershell
uv run python -m py_compile scripts\audit_kstyle_news_coverage.py scripts\audit_event_normalization_candidates.py scripts\build_event_signal_audit_report.py .agents\skills\dictionary_maintenance\scripts\audit_alias_candidates.py
git diff --check
```

K-Style parser または test を変更した場合:

```powershell
uv run python -m pytest tests\test_kstyle_source.py
```

既知の失敗:

- `tests/test_kstyle_source.py` は、2026-05-12時点で `JIHO&EDEN` 期待値に対して `NINE.i` を返す既存失敗がある。
- この失敗を解消する変更を行った場合は、失敗が解消したことをverify結果に明記する。
- この失敗に触れない変更では、環境エラーではなく既存parser課題として扱う。

## PR Body Contract

PR本文には次を必ず含める。

```text
## Summary
- 何を変更したか
- どの監査候補に対応したか

## Evidence
- data/event_signal_audit_report.json の該当候補
- URL、title、event_date、venue_name、artist_name などの根拠

## lp_impact
- none / display_count_change / category_change / duplicate_grouping_change / source_priority_change
- LP側への影響がない場合は、その理由

## needs_review_reason
- 残っている確認事項
- 0件の場合は「なし」と書く

## Verify
- 実行したコマンド
- 成功/失敗
- 既知失敗が残る場合は、その理由

## Merge Policy
- dry-run 初期運用のため自動マージしない
```

## Auto-merge Gate Checklist

初期運用では自動マージしない。

将来、自動マージを検討する場合でも、次のチェックリストをすべて満たさない限り自動マージしてはいけない。

### Required Evidence

自動マージ判定には、次の証跡がすべて必要である。

- `data/event_signal_audit_report.json` が生成済みである。
- `summary.lp_impact` が `none` である、または候補ごとの `candidate_lp_impact_counts` とPR本文の `lp_impact` が一致している。
- 対象候補の `automation_bucket` が `pr_candidate` または `report_only` である。
- 対象候補に `needs_review_reason` が残っていない。
- 変更対象ファイル一覧がPR本文に明記されている。
- 候補ごとの根拠URL、title、event_date、venue_name、artist_name のうち、該当する値がPR本文に明記されている。
- verifyコマンドと結果がPR本文に明記されている。
- `git diff --check` が成功している。
- K-Style parser または test を変更した場合、`uv run python -m pytest tests\test_kstyle_source.py` の結果が明記されている。
- 配布DB、manifest、Release assetを更新していない、または更新した場合は自動マージ対象外としている。

### Auto-merge Allowed Candidates

次のいずれかに限り、将来の自動マージ候補にできる。

- 監査レポートのみの更新
  - 対象ファイル: `data/event_signal_audit_report.json`、`data/event_signal_audit_report.md`
  - 条件: `summary.lp_impact=none`
- 低リスクな会場alias追加
  - 対象ファイル: `data/venue_aliases.csv`
  - 条件: 既存 `venue_id` に別名を追加するだけで、`venue_id`、正式会場名、capacity、source_url、strategyを変更しない
- 低リスクなアーティストmanual entry追加
  - 対象ファイル: `data/artist_registry.manual.csv`
  - 条件: 既存 `artist_id` のcanonical名を変更せず、明確な別名または新規manual entryだけを追加する
- 狭いテスト追加
  - 対象ファイル: `tests/test_kstyle_source.py` など既存テストファイル
  - 条件: 既存仕様を固定するテスト追加のみで、実装変更を含まない
- K-Style parserの狭い形式対応
  - 対象ファイル: `scripts/signals/sources/kstyle.py`
  - 条件: 既存の `■公演情報` / `■開催概要` セクション抽出の範囲内で、日付、会場、アーティスト抽出の形式差分だけに対応する
  - 条件: `tests/test_kstyle_source.py` で対象ケースを固定している

### Auto-merge Prohibited Candidates

次のいずれかを含む変更は、自動マージしてはいけない。

- `events.sqlite` の再生成または内容変更
- `event_signals.sqlite` の再生成または内容変更
- `data/manifest.json` の更新
- GitHub Release asset の更新
- DBスキーマ変更
- `venue_id` の変更
- `artist_id` の変更
- `data/venue_registry.csv` の正式会場名、capacity、source_url、strategy変更
- 新しい外部サービス依存の追加
- Python依存ライブラリの追加または更新
- GitHub Actions workflow の権限、schedule、trigger変更
- parser全体の大幅再設計
- 取得対象ソースの大幅追加
- source優先順位の変更
- LP側の表示契約、フィールド契約、カテゴリ契約の変更
- `lp_impact=source_priority_change` を含む変更
- `needs_review_reason` が1件でも残る変更

### Required Classification

自動マージ判定では、候補を次のどれか1つに分類する。

- `auto_merge_candidate`: 将来の自動マージ候補。ただし初期運用ではマージしない。
- `pr_only`: PR作成まで。人間レビュー後にマージする。
- `human_review_required`: 修正しない。確認観点だけ出す。
- `blocked`: 禁止条件に該当するため、設計または仕様相談へ戻す。

### Decision Output Contract

自動マージ判定の出力には、次を含める。

```json
{
  "merge_gate_version": 1,
  "classification": "auto_merge_candidate | pr_only | human_review_required | blocked",
  "changed_files": [],
  "allowed_candidate_type": "",
  "prohibited_reasons": [],
  "required_evidence_missing": [],
  "lp_impact": "none | display_count_change | category_change | duplicate_grouping_change | source_priority_change",
  "needs_review_reason": [],
  "verify_commands": [],
  "verify_result": "passed | failed | not_run",
  "merge_action": "do_not_merge"
}
```

初期運用では、`classification=auto_merge_candidate` でも `merge_action` は必ず `do_not_merge` とする。

## LP Impact Handling

監査レポート生成のみの場合:

- `lp_impact=none`
- 理由: `events.sqlite`、`event_signals.sqlite`、`manifest.json`、Release assetを変更しないため

候補を修正する場合:

- alias追加: `duplicate_grouping_change`
- artist manual entry追加: `duplicate_grouping_change` または `category_change`
- category分類修正: `category_change`
- K-Style取得漏れ修正: `display_count_change`
- source優先順位を変える変更: `source_priority_change`

`lp_impact` が `none` 以外の場合は、PR本文でLP側の表示件数、カテゴリ、同一イベントのまとまり、データ鮮度のどれに影響するかを書く。

## Completion Criteria

dry-run は次を満たすと完了とする。

- 監査レポートを生成している。
- 候補を `report_only`、`pr_candidate`、`human_review` に分けている。
- 低リスク修正案がある場合、変更対象ファイルと根拠が明記されている。
- verify結果が明記されている。
- `lp_impact` が明記されている。
- `needs_review_reason` が残る候補を自動修正していない。
- PRを作る場合も、自動マージしていない。

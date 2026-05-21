# Event Signal Audit Automation

## Purpose

この文書は、Codex automation がイベント情報監査を実行し、低リスク候補を自動マージし、その後にマージ結果を監査するための手順書である。

対象は、会場公式以外のイベント情報に関する取得漏れ、イベント単位の正規化、会場名・アーティスト名・カテゴリ分類のメンテナンス候補である。

Codex automation は、監査レポート生成、低リスク修正案の作成、本文確認済み候補の限定取り込み、verify、PR作成、自動マージ判定までを行う。`Auto-merge Gate Checklist` をすべて満たす `auto_merge_candidate` は自動マージしてよい。自動マージした場合は、同じ候補をマージ前と別の観点で確認する `Post-merge Audit` を必ず実行する。

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
- `scripts/signals/sources/kstyle.py`
- `scripts/update_event_signals_data.py`

## Automation Prompt

Codex automation には次のプロンプトを使う。

```text
market-stats-viewer のイベント情報監査レポートを確認し、低リスク修正案の作成、限定取り込み、自動マージ判定、マージ後監査まで実行してください。

必ず最初に以下を読んでください。
- AGENTS.md
- docs/context/STATUS.md
- docs/context/DECISIONS.md
- docs/spec_update_pipeline.md
- docs/event_signal_audit_automation.md
- data/event_signal_audit_report.json

実行目的:
- data/event_signal_audit_report.json の `summary` と候補配列を読み、各候補行の `automation_bucket` ごとに処理を分ける。
- report_only は監査結果の要約だけを作る。
- pr_candidate は記事本文を確認し、低リスク修正案または限定取り込みを作る。
- human_review は修正せず、理由と確認対象をまとめる。
- K-Style 取得漏れ候補は、本文を取得して、国内公演か、未来日程か、日付・会場・アーティストが抽出可能かを確認する。
- 確認済みで現行parserが抽出できる候補は `backfill_article_urls` へ追加し、`data/event_signals.sqlite` へ限定取り込みしてよい。
- 現行parserが近い形式差分だけで失敗している候補は、`tests/test_kstyle_source.py` で対象形式を固定し、`scripts/signals/sources/kstyle.py` に狭い parser 形式対応を追加してから限定取り込みしてよい。
- 直接取り込みは、記事本文全文を保存せず、既存の `SignalRecord` 生成、辞書正規化、`upsert_signals` と同等の保存経路を使う。

許可する変更:
- data/event_signal_audit_report.json
- data/event_signal_audit_report.md
- data/event_signals.sqlite への K-Style 確認済み候補の限定追加
- data/ticketjam_supplement_report.json
- data/ticketjam_supplement_report.md
- data/venue_aliases.csv への低リスク alias 追加案
- data/artist_registry.manual.csv への低リスク manual entry 追加案
- tests/test_kstyle_source.py など、既存挙動を固定するための狭いテスト追加
- scripts/signals/sources/kstyle.py の狭い parser 形式対応
- scripts/update_event_signals_data.py の `kstyle_music.backfill_article_urls` 追加
- docs/context/STATUS.md の実行結果更新

禁止する変更:
- events.sqlite / event_signals.sqlite の大規模再生成
- K-Style以外の source 行の再生成または削除
- data/manifest.json の更新
- Release asset の更新
- DBスキーマ変更
- venue_id / artist_id の変更
- venue_registry.csv の正式会場名変更
- 新しい外部サービス依存の追加
- parser全体の大幅再設計
- LP側の表示契約を変える変更
- `Auto-merge Gate Checklist` を満たさない変更の自動マージ

必須出力:
- 変更対象ファイル一覧
- 候補ごとの根拠
- 候補ごとの判定結果（取り込み、parser改善後に取り込み、対象外、人間確認）
- 実施したverifyコマンドと結果
- lp_impact
- needs_review_reason
- 自動マージ可、PR作成のみ、人間確認が必要、の分類

最終状態:
- `classification=auto_merge_candidate` で verify が通り、禁止条件に該当しない場合は自動マージしてよい。
- 自動マージした場合は `Post-merge Audit` を実行し、監査結果をPRまたはautomation出力に残す。
- needs_review_reason が1件でも残る場合、その候補は修正しない。
```

## Execution Steps

1. `git status --short` を確認する。
2. `data/event_signal_audit_report.json` を読む。
3. `summary.lp_impact` が `none` であること、または候補ごとの `candidate_lp_impact_counts` が説明されていることを確認する。
4. `summary.automation_bucket_counts` を確認し、候補を次の3区分に分ける。
   - `report_only`: 修正しない。レポートの要約対象とする。
   - `pr_candidate`: 記事本文を確認し、低リスク修正案または限定取り込みの対象にしてよい。
   - `human_review`: 修正しない。根拠と確認観点だけを出す。
5. `needs_review` を確認する。
6. K-Style の `pr_candidate` は、本文確認結果で次の4区分に再分類する。
   - `import_ready`: 国内公演、未来日程、日付、会場、アーティストを確認でき、現行parserで抽出できる。
   - `parser_patch_ready`: 国内公演、未来日程、日付、会場、アーティストを確認できるが、狭い形式差分により現行parserが落としている。
   - `out_of_scope`: 海外公演、過去公演、展示・配信・リリース記事、リンク集のみ、またはイベント日程として保存しない記事。
   - `human_review_required`: 本文取得不可、日程や会場が不明、国内公演か判断できない、または parser 全体設計が必要。
7. `import_ready` は `scripts/update_event_signals_data.py` の `kstyle_music.backfill_article_urls` にURLを追加し、`data/event_signals.sqlite` に限定取り込みしてよい。
8. `parser_patch_ready` は、対象形式を `tests/test_kstyle_source.py` に追加し、`scripts/signals/sources/kstyle.py` の既存 `■公演情報` / `■開催概要` 抽出範囲内だけを修正する。修正後に該当URLを `backfill_article_urls` へ追加し、限定取り込みしてよい。
9. `out_of_scope` と `human_review_required` は修正しない。理由と確認対象だけを出す。
10. 候補行の `needs_review_reason` が残っていても、本文確認により `import_ready` または `parser_patch_ready` の証跡が揃った候補は、当該候補の `needs_review_reason` を解消済みとして扱ってよい。証跡が揃わない候補は、人間確認対象として扱う。
11. 低リスク修正案を作る場合、変更範囲を1種類に絞る。
   - alias追加だけ
   - manual artist追加だけ
   - K-Style parserの狭い形式対応だけ
   - テスト追加だけ
12. K-Style候補を取り込んだ場合は、`scripts.build_ticketjam_supplement_report` を再生成する。
13. 修正後に監査レポートを再生成する。
14. verifyを実行する。
15. PRを作る場合は、PR本文に `lp_impact`、変更対象、根拠、verify結果、残った `needs_review_reason` を書く。
16. `Auto-merge Gate Checklist` を評価し、`classification` と `merge_action` を出力する。
17. `classification=auto_merge_candidate` かつ `merge_action=merge_and_run_post_merge_audit` の場合だけ自動マージする。
18. 自動マージ後は `Post-merge Audit` を実行し、`post_merge_audit_result` を出力する。監査に失敗した場合は、同じautomation内で無言修正せず、`needs_fix_pr` または `needs_revert_pr` として人間が確認できる後続対応に分ける。

## K-Style Candidate Import Rules

K-Style候補を取り込んでよい条件:

- 記事本文に `■公演情報` または `■開催概要` の対象セクションがある。
- 日本国内公演である。判定には `日本`、都道府県、市区名、国内会場名、`IN JAPAN` などを使う。
- イベント日が現在日以降である。過去公演は取り込まない。
- `event_start_date`、`venue_name`、`artist_name` を確認できる。
- 現行parser、または狭い形式対応を追加したparserで、対象日程を `SignalRecord` として生成できる。
- 既存の `normalize_signal_labels` と `upsert_signals` 相当の経路で保存できる。

K-Style候補を取り込まない条件:

- 海外公演のみの記事。
- 展示、配信、楽曲リリース、動画、テレビ、ロケ地ツアー、チケット受付だけの記事で、イベント日程として保存しないもの。
- 本文がリンク集だけで、日付と会場が記事本文から抽出できないもの。
- 本文取得不可、または `■公演情報` / `■開催概要` セクションを確認できないもの。
- parser全体の再設計、source優先順位変更、取得対象ソース追加が必要なもの。
- 取り込みに DBスキーマ変更、ID変更、Release asset更新、manifest更新が必要なもの。

限定取り込み後に必ず確認する項目:

- `data/event_signals.sqlite` の `kstyle_music` 件数。
- 取り込んだ各URLごとの保存件数。
- 取り込んだ各日程の `event_start_date`、`venue_name`、`artist_name`。
- `data/event_signal_audit_report.json` の `missed_articles`、`needs_review_count`、`automation_bucket_counts`。
- `lp_impact=display_count_change` として、LP側の表示件数が変わること。
- `manifest.json` と Release asset を更新していないこと。

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

ネットワークを使わない監査レポート再生成の場合:

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

K-Style候補を取り込んだ場合:

```powershell
uv run python -m scripts.build_ticketjam_supplement_report
```

取り込み件数確認:

```powershell
uv run python -c "import sqlite3; c=sqlite3.connect('data/event_signals.sqlite'); print(c.execute(\"SELECT COUNT(*) FROM signals WHERE source_id='kstyle_music'\").fetchone()[0]); c.close()"
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
- `Auto-merge Gate Checklist` を満たす場合だけ自動マージする
- 自動マージ後は `Post-merge Audit` を必ず実行する
```

## Auto-merge Gate Checklist

次のチェックリストをすべて満たす候補だけを自動マージしてよい。

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
- 配布DBのうち `data/event_signals.sqlite` を変更する場合、変更内容が K-Style 確認済み候補の限定追加または更新だけである。
- `data/manifest.json` と Release asset を更新していない。
- 自動マージ後に実行する `Post-merge Audit` の確認項目がPR本文またはautomation出力に明記されている。

### Auto-merge Allowed Candidates

次のいずれかに限り、自動マージ候補にできる。

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
- K-Style確認済み候補の限定取り込み
  - 対象ファイル: `scripts/update_event_signals_data.py`、`data/event_signals.sqlite`、`data/event_signal_audit_report.json`、`data/event_signal_audit_report.md`、必要に応じて `data/ticketjam_supplement_report.json`、`data/ticketjam_supplement_report.md`
  - 条件: 本文確認済みで、国内公演、未来日程、日付、会場、アーティストを確認できる
  - 条件: `backfill_article_urls` への明示URL追加だけで対応し、source優先順位、DBスキーマ、manifest、Release asset、LP表示契約を変更しない

### Auto-merge Prohibited Candidates

次のいずれかを含む変更は、自動マージしてはいけない。

- `events.sqlite` の再生成または内容変更
- `event_signals.sqlite` の大規模再生成、K-Style確認済み候補の限定追加または更新以外の内容変更
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
- 対象候補に未解消の `needs_review_reason` が残る変更

### Required Classification

自動マージ判定では、候補を次のどれか1つに分類する。

- `auto_merge_candidate`: 自動マージしてよい。マージ後に `Post-merge Audit` を必ず実行する。
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
  "merge_action": "merge_and_run_post_merge_audit | do_not_merge",
  "post_merge_audit_required": true
}
```

`classification=auto_merge_candidate` の場合だけ、`merge_action=merge_and_run_post_merge_audit` を選択してよい。それ以外の分類では `merge_action=do_not_merge` とする。

## Post-merge Audit

自動マージ後の監査は、マージされた差分が `Auto-merge Gate Checklist` の範囲内に収まっていたかを確認する。マージ前の候補選定と同じ判断を繰り返すだけでなく、実際に取り込まれたDB行、生成レポート、LP影響、禁止ファイルの有無を確認する。

### Required Checks

- マージ後の差分に、PR本文またはautomation出力で明記された変更対象以外のファイルが含まれていない。
- `data/manifest.json`、Release asset、workflow、DBスキーマ、source優先順位が変更されていない。
- `data/event_signals.sqlite` を変更した場合、対象は `source_id='kstyle_music'` の本文確認済みURLだけである。
- K-Style取り込み行には `event_start_date`、`venue_name`、`artist_name` が入っている。
- K-Style取り込み行は、取り込み判断時点で未来日程である。
- 海外公演、展示、配信、楽曲リリース、動画、テレビ、ロケ地ツアー、リンク集のみの記事が取り込まれていない。
- `data/event_signal_audit_report.json` の `summary.missed_articles`、`summary.needs_review_count`、`summary.automation_bucket_counts` の変化が、取り込み件数またはレポート更新内容と矛盾していない。
- K-Style候補を取り込んだ場合、`data/ticketjam_supplement_report.json` と `.md` が再生成されている。
- `lp_impact` が `none` 以外の場合、表示件数、カテゴリ、同一イベントのまとまり、source優先順位のどれに影響したかが明記されている。
- verifyコマンドと結果が残っている。

### Post-merge Audit Output

```json
{
  "post_merge_audit_version": 1,
  "merged_ref": "",
  "result": "post_merge_audit_passed | needs_fix_pr | needs_revert_pr | human_review_required",
  "changed_files": [],
  "unexpected_files": [],
  "forbidden_changes": [],
  "db_row_checks": [],
  "lp_impact": "none | display_count_change | category_change | duplicate_grouping_change | source_priority_change",
  "verify_commands": [],
  "notes": []
}
```

`result=needs_fix_pr` または `result=needs_revert_pr` の場合は、後続PRまたは人間確認へ分ける。同じautomation内で、監査失敗を隠す修正を追加してはいけない。

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

イベント情報監査automationは次を満たすと完了とする。

- 監査レポートを生成している。
- 候補を `report_only`、`pr_candidate`、`human_review` に分けている。
- 低リスク修正案がある場合、変更対象ファイルと根拠が明記されている。
- verify結果が明記されている。
- `lp_impact` が明記されている。
- `needs_review_reason` が残る候補を自動修正していない。
- `auto_merge_candidate` を自動マージした場合、`Post-merge Audit` の結果が明記されている。
- `pr_only`、`human_review_required`、`blocked` の候補は自動マージしていない。

# Active Skill Bundle

このディレクトリは、この repo で Codex が自動検出する Skill 置き場です。
`template_bundle.txt` は `repo-template-codex` 由来の baseline を示し、repo 固有 skill はこの README で別管理します。

- 新規 Skill 名は hyphen-case を既定とします。既存の underscore 名は専用 migration まで legacy として扱います。
- Skill 検証は `scripts/validate_skills.ps1` を使います。legacy naming は warning 扱いにし、それ以外の validator error は fail にします。

## Template-native skills

| Skill | 何に効くか | Codex が使いそうな時 | 導入理由 | 元の出典 |
| --- | --- | --- | --- | --- |
| context_writeback | 常設コンテキストへの最小差分反映 | DECISIONS / STATUS / Owner Profile を更新したい時 | このテンプレの正本運用の中核 | local template |
| design-review | 責務境界・依存方向・分割要否の設計レビュー | 実装前に置き場所や分割方針を見たい時 | AI 編集耐性を task-specific な手順で点検するため | local template |
| docs_governance | ドキュメントの新設可否と正本整理 | README と docs の責務を分けたい時 | 重複記載を防ぐため | local template |
| release_gate | リリース可否判定とノート整理 | フェーズ完了時やタグ前 | リリース判断を標準化するため | local template |
| repo_bootstrap | 新規 repo の最小構成整理 | 初期構成を責務ベースで作る時 | テンプレの立ち上げを安定化するため | local template |
| task-add-and-triage | タスク追加直後の分割と棚卸し | backlog を整理しながら次順を決めたい時 | 実行順の迷いを減らすため | local template |

## External default bundle

| Skill | 何に効くか | Codex が使いそうな時 | 導入理由 | 元の出典 |
| --- | --- | --- | --- | --- |
| verification-before-completion | 完了主張前の fresh verification 徹底 | テスト通過や修正完了を主張する直前 | 汎用・安全・軽量で技術依存がほぼない | obra/superpowers |
| search-first | 実装前の既存解調査 | ライブラリ追加や新規 utility 実装前 | 再発明を減らし、依存判断を早める | affaan-m/everything-claude-code |
| deep-research | 複数ソースの比較と出典付き調査 | investigation、比較表、要約作成時 | docs / investigation 両方で再利用しやすい | Shubhamsaboo/awesome-llm-apps |

## Repo-specific additions

| Skill | 何に効くか | Codex が使いそうな時 | 導入理由 | 元の出典 |
| --- | --- | --- | --- | --- |
| bom_guard | Windows での UTF-8 BOM 混入防止 | PowerShell 経由でテキストを書き換える時 | この repo の Windows 運用で再発防止したい | local repo |
| dictionary_maintenance | `event_signals` 辞書の alias 整備 | 会場名やアーティスト名の未解決候補を潰す時 | ドメイン固有データ運用があるため | local repo |
| generic-skill-template-sync | repo 追加 skill の template 逆輸入判定 | skill を汎用化できるか整理する時 | template 利用 repoとして差分を還元しやすくするため | local repo |
| gitignore_guard | 新規生成物の `.gitignore` 判定 | 新しい補助ファイルや生成物が出た時 | 追跡対象の事故を減らしたい | local repo |
| sidebiz_sync | 確定事項の SideBiz ハブ同期 | 方針確定後に外部ハブへ短く共有する時 | repo 外の運用ハブ連携があるため | local repo |
| spec-wallbat-to-task | 仕様壁打ちから task 化までの順序固定 | 要件が曖昧な変更相談の時 | 実装着手前の仕様確定フローを守るため | local repo |

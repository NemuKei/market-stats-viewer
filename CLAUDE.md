# CLAUDE.md

## Project
宿泊旅行統計ビューア — 観光庁の公開統計を Streamlit で可視化。
公開URL: https://market-stats-viewer.streamlit.app/

## Tech Stack
- Python 3.11–3.12 / uv（パッケージ管理）
- Streamlit 1.41.1（UI）
- pandas 2.2.3 / openpyxl 3.1.5（データ処理・Excel入出力）
- beautifulsoup4 + requests（スクレイピング）
- GitHub Actions（定期データ更新）

## Commands
```bash
uv sync                                    # 依存インストール
uv run streamlit run app.py                # アプリ起動
uv run python -m scripts.update_data       # 宿泊統計データ更新
uv run python -m scripts.update_tcd_data   # 旅行・観光消費動向調査データ更新
uv run python -m scripts.update_events_data  # イベント情報データ更新
```

## Structure
```
app.py                        # Streamlit エントリポイント
scripts/                      # データ更新スクリプト（モジュール実行）
packages/                     # 共有ライブラリ
data/                         # 生成データ + meta JSON
docs/
  spec_*.md                   # 仕様書（正本）
  context/STATUS.md           # 現在地スナップショット
  context/DECISIONS.md        # 意思決定ログ
.agents/skills/               # Skill 定義
.github/workflows/            # CI/CD
```

## Source Priority
1. セキュリティ / 法令 / 公開制約
2. 仕様書（`docs/spec_*.md`）
3. 現況 / 意思決定ログ（`docs/context/`）
4. `CLAUDE.md` / `AGENTS.md`
5. Archive

同順位で矛盾 → より新しい決定を優先。未解決なら `DECISIONS.md` に `D-YYYYMM-xxx` で暫定記録。

## Read Budget
- 初手で読むのは `CLAUDE.md` のみ
- 追加読込はタスク遂行に必要な最小数に限定（目安: 追加 2 ファイルまで）
- 不足は推測せず、必要ファイルを特定して読む

## Engineering Defaults
- YAGNI / KISS / DRY
- 後方互換 shim は明確な運用要件がある場合のみ
- 変更は最小差分、ロールバック可能性を維持
- 実行中または verify 中に、未導入のツール、ライブラリ、Skill、preset が不足能力の原因になっている場合は、短い導入提案をしてよい。提案すべきか迷う場合は、提案を抑えるより、不足内容と候補を短く示す方を優先する。
- 新しい外部ツールや依存ライブラリを提案する前に、既存手段で代替できないか確認する。外部導入候補が残る場合は、`security-best-practices` が使える環境ではそれを使い、使えない場合でも供給網、権限、install script、version 固定を確認する。
- 導入提案を見送られた場合は、少なくとも `not-now`、`policy-reject`、`security-reject`、`cost-reject` のいずれかで理由を整理する。`policy-reject` と `security-reject` は、明示的な再検討があるまで再提案しない。

## Owner Profile
- Language: 日本語
- Technical: 非エンジニア — コード全文より「何を / なぜ / 影響範囲」を先に把握したい
- Communication: 結論先出し + 次アクション明確 + 専門語は必要最小限

## Delivery Rule
- GUI/UX 変更あり → 最終回答に `GUIで確認してほしい箇所`（画面名・操作手順・期待結果）を明示
- GUI 変更なし → `GUI確認不要` + 理由を明記
- verify 未通過では通常の `commit` / `git push` を行わない
- ユーザー停止指示がない限り、verify 通過後のみ `commit` + `git push origin <current-branch>` まで進める
  - 認証/権限エラー時は失敗理由 + 再実行コマンドを共有

## Security Baseline
- API キー・token・cookie・資格情報・個人情報をコミットしない
- `.env` 相当は作らない / 参照しない
- データ取得元は公的公開統計を原則とする

## Update Policy
- 仕様外の挙動 → 既存仕様として断定せず、新仕様提案として扱う
- 仕様変更手順: `DECISIONS.md` 更新 → `spec_*.md` 反映 → 実装

## Skills
必要時のみ使用。各スキルの条件と手順は SKILL.md を参照。

| Skill | 用途 | 定義 |
|---|---|---|
| context-writeback | 常設コンテキストへの反映（4 条件ゲート） | `~/.codex/skills/context-writeback/SKILL.md` |
| design-review | 責務境界・依存方向・分割要否の設計レビュー | `~/.codex/skills/design-review/SKILL.md` |
| docs-governance | ドキュメント新設 vs 統合判断（3 条件ゲート） | `~/.codex/skills/docs-governance/SKILL.md` |
| release-gate | リリース可否判定、タグ提案、リリースノート整理 | `~/.codex/skills/release-gate/SKILL.md` |
| verification-before-completion | 完了主張前の fresh verification | `~/.codex/skills/verification-before-completion/SKILL.md` |
| search-first | 実装前の既存解・既存パターン調査 | `~/.codex/skills/search-first/SKILL.md` |
| missing-capability-proposal | 実行中に見つかった不足能力の導入提案整理 | `~/.codex/skills/missing-capability-proposal/SKILL.md` |
| deep-research | 複数ソース比較と出典付き調査 | `~/.codex/skills/deep-research/SKILL.md` |
| dictionary_maintenance | event_signals の artist/venue 辞書の定期メンテ | `.agents/skills/dictionary_maintenance/SKILL.md` |
| gitignore_guard | 新規ファイルの `.gitignore` 判定と追記 | `.agents/skills/gitignore_guard/SKILL.md` |
| repo-bootstrap | 責務ベースの最小構成整備 | `~/.codex/skills/repo-bootstrap/SKILL.md` |
| sidebiz_sync | 確定事項の SideBiz ハブ同期 | `.agents/skills/sidebiz_sync/SKILL.md` |
| bom-guard | UTF-8 BOM 問題の防止 | `~/.codex/skills/bom-guard/SKILL.md` |
| spec-wallbat-to-task | 壁打ち → 仕様確定 → タスク化 | `.agents/skills/spec-wallbat-to-task/SKILL.md` |
| task-add-and-triage | タスク追加 + バックログ棚卸し | `~/.codex/skills/task-add-and-triage/SKILL.md` |
| generic-skill-template-sync | 汎用 Skill のテンプレリポ同期 | `.agents/skills/generic-skill-template-sync/SKILL.md` |

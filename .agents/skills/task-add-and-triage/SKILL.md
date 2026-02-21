---
name: task-add-and-triage
description: タスク追加直後に未実装タスクの棚卸し・統合・順序最適化を実施し、Remaining Task Triage を更新する。
---

# Purpose
タスク追加のたびにバックログを再整理し、重複や順序崩れを防ぐ。

# When to use / When NOT to use
- When to use: `tasks_backlog.md` にタスク追加した直後 / 既存タスクとの重複・依存が疑われるとき
- When NOT to use: typo 修正のみ / 完了チェック更新のみで優先順位見直し不要なとき

# Procedure
1. 未実装タスク (`- [ ]`) を一覧化する。
2. 追加タスクと既存タスクの重複・包含関係を確認する。
3. 統合可能なタスク群をエピック単位で抽出する。
4. 依存関係と効果対コストで順序を最適化し、`Now/Next/After Next/Later` に反映する。
5. `Remaining Task Triage (ASCII)` を更新する。統合時は元タスクIDの追跡可能性を残す。
6. 実装対象がどこまでかをユーザーへ明示する。

# Validation
- Now/Next 配置明記 / 重複・統合の判断理由あり / 順序変更理由あり / Triage 更新済

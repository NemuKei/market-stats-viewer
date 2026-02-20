---
name: task-add-and-triage
description: 新規タスクを追加した直後に、未実装タスクの棚卸し・統合効率化・順番最適化までを必ず実施したいときに使う。重複・依存・優先度を整理し、Remaining Task Triage を更新して実行順を確定する。
---

# Purpose
タスク追加のたびにバックログを再整理し、重複や順序崩れを防ぐ。

# When to use / When NOT to use
- When to use:
  - `tasks_backlog.md` に新規タスクを追加した直後
  - 追加タスクが既存タスクと重複・依存しそうなとき
  - 実装順序を `Now/Next` に反映したいとき
- When NOT to use:
  - 単純な typo 修正のみでタスク構造が変わらないとき
  - 完了チェックの更新だけで、優先順位見直しが不要なとき

# Inputs
- 追加したタスク（ID, Objective, Scope, Acceptance）
- 未実装タスク一覧（`- [ ]`）

# Outputs
- 棚卸し結果（重複・統合候補・依存関係）
- 更新済み `Remaining Task Triage (ASCII)` セクション
- 最適化後の未実装タスク実行順（Now/Next/After Next/Later）
- 必要時のみ、統合後の実行順ルール

# Procedure
1. 新規タスク追加後、未実装タスクを一覧化する。
2. 追加タスクと既存タスクの重複・包含関係を確認する。
3. 統合可能なタスク群をエピック単位で抽出する。
4. 依存関係と効果対コストに基づいて、未実装タスクの順番を最適化する。
5. 最適化結果を `Now/Next/After Next/Later` に反映する。
6. `Remaining Task Triage (ASCII)` に統合結果を反映する。
7. 統合した場合は、元タスクIDの追跡可能性を残す（ID列挙または参照）。
8. 更新後、実装対象がどこまでかをユーザーへ明示する。

# Validation
- 新規追加タスクが `Now/Next` のどこに入るか明記されている。
- 重複・統合候補の判断理由がある。
- 並び順変更の理由（依存 or 効果対コスト）が明記されている。
- `Remaining Task Triage (ASCII)` が古い状態のまま残っていない。
- 実装順序ルールが現在のバックログ構造と整合している。

# Examples
- 「タスク追加したので、残タスクを棚卸しして統合整理までやって」
- 「追加後にNow/Nextを更新して、重複をまとめて」

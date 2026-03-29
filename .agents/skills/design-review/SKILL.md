---
name: design-review
description: Review change placement and software design for non-trivial implementation, refactoring, or architecture questions. Use when a task may cross responsibility boundaries, introduce abstractions, grow a god file or function, mix domain rules with UI or handlers, or when the user asks for design feedback before coding.
---

# Design Review

## Overview

Review where code should live before or during implementation.
Root `AGENTS.md` defines the repo-wide rules. This skill only adds the task-specific review procedure for responsibility boundaries, dependency direction, and split decisions.

## Workflow

1. Frame the change first.
   - Identify the requested behavior, the public behavior that must stay unchanged, and the files or layers likely to move.
   - Identify the minimum verification that would prove the design change is safe.
   - For non-trivial changes, name the change scope, the public behavior that must stay unchanged, and the minimum verification before judging placement.
2. Check placement before code shape.
   - Keep business rules out of UI, CLI, handlers, and transport adapters.
   - Keep API, DB, file I/O, and other side effects at boundaries.
   - If domain rules and side effects are already mixed, recommend moving logic before adding more code.
3. Check dependency direction.
   - Prefer outer layers depending on inner rules, not the reverse.
   - If a seam is needed, prefer a small function or module split first.
   - Introduce interfaces or abstractions only when there is a real substitution or testing need.
4. Check growth pressure.
   - Do not extend god files, god classes, or god functions.
   - If responsibility expands, propose the smallest useful split and name the target module or boundary.
   - Prefer composition over inheritance for new code unless inheritance is clearly justified by framework constraints.
5. Decide the action.
   - `Keep`: current placement is sound; implement with minimal diff.
   - `Move`: logic belongs in a different module or layer.
   - `Extract`: create a smaller testable unit while preserving public behavior.
   - `Split First`: the task crosses too many responsibilities to implement safely in one step.
   - `Keep` is valid only when the current placement stays understandable for the same kind of future change.
   - If a small `Move` or `Extract` reduces repeated confusion without widening the blast radius, prefer it over a purely local patch.
6. Report concretely.
   - Start with the conclusion.
   - State what to change, why, impact range, and required verification.
   - If reviewing existing code, cite the smallest relevant files and lines.
   - If no design change is justified, say so explicitly.

## Output Pattern

```markdown
## 結論
[Keep / Move / Extract / Split First]

## 理由
- [責務境界または依存方向の判断]
- [公開挙動 / testability / side effect への影響]

## 次アクション
- [どのファイル / 層へ置くか]
- [必要な verify]
```

## Guardrails

- Do not turn a small task into a repo-wide rewrite.
- Do not add speculative abstractions or future-only interfaces.
- Do not recommend a pattern without naming the concrete boundary it protects.
- If existing code is constrained, choose the smallest local improvement that reduces future confusion.

## Example Triggers

- 「このロジックをどこに置くべきか見て」
- 「handler が太いので、どこまで分けるべきか判断して」
- 「interface を切るべきか、それとも関数抽出で十分か見て」
- 「既存の密結合構造に乗るしかないか、先にレビューして」

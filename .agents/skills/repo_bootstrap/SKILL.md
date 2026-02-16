---
name: repo_bootstrap
description: 新規リポジトリを最小構成で立ち上げるときに使う。構成は責務で分割し、入口はルートの AGENTS.md とする。順序起点の階層追加や START_HERE/THREAD_START の常設には使わない。
---

# Purpose
新規リポジトリを、責務ベースの最小構成で運用開始可能な状態にする。

# When to use / When NOT to use
- When to use:
  - 新規リポジトリの初期構成を整えるとき
  - 既存リポジトリの入口と責務分割を見直すとき
- When NOT to use:
  - 順序案内のためだけに階層や常設ファイルを増やすとき
  - `START_HERE.md` / `THREAD_START.md` の常設を前提にするとき

# Inputs
- 対象リポジトリの現状ディレクトリ構成
- 最低限必要な責務（運用ルール、実行手順、仕様、文脈、アーカイブ）

# Outputs
- 責務ベースで整理された最小構成
- 入口としてのルート `AGENTS.md`

# Procedure
1. 入口をルート `AGENTS.md` に固定する。
2. ディレクトリを「読む順序」ではなく「責務」で分ける。順序説明のための階層は追加しない。
3. `START_HERE.md` / `THREAD_START.md` を常設しない。
4. 推奨最小構成を満たすように作成・整理する。
   1. `AGENTS.md`（運用ルール）
   2. `README.md`（実行/利用手順）
   3. `docs/spec_*.md`（仕様）
   4. `docs/context/STATUS.md` / `docs/context/DECISIONS.md` / `docs/tasks_backlog.md` 相当（現在地/判断/タスク）
   5. `docs/archive/**`（過去資産）
5. 既存構成に同等責務のファイルがある場合は活かし、最小差分で整える。

# Validation
- 入口がルート `AGENTS.md` になっている。
- 構成が責務ベースで、順序起点の階層追加がない。
- `START_HERE.md` / `THREAD_START.md` が常設されていない。
- 推奨最小構成の責務が揃っている。

# Examples
- 「新規リポジトリを運用開始できる最小構成だけ作って」
- 「入口を `AGENTS.md` に統一し、責務ごとにディレクトリを整理して」

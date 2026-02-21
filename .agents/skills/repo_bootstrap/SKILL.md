---
name: repo_bootstrap
description: 新規リポジトリを責務ベースの最小構成で立ち上げるときに使う。入口はルート AGENTS.md / CLAUDE.md とし、順序起点の階層追加はしない。
---

# Purpose
新規リポジトリを責務ベースの最小構成で運用開始可能にする。

# When to use / When NOT to use
- When to use: 新規リポジトリの初期構成 / 既存リポジトリの入口・責務分割の見直し
- When NOT to use: 順序案内のための階層追加 / `START_HERE.md` / `THREAD_START.md` の常設

# Procedure
1. 入口をルート `AGENTS.md` / `CLAUDE.md` に固定する。
2. ディレクトリは「責務」で分ける（読む順序ではない）。
3. 推奨最小構成:
   - `AGENTS.md` / `CLAUDE.md`（運用ルール）
   - `README.md`（実行/利用手順）
   - `docs/spec_*.md`（仕様）
   - `docs/context/STATUS.md` / `docs/context/DECISIONS.md`（現在地/判断）
   - `docs/archive/**`（過去資産）
4. 既存構成に同等責務のファイルがあれば活かし、最小差分で整える。

# Validation
- 入口がルート `AGENTS.md` / `CLAUDE.md` / 責務ベース構成 / `START_HERE` 等が常設されていない

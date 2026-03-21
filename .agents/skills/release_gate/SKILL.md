---
name: release_gate
description: リリース可否判定、タグ提案、リリースノート作成、タグ付け実行を標準化する。フェーズ完了時と任意リリース指示時の両方に対応する。
---

# Purpose
リリース運用を「毎回同じ確認・同じ手順」で実行し、タグ採番やノート品質のブレを防ぐ。
root `AGENTS.md` の repo-wide ルールを前提にし、この Skill は release gate に必要な task-specific procedure だけを追加する。

# When to use / When NOT to use
- When to use:
  - フェーズ完了（Phase内タスク100%完了）後の正式リリース
  - ユーザーが任意タイミングでリリースを指示したとき
  - タグ採番とリリースノートを提案してから実行したいとき
- When NOT to use:
  - 実験コミットの共有だけで、リリース化しないと明言されているとき
  - 未反映の必須変更が残っており、リリース判定ができないとき

# Inputs
- リリース対象ブランチ（既定: `main`）
- 直前リリースタグ（例: `v0.6.13`）
- 今回の対象範囲（フェーズ名または任意スコープ）
- 実行モード（`phase_complete` / `manual`）

# Outputs
- Release Ready 判定（Pass/Fail と理由）
- 推奨タグ2種
  - マイルストーンタグ: `phase-<phase>-done-YYYYMMDD`
  - リリースタグ: `vX.Y.Z`
- リリースノート草案（概要/変更点/影響/確認）
- 実行ログ（作成タグ、push結果、未実施理由）

# Procedure
1. Preflight（必須）
   - `git fetch origin --tags`
   - `git status --short` が空であること
   - `git branch --show-current` が対象ブランチであること
   - `docs/tasks_backlog.md` / `docs/context/STATUS.md` が最新であること
2. 差分確認
   - `git describe --tags --abbrev=0` で直前タグを取得
   - `git log --pretty=format:"- %h %s" <prev_tag>..HEAD` でコミット一覧を生成
   - `git diff --name-only <prev_tag>..HEAD` で影響ファイルを確認
3. バージョン提案（SemVer）
   - MAJOR: 破壊的変更あり
   - MINOR: 後方互換な機能追加（フェーズ完了時の既定）
   - PATCH: バグ修正/軽微改善のみ
4. タグ作成
   - フェーズ完了時: `phase-<phase>-done-YYYYMMDD` を作成
   - 常時: `vX.Y.Z` の注釈付きタグを作成
5. push
   - `git push origin <branch>`
   - `git push origin <tag...>`
6. リリースノート作成
   - 3ブロックを最小構成で作る
     - 変更概要
     - 主な変更点（ユーザー影響順）
     - 既知の注意点/確認事項
7. 公開
   - `gh` が利用可能なら GitHub Release をCLIで作成
   - `gh` が無い場合は、タグpushまで自動実行し、ノートを手動貼付用で出力

# GitHub Release CLI Flow (`gh`)
1. インストール確認
   - `gh --version`
2. 初回認証
   - `gh auth login --hostname github.com --git-protocol https --web`
   - `gh auth status`
3. 既存Release重複確認
   - `gh release view <tag> --repo <owner>/<repo>`
4. リリース作成
   - `gh release create <tag> --repo <owner>/<repo> --title "<title>" --notes-file <path>`
5. 公開確認
   - `gh release view <tag> --repo <owner>/<repo> --json name,tagName,isDraft,isPrerelease,publishedAt,url`

# Validation
- `git status --short` が空で実行されている
- 最新タグと今回タグの関係が説明できる
- タグは重複せず、命名規則に一致する
- ノートは `<prev_tag>..HEAD` の差分と整合している

# Quick Commands (PowerShell)
```powershell
git fetch origin --tags
git status --short
git branch --show-current
$prev = git describe --tags --abbrev=0
git log --pretty=format:"- %h %s" "$prev..HEAD"
git diff --name-only "$prev..HEAD"
gh --version
gh auth status
gh release view <tag> --repo <owner>/<repo>
```

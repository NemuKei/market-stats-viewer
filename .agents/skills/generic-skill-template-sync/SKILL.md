---
name: generic-skill-template-sync
description: Skill 追加・更新時に汎用/固有を判定し、汎用ならテンプレリポジトリへ同期する。AGENTS.md / CLAUDE.md と template_bundle.txt の整合も維持する。
---

# Purpose
Skill 追加時に「開発リポだけ更新されてテンプレへ未反映」を防ぐ。

# When to use / When NOT to use
- When to use: `.agents/skills/<name>/` を新規追加・更新した直後
- When NOT to use: リポジトリ固有 Skill のみ / typo 修正のみで運用差分なし

# Procedure
1. Skill の目的と適用範囲を確認する。
2. 汎用判定:
   - 汎用: 多くのリポジトリで再利用可能、特定プロダクト/外部連携に依存しない
   - 固有: 特定ドメイン・システム・運用に依存
3. 現在リポジトリを更新:
   - `AGENTS.md` / `CLAUDE.md` の Skills 一覧へ追記・更新
   - 汎用なら `.agents/skills/template_bundle.txt` に追加
4. 汎用判定の場合、テンプレリポジトリへ同期:
   - テンプレ側 `.agents/skills/<name>/` へ反映
   - テンプレ側 `AGENTS.md` / `template_bundle.txt` も更新
5. 同期先パスが不明なら推測せずユーザーに確認。

# Validation
- Skill 名とフォルダ名一致 / frontmatter に name+description / 汎用判定理由あり / 汎用時は3点（現リポ AGENTS+CLAUDE, bundle, テンプレ）更新済

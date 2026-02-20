---
name: generic-skill-template-sync
description: 新しいSkillを追加または更新したときに、そのSkillが汎用かリポジトリ固有かを判定し、汎用Skillであればテンプレリポジトリへ同期反映する。AGENTS.md と template_bundle.txt の整合更新も同時に行う。
---

# Purpose
Skill追加時に「このリポジトリだけ更新されてテンプレへ未反映」を防ぐ。

# When to use / When NOT to use
- When to use:
  - `.agents/skills/<skill-name>/` を新規追加した直後
  - 既存Skillを更新し、テンプレへ同期すべきか再判定したいとき
  - `AGENTS.md` と `.agents/skills/template_bundle.txt` の整合を保ちたいとき
- When NOT to use:
  - リポジトリ固有Skill（業務固有連携、特定ドメイン専用）だけを追加したとき
  - typo修正のみで運用差分がないとき

# Inputs
- 追加/更新したSkill名（例: `my-new-skill`）
- Skill本体（`.agents/skills/<skill-name>/SKILL.md`）
- テンプレリポジトリのパス（分かっている場合）

# Outputs
- 汎用/固有の判定結果（理由付き）
- 更新済み `AGENTS.md`（必要な場合）
- 更新済み `.agents/skills/template_bundle.txt`（汎用の場合）
- テンプレリポジトリへの同期結果（成功/未実施理由）

# Procedure
1. 追加/更新したSkillの目的と適用範囲を確認する。
2. 次の基準で汎用判定する:
   - 汎用: 多くのリポジトリで再利用でき、特定プロダクト/外部連携に依存しない。
   - 固有: 特定ドメイン、特定システム名、特定運用に依存する。
3. 現在リポジトリを更新する:
   - `AGENTS.md` の Skills一覧へ追記または説明更新
   - 汎用なら `.agents/skills/template_bundle.txt` にSkill名を追加
4. 汎用判定ならテンプレリポジトリへ同期する:
   - テンプレ側へ `/.agents/skills/<skill-name>/` を同名で反映
   - テンプレ側 `AGENTS.md` に同じSkill行を反映
   - テンプレ側 `.agents/skills/template_bundle.txt` に追記
5. 同期先パスが不明な場合は推測せず、ユーザーに確認して停止する。
6. 差分を確認し、必要なら `commit` と `push` を行う。

# Validation
- Skill名とフォルダ名が一致している。
- `SKILL.md` の frontmatter は `name` と `description` を持つ。
- 汎用判定理由が1行以上で残っている。
- 汎用の場合、少なくとも以下3点が更新されている:
  - 現在リポジトリの `AGENTS.md`
  - 現在リポジトリの `.agents/skills/template_bundle.txt`
  - テンプレリポジトリ側の同等ファイル

# Examples
- 「新しいSkill作った。汎用ならテンプレにも反映して」
- 「このSkill更新、テンプレ同梱対象か判定して同期して」

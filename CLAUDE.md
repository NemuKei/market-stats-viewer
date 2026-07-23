# CLAUDE.md

このファイルは互換入口であり、運用正本ではない。

- 最初に root `AGENTS.md` を読み、目的、読み順、安全境界、verify / Git既定に従う。
- `PROJECT_CONTEXT`、`STATUS`、`DECISIONS`、`spec` は `AGENTS.md` に記載された条件で必要なものだけ読む。
- 実行手順、開発command、公開URLは `README.md` と `docs/spec_update_pipeline.md` を正とする。
- shared Skill は現在の user-scope runtime、repo固有Skillは `.agents/skills/README.md` を正とし、このファイルにSkill catalogを複製しない。

source priority、Skill名、依存version、完了履歴をこの互換入口で独自管理しない。

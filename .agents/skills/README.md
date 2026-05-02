# Repo-Specific Skills

このディレクトリには、`market-stats-viewer` 固有の Skill だけを置く。

- 共有 Skill は `~/.codex/skills` から使う
- `.agents/skills/` には、この repo のファイル構成や運用に依存する Skill だけを残す

## この repo に残す Skill

| Skill | 役割 |
| --- | --- |
| `dictionary_maintenance` | `event_signals` の辞書メンテナンスを行う |
| `generic-skill-template-sync` | 汎用 Skill のテンプレ逆輸入要否を判定する |
| `spec-wallbat-to-task` | 仕様壁打ちから backlog タスク化までを固定する |

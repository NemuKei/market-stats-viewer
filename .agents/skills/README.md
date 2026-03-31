# Repo-Specific Skills

このディレクトリには、`market-stats-viewer` 固有の Skill だけを置く。

- 共有 Skill は `~/.codex/skills` から使う
- `.agents/skills/` には、この repo のファイル構成や運用に依存する Skill だけを残す

## この repo に残す Skill

| Skill | 役割 |
| --- | --- |
| `dictionary_maintenance` | `event_signals` の辞書メンテナンスを行う |
| `generic-skill-template-sync` | 汎用 Skill のテンプレ逆輸入要否を判定する |
| `gitignore_guard` | 新規生成物の `.gitignore` 判定を行う |
| `sidebiz_sync` | 確定事項を SideBiz ハブへ同期する |
| `spec-wallbat-to-task` | 仕様壁打ちから backlog タスク化までを固定する |

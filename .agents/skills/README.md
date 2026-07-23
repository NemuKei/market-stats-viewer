# Repo-Specific Skills

このディレクトリには、`market-stats-viewer` 固有の Skill だけを置く。

- 共有 Skill は `~/.codex/skills` から使う
- `.agents/skills/` には、この repo のファイル構成や運用に依存する Skill だけを残す

## この repo に残す Skill

| Skill | 役割 |
| --- | --- |
| `dictionary-maintenance` | `event_signals` の辞書メンテナンスと監査候補抽出を行う |
| `venue-web-discovery` | 会場起点の公式/準公式Web検知からLP-readyイベント出力までを固定する |

共有・汎用の判断手順は global Skill を使い、cross-repo sync や一般的な仕様壁打ちを repo-local Skill として複製しない。退役した旧Skill本文はGit履歴に保持する。

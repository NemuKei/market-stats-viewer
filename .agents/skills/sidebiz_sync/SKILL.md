---
name: sidebiz_sync
description: 確定した実装方針・決定事項を SideBiz ハブへ要約同期する。コード詳細は持ち込まず要点のみ。
---

# Purpose
このリポジトリの確定情報を副業ハブ（SideBiz）へ最小要約で同期し、横断確認を容易にする。

# When to use / When NOT to use
- When to use: STATUS の Next/Done 更新時 / DECISIONS に影響ある決定追加時 / 仕様変更確定時
- When NOT to use: 実装途中の未確定案 / コード差分の詳細説明

# Procedure
1. 変更が「確定情報」か判定（未確定なら同期しない）。
2. 開発リポ側の正本を先に更新（STATUS / DECISIONS / spec）。
3. SideBiz ハブへ 1件1〜3行で要約追記:
   - 同期先: `c:/Users/n-kei/dev/SideBiz_HotelRM/00_Admin/workspace_index.md`
   - 節: `## 開発リポ連携メモ（要約） > ### market-stats-viewer`
   - 内容: 何を決めた + 次アクション（必要時） + 正本参照
4. コード詳細は書かない。

# Validation
- 開発リポ正本が先に更新済 / 要約は1件1〜3行 / コード詳細なし

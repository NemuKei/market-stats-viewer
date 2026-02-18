---
name: sidebiz_sync
description: market-stats-viewer の実装方針・確定事項を SideBiz ハブへ要約連携するときに使う。コード詳細は持ち込まず、要点のみを追記する。
---

# Purpose
このリポジトリで確定した実装方針や判断を、副業ハブ（SideBiz）へ最小要約で同期し、横断確認を容易にする。

# When to use / When NOT to use
- When to use:
  - `docs/context/STATUS.md` の Next/Done が更新されたとき
  - `docs/context/DECISIONS.md` に将来影響のある決定を追加したとき
  - 仕様変更（`docs/spec_*.md`）の方針が確定したとき
- When NOT to use:
  - 実装途中のメモや未確定案のみのとき
  - コード差分の詳細説明を書きたいとき（正本は開発リポ側に残す）

# Inputs
- 確定した変更内容（決定内容、次アクション、主要仕様更新）
- 開発リポ側の正本参照先
  - `docs/context/STATUS.md`
  - `docs/context/DECISIONS.md`
  - `docs/spec_*.md`

# Outputs
- SideBizハブ要約の更新:
  - `c:/Users/n-kei/dev/SideBiz_HotelRM/00_Admin/workspace_index.md`
  - 節: `## 開発リポ連携メモ（要約） > ### market-stats-viewer`

# Procedure
1. 変更が「確定情報」か判定する（未確定なら同期しない）。
2. market-stats-viewer 側の正本を先に更新する（status / decisions / spec）。
3. SideBizハブには 1件1〜3行で要約を追記する。
   1. 何を決めた/更新したか
   2. 次に何をするか（必要時）
   3. 正本ファイル参照
4. コード詳細・実装断片は書かない（索引要約に限定する）。

# Validation
- market-stats-viewer 側の正本更新が先に行われている。
- SideBizハブ要約は `### market-stats-viewer` 節に追記されている。
- 1件1〜3行で、要点と参照先のみ記載されている。
- コード詳細を持ち込んでいない。

# Example
- 「指標追加の仕様を更新したので、SideBizの `workspace_index.md` の market-stats-viewer 節へ要約を追記する」

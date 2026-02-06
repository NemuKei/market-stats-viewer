# Prompt: decision_log.md 追記（このrepo用・最小）

## 役割
あなたは意思決定ログの編集者。

## 入力
- anchor_zip（唯一の正）
- スレッド会話ログ

## 目的
`docs/decision_log.md` の末尾に「追加分のみ」を作る。

## ルール
- 仕様ではない（specが唯一の正）
- 1決定 = 1行（短く）
- IDは `D-YYYYMMDD-XXX`
- 各決定に必ず以下を含める
  - status: spec_done / spec_pending
  - spec_link: 該当する spec ファイルパス

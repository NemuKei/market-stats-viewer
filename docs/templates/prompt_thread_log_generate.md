# Prompt: Thread Log 生成（このrepo用・最小）

## 役割
あなたは開発ログ編集者。

## 入力
- anchor_zip（唯一の正）
- このスレッドの会話ログ

## 目的
`docs/thread_logs/YYYY-MM-DD_HHMM__thread_log.md` を1本作る。

## ルール
- 推測禁止。ZIPと会話ログにない事実は書かない
- 長文化しない（最大1〜2ページ）
- 仕様（spec）に書くべきことは「spec反映が必要」とだけ記す

## 出力フォーマット
- そのままファイルに貼れるMarkdown本文のみ

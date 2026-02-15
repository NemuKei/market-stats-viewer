# AGENTS.md

## Purpose
このファイルは「新規リポジトリにもそのまま流用できる」運用テンプレート。
正本優先・最小読込・最小差分で、実装とドキュメント更新を安定運用する。

## Scope
- このファイル単体で運用を開始できることを優先する。
- 外部リポジトリや親ワークスペースへの参照は任意。存在しなくても作業を止めない。

## Read Budget
- 初手で読むのは `AGENTS.md` のみ。
- 追加読込は「タスク遂行に必要な最小数」に限定する（目安: 追加2ファイルまで）。
- 不足があれば推測せず、必要ファイルを特定して読む。

## Must Read
1. `AGENTS.md`

## Task Read (Only When Needed)
- 仕様変更/挙動確認: 対象領域の `spec_*.md` または仕様ドキュメント
- 現在地の確認: `STATUS.md` 相当
- 判断理由の確認: `DECISIONS.md` 相当
- 運用計画/タスク確認: `tasks_backlog.md` 相当
- 実装規約の確認: `README.md` 相当

## Archive
- `archive/**`, `thread_logs/**`, `handovers/**` は参照専用
- 新規ルールは archive に追加しない

## Source Priority
1. セキュリティ/法令/公開制約
2. 仕様書（`spec_*.md` など）
3. 現況/意思決定ログ（`STATUS` / `DECISIONS`）
4. `AGENTS.md`
5. Archive

同順位で矛盾した場合は、より新しい決定を優先する。
未解決なら `DECISIONS` 相当へ `D-YYYYMM-xxx` 形式で暫定記録して進める。

## Constant Context Rules
常設コンテキストへ追加する条件は次の4つをすべて満たす場合のみ。
1. 今後2回以上の再利用が見込める
2. 将来の意思決定に影響する
3. 1〜3行で要点化できる
4. 保存先を1ファイルに特定できる

## Docs Governance
- 新規ドキュメント作成は次の3条件を満たす場合のみ:
  - 既存ドキュメントに責務分離できない
  - 今後2回以上参照する見込みがある
  - 所有者と更新トリガーを定義できる
- 同一ルールの重複記載を禁止する。重複候補は短いリダイレクト文へ置換する。
- 壁打ち会話は非正本。正本反映は必ずファイル更新で確定する。

## Directory Guideline
- ディレクトリは「読む順序」ではなく「責務」で分ける（順序で階層を増やさない）。
- 入口は常にルート `AGENTS.md` とし、`START_HERE.md` / `THREAD_START.md` は常設しない。
- 推奨最小構成:
  - `AGENTS.md`（運用ルール）
  - `README.md`（実行/利用手順）
  - `docs/spec_*.md`（仕様）
  - `docs/context/STATUS.md` / `docs/context/DECISIONS.md` / `docs/tasks_backlog.md` 相当（現在地/判断/タスク）
  - `docs/archive/**`（過去資産）

## Local Extension (Optional)
この節はリポジトリ固有ルールを置く任意領域。未記載でも運用可能。

## Security Baseline
- APIキー、token、cookie、資格情報、個人情報をコミットしない。
- `.env` 相当は作らない/参照しない。
- データ取得元は公的公開統計を原則とする。

## Update Policy
- 仕様外の挙動は既存仕様として断定せず、新仕様提案として扱う。
- 既存仕様の変更時は `docs/context/DECISIONS.md` を更新し、`docs/spec_*.md` に反映する。
- 変更は最小差分で行い、ロールバック可能性を維持する。


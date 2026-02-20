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
- 実装規約の確認: `README.md` 相当
- リポジトリ固有の運用計画: `Local Extension` で定義されたドキュメントのみ参照

## Skills (Only When Needed)
- `context_writeback`: 常設コンテキストへの反映が必要なときだけ使う。条件判定と反映手順は `.agents/skills/context_writeback/SKILL.md` を参照。
- `docs_governance`: ドキュメント新設/統合/正本反映の判断が必要なときだけ使う。手順は `.agents/skills/docs_governance/SKILL.md` を参照。
- `repo_bootstrap`: 新規リポジトリの最小構成を責務ベースで整備するときだけ使う。手順は `.agents/skills/repo_bootstrap/SKILL.md` を参照。
- `sidebiz_sync`: 実装方針や確定事項を SideBiz ハブへ要約同期するときだけ使う。手順は `.agents/skills/sidebiz_sync/SKILL.md` を参照。

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
常設コンテキストの追記手順と更新先の選択は `.agents/skills/context_writeback/SKILL.md` を参照。
この節では「推測禁止」「条件を満たすときのみ反映」の方針を維持する。

## Docs Governance
ドキュメント新設可否、重複排除、正本反映の確定手順は `.agents/skills/docs_governance/SKILL.md` を参照。
この節では「重複記載禁止」「会話は非正本」の方針を維持する。

## Engineering Defaults
- デフォルトは単純さを優先する（YAGNI / KISS / DRY）。
- 後方互換のための shim・fallback は、明確な運用要件がある場合のみ追加する。
- 互換ロジックを追加する場合は、目的・適用範囲・廃止条件を必ず記載する。

## Directory Guideline
責務ベースのディレクトリ設計と最小構成の作成手順は `.agents/skills/repo_bootstrap/SKILL.md` を参照。
この節では「入口はルート `AGENTS.md`」「`START_HERE.md` / `THREAD_START.md` を常設しない」方針を維持する。

## Local Extension (Optional)
この節はリポジトリ固有ルールを置く任意領域。未記載でも運用可能。

### 運用計画の参照先
- 運用計画や次アクションの確認は `docs/context/STATUS.md` を参照する。

## Owner Profile (Stable Context)
- Language: 日本語
- Domain baseline: 対象ドメインの実務知識あり
- Technical baseline: 非エンジニア。コード全文より「何を/なぜ/影響範囲」を先に把握したい
- Communication preference: 結論先出し + 次アクション明確 + 専門語は必要最小限
- Explanation depth: 実装意図と変更点の説明を重視

更新ルール:
- 本人が明示した内容のみ更新する（推測禁止）
- 同傾向が複数セッションで再現したときに固定化する
- 更新時は `DECISIONS.md` 相当に `D-YYYYMM-xxx` で1件記録する

## Delivery Rule
- GUI/UXに影響する実装を行った場合、最終回答に `GUIで確認してほしい箇所` を必ず明示する。
- `GUIで確認してほしい箇所` には、画面名・操作手順・期待結果を最低1件以上含める。
- GUI確認が不要な変更（内部処理/ドキュメントのみ等）の場合は、最終回答に `GUI確認不要` と理由を明記する。
- ユーザーが停止を明示しない限り、変更作業は `commit` と `git push origin <current-branch>` までを原則セットで完了する（認証/権限エラー時は失敗理由と再実行コマンドを共有する）。

## Security Baseline
- APIキー、token、cookie、資格情報、個人情報をコミットしない。
- `.env` 相当は作らない/参照しない。
- データ取得元は公的公開統計を原則とする。

## Update Policy
- 仕様外の挙動は既存仕様として断定せず、新仕様提案として扱う。
- 既存仕様の変更時は `docs/context/DECISIONS.md` を更新し、`docs/spec_*.md` に反映する。
- 変更は最小差分で行い、ロールバック可能性を維持する。


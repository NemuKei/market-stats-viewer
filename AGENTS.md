# AGENTS — market-stats-viewer

## 0) この文書の目的
ChatGPT / Codex にこのリポジトリの前提と運用ルールを固定し、
「推測で暴走」「参照齟齬」「秘密情報混入」を防ぐ。

## 1) Single Source of Truth（唯一の正）
- 仕様の唯一の正：`docs/spec_*.md`
- 決定事項：`docs/decision_log.md`（仕様ではない。仕様反映の追跡用）
- 引継：`docs/handovers/`
- スレッドログ：`docs/thread_logs/`

## 2) 推測禁止（品質ゲート）
- 判断に必要なファイルが無い場合は **推測で進めず、要求して止まる**
- 仕様に書いていない挙動は **新仕様として提案**し、既存挙動として断定しない

## 3) セキュリティ / 公開リポジトリ前提
- APIキー、token、cookie、資格情報、個人情報を **絶対にコミットしない**
- `.env` 相当は作らない/参照しない
- 取得元は原則「公的に公開されている統計」に限定する

## 4) 実装方針（このrepoのスケールに合わせた最小）
- Python 3.11
- 依存は `requirements.txt` に固定
- 更新処理は `scripts/` に集約（Streamlit側は表示に集中）
- データは `data/market_stats.sqlite` と `data/meta.json`

## 5) 出力ルール（AIに依頼するとき）
- 変更依頼を受けたら、対象ファイルの **全文置換**で提示する（レビューしやすくする）
- docs更新は「specが唯一の正」を崩さない
- 既存仕様の変更は `docs/decision_log.md` に決定事項を追記し、specにも反映する

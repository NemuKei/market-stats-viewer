---
name: dictionary-maintenance
description: event_signals の artist/venue 辞書を定期メンテする。未解決候補の抽出、aliases 反映、名称変更時の処理、Wikidata更新方針の確認まで行う。
---

# Purpose
artist/venue の表記ゆれを継続的に抑え、会場公式とニュースの表示名を揃える。

# When to use / When NOT to use
- When to use:
  - `update_event_signals_data` 実行後に未解決候補を点検するとき
  - `data/venue_aliases.csv` / `data/artist_registry.manual.csv` を更新するとき
  - 会場の正式名称変更があったとき
- When NOT to use:
  - 単発の表示調整だけで辞書更新が不要なとき
  - 辞書ルールを変えずにデータ更新のみを行うとき

# Procedure
1. 最新データを反映する。
   - `uv run python -m scripts.update_event_signals_data --only starto_concert,kstyle_music --rebuild`
2. 未解決候補を抽出する。
   - `uv run python .agents/skills/dictionary_maintenance/scripts/audit_alias_candidates.py --top 20`
3. 辞書へ反映する。
   - 会場: `data/venue_aliases.csv` に alias を追加
   - アーティスト: `data/artist_registry.manual.csv` に manual entry を追加
4. 会場名変更がある場合は以下を必ず実施する。
   - `data/venue_registry.csv` の `venue_name` を新正式名へ更新
   - 旧正式名を `data/venue_aliases.csv` の `aliases_json` へ追加
   - `venue_id` は変更しない
5. 再実行して確認する。
   - `uv run python -m scripts.update_event_signals_data --only starto_concert,kstyle_music --rebuild`
   - 2. を再実行し、未解決候補が減っていることを確認
6. 仕様変更を伴う場合のみ正本を更新する。
   - `docs/spec_data.md` / `docs/spec_update_pipeline.md` / `docs/context/DECISIONS.md`

# Rules
- アーティスト辞書:
  - Wikidata の定期更新（既存 workflow）を継続する
  - `manual` は自動更新しない
- 会場辞書:
  - 正本は `data/venue_registry.csv`（`venue_id` 固定）
  - `data/venue_aliases.csv` で別名吸収
  - Wikidata 自動同期は行わない（手動レビュー前提）

# Validation
- `audit_alias_candidates.py` で上位未解決候補を説明できる
- `raw_*` と正規化後表示の差分が意図どおりである
- 会場名称変更時に `venue_id` を維持している

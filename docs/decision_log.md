# docs/decision_log.md（全文置換）

# decision_log（market-stats-viewer）

> 目的：横断の決定事項を短く残す（仕様ではない。仕様の唯一の正は `docs/spec_*.md`）

## Decisions

- D-20260206-001 | アーキテクチャは「Public GitHub + GitHub Actionsでデータ生成→commit + Streamlitで表示」 | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260206-002 | データソースは観光庁の推移表Excelを優先（MVP） | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-003 | 全国（00）は推移表由来を使わず、01〜47の合算で生成する | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-004 | 表示は単一ページ（Streamlit）で「表＋グラフ」をMVPとする | status: spec_done | spec_link: docs/spec_app.md
- D-20260206-005 | 共有は make_release_zip.py によるアンカーZIP（VERSION/MANIFEST同梱）を唯一手段とする | status: spec_done | spec_link: START_HERE.md
- D-20260206-006 | make_release_zip.py の include パターンを fnmatch 前提で `scripts/**` / `docs/**` に統一し、同梱漏れ（scripts/docs）が再発しない形にする | status: spec_done | spec_link: START_HERE.md
- D-20260206-007 | 更新スクリプト実行を `python -m scripts.update_data` に統一し、`scripts` をパッケージ化して import 破綻を回避する | status: spec_done | spec_link: START_HERE.md
- D-20260206-008 | D-20260206-005（アンカーZIP運用）を START_HERE.md 整備により完了扱い（spec_done）とする | status: spec_done | spec_link: START_HERE.md
- D-20260206-009 | openpyxl での推移表パースは `read_only=False` を採用し、セル参照型パースの性能劣化を回避する | status: spec_done | spec_link: docs/spec_update_pipeline.md

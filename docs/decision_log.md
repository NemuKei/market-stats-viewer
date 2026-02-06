# decision_log（market-stats-viewer）

> 目的：横断の決定事項を短く残す（仕様ではない。仕様の唯一の正は `docs/spec_*.md`）

## Decisions

- D-20260206-001 | アーキテクチャは「Public GitHub + GitHub Actionsでデータ生成→commit + Streamlitで表示」 | status: spec_done | spec_link: docs/spec_update_pipeline.md
- D-20260206-002 | データソースは観光庁の推移表Excelを優先（MVP） | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-003 | 全国（00）は推移表由来を使わず、01〜47の合算で生成する | status: spec_done | spec_link: docs/spec_data.md
- D-20260206-004 | 表示は単一ページ（Streamlit）で「表＋グラフ」をMVPとする | status: spec_done | spec_link: docs/spec_app.md
- D-20260206-005 | 共有は make_release_zip.py によるアンカーZIP（VERSION/MANIFEST同梱）を唯一手段とする | status: spec_pending | spec_link: START_HERE.md

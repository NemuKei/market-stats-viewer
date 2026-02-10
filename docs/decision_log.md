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
- D-20260209-001 | グラフを折れ線から縦棒へ変更し、チャートモード（積み上げ/同月比較）と指標・年選択を追加する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-002 | 時系列チャートに表示内容切替（国内+海外積み上げ / 全体 / 国内 / 海外）を追加する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-003 | 地域区分に地方を追加し、地方選択時は都道府県（01〜47）の月次合算で表示する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-004 | 期間指定UIを単一の年月選択から開始/終了の年・月分離に変更する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-005 | Excelエクスポートを「データ＋Excelネイティブグラフ（時系列/年別同月比較）」に拡張する | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-006 | Excel出力の補助表重なりを防ぐため、年別補助表の開始行を動的決定し重なり検知ガードを入れる | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-007 | Excel出力の2チャートで軸IDを分離し、軸表示が不安定にならないようにする | status: spec_done | spec_link: docs/spec_app.md
- D-20260209-008 | Excel出力チャートの可読性向上として凡例配置・軸表示/目盛り・グリッド・レイアウト調整を行う | status: spec_done | spec_link: docs/spec_app.md
- D-20260210-001 | グラフに「値の種類（月次 / 年計推移=表記月起点の直近12か月ローリング）」切替を追加し、時系列・年別同月比較・Excelグラフに同一反映する。年計推移では先頭11か月を非表示とする | status: spec_done | spec_link: docs/spec_app.md

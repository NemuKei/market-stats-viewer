# START HERE — market-stats-viewer

## このリポジトリの目的
観光庁（宿泊旅行統計調査）の「月別・都道府県別 延べ宿泊者数（全体/国内/海外）」を、
Excel手作業なしで **表＋グラフ**で確認できる形にする。

- 表示：Streamlit（ローカル / Streamlit Community Cloud）
- 更新：GitHub Actions（定期）でデータ生成 → commit

## Single Source of Truth（唯一の正）
- 仕様：`docs/spec_*.md`
- AI運用ルール：`AGENTS.md`
- 決定事項ログ：`docs/decision_log.md`
- スレッド引継：`docs/handovers/`
- スレッド作業ログ：`docs/thread_logs/`

## ローカル実行（VS Code）
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/update_data.py
streamlit run app.py

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

python -m scripts.update_data
python -m scripts.update_tcd_data
streamlit run app.py
```

## データ更新（自動）
- `.github/workflows/update_data.yml` が週1で実行
- `python -m scripts.update_data` と `python -m scripts.update_tcd_data` を順に実行
- 更新があれば `data/meta.json` / `data/meta_tcd.json` / `data/market_stats.sqlite` を更新して commit/push

## 共有（アンカーZIP）
共有は `make_release_zip.py` で作ったZIPを「唯一の正」として扱う。

- コードのみ（標準）
  - `python make_release_zip.py`
- データも同梱（必要なときだけ）
  - `python make_release_zip.py --with-data`

ZIPには必ず `VERSION.txt` と `MANIFEST.txt` が入る。

## スレッド移行（最小ルール）
- 次スレ開始時は必ず「アンカーZIP（packages/の最新）」＋「handover」を添付して開始する
- 推測で進めない（不足があれば要求して止まる）

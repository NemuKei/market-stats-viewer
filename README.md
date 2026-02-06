# 宿泊旅行統計（延べ宿泊者数）ビューア

## できること
- 都道府県×月次の「延べ宿泊者数（全体/国内/海外）」を表＋グラフで表示
- 観光庁ページの「推移表（Excel）」を取得→整形→SQLiteへ保存
- GitHub Actionsで定期更新し、Streamlit Community Cloudで公開表示

## ローカル実行（VS Code）
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/update_data.py
streamlit run app.py

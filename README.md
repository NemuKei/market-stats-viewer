# 宿泊旅行統計（延べ宿泊者数）ビューア

## できること
- 都道府県または地方単位で「延べ宿泊者数（全体/国内/海外）」を表＋グラフで表示
- 時系列を縦棒で表示し、表示内容を切替（国内+海外の積み上げ / 全体 / 国内 / 海外）
- 年別の同月比較を縦棒で表示（全体/国内/海外の切替、年の複数選択）
- 開始/終了を年・月で指定して期間を絞り込み
- 観光庁ページの「推移表（Excel）」を取得→整形→SQLiteへ保存
- GitHub Actionsで定期更新し、Streamlit Community Cloudで公開表示（public repo 前提）

## ローカル実行（VS Code）
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.update_data
streamlit run app.py
```

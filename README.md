# 宿泊旅行統計（延べ宿泊者数）ビューア

## 公開URL
- 公開URL: (未設定)

## できること
- 地域区分（都道府県 / 地方）を切り替えて表示
- 地域選択
  - 都道府県: 全国（00）+ 都道府県（01〜47）
  - 地方: 北海道 / 東北 / 関東 / 中部 / 近畿（関西） / 中国 / 四国 / 九州・沖縄
- 期間選択（開始/終了の年・月）
  - 開始・終了は年/月を個別指定
  - 範囲外の年月は自動補正、開始>終了は自動入替
- 表示モード（表＋グラフ / 表のみ / グラフのみ）
- グラフ表示
  - 時系列（縦棒）: 国内+海外（積み上げ） / 全体 / 国内 / 海外
  - 年別同月比較（縦棒）: 指標（全体/国内/海外）切替 + 年複数選択
- Excelエクスポート（データ＋グラフ）
  - 現在表示中の表データを `data` シートへ出力
  - `charts` シートに時系列・年別同月比較のExcelネイティブグラフを出力
- データ更新
  - ローカル更新: `python -m scripts.update_data`
  - GitHub Actionsによる更新実行（public repo前提）

## ローカル実行（VS Code）
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.update_data
streamlit run app.py
```

# 宿泊旅行統計（延べ宿泊者数）ビューア

## 公開URL
- 公開URL: https://market-stats-viewer.streamlit.app/

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
  - 値の種類: 月次 / 年計推移（表記月起点の直近12か月ローリング）
  - 時系列（縦棒）: 国内+海外（積み上げ） / 全体 / 国内 / 海外
  - 年別同月比較（縦棒）: 指標（全体/国内/海外）切替 + 年複数選択
- Excelエクスポート（データ＋グラフ）
  - 現在表示中の表データを `data` シートへ出力
  - `charts` シートに時系列・年別同月比較のExcelネイティブグラフを出力
- データ更新
- ローカル更新: `uv run python -m scripts.update_data`
  - GitHub Actionsによる更新実行（public repo前提）

## ローカル実行（VS Code）
```bash
uv venv
# Optional (manual activate)
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
uv sync

uv run ruff check .

uv run python -m scripts.update_data
uv run python -m scripts.update_events_data
uv run python -m scripts.update_event_signals_data
uv run streamlit run app.py
```

## リリースZIP作成
- 実行コマンド: `python make_release_zip.py`
- デフォルトで `data/` フォルダを同梱
- `data/` を除外したい場合: `python make_release_zip.py --without-data`

## 全国イベント情報（会場公式）
- サイドバーの `参考情報` → `全国イベント情報（会場公式）` で表示
- 主要コンサート/イベント会場の公式サイトからイベント日程を定期収集
- データ: `data/events.sqlite`（venues + events テーブル）
- 会場定義: `data/venue_registry.csv`（1行追加で会場追加可能）
- イベント更新コマンド:
  - `uv run python -m scripts.update_events_data`
  - オプション: `--limit N`, `--only venue_id1,venue_id2`, `--verbose`

## 全国イベント速報（ニュース）
- サイドバーの `参考情報` → `全国イベント速報（ニュース）` で表示
- 速報ソース（MVP）:
  - STARTO NEWS（CONCERT）
  - Kstyle（MUSIC）
- 収集対象の前提:
  - 現状は音楽ライブ/コンサート情報を主対象とする（全ジャンル網羅ではない）
  - BCL連携時は `event_signals.sqlite` を「ニュース速報（コンサート中心）」として扱う
- データ: `data/event_signals.sqlite`（signal_sources + signals テーブル）
- 更新コマンド:
  - `uv run python -m scripts.update_event_signals_data`
  - オプション: `--only starto_concert,kstyle_music,ticketjam_events`, `--verbose`
- 保存方針:
  - ニュース本文は保存しない
  - 保存対象は掲載日時・タイトル・URL・短い抜粋（取得できる場合のみ）

## 全国イベント参考（二次流通）
- サイドバーの `参考情報` → `全国イベント参考（二次流通）` で表示
- ソース:
  - `ticketjam_events`（公開sitemap由来）
- 取得方針:
  - `MusicEvent` かつ未来開催のみ
  - 必須4項目（イベント日・会場・アーティスト・イベント名）が揃う行のみ保存
  - 初回は広め取得（bootstrap）、以後は増分巡回（新規 + 更新）

## 旅行・観光消費動向調査（TCD）拡張
- サイドバーの `統計の種類` で以下を切替:
  - `宿泊旅行統計調査`（既存）
  - `旅行・観光消費動向調査`（新規）
- TCDデータ更新コマンド:
  - `uv run python -m scripts.update_tcd_data`
- TCDメタ:
  - `data/meta_tcd.json`

## 自動更新スケジュール
- Workflow: `.github/workflows/update_data.yml`
- Trigger:
  - `schedule`: `0 3 * * 1`（毎週月曜 03:00 UTC / 日本時間 月曜 12:00）
  - `workflow_dispatch`: 手動実行可
- 実行順:
  1. `uv run python -m scripts.update_data`
  2. `uv run python -m scripts.update_tcd_data`
  3. `uv run python -m scripts.update_events_data`
- 注記:
  - 取得元サイトの構造変更等により、自動更新が遅れる/失敗する場合があります。
  - その場合は GitHub Actions の実行結果を確認し、必要に応じて手動実行してください。

## 速報データ自動更新
- Workflow: `.github/workflows/update_signals.yml`
- Trigger:
  - `schedule`: `0 */12 * * *`（12時間ごと UTC）
  - `workflow_dispatch`: 手動実行可
- 実行コマンド:
  - `uv run python -m scripts.update_event_signals_data`
- 差分がある場合のみ commit/push

## ワークスペース索引
- ワークスペース横断の正本: c:/Users/n-kei/dev/SideBiz_HotelRM/00_Admin/workspace_index.md
- 本READMEは当リポジトリ固有情報を主に記載し、横断マッピングは正本を参照してください。

## 常設コンテキスト
- `docs/context/STATUS.md`: 現在地（最新スナップショット）
- `docs/context/DECISIONS.md`: 意思決定ログ

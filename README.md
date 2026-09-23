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
PowerShell でまとめてセットアップする場合:
```powershell
.\scripts\setup.ps1
# 例: lint + 各種データ更新 + アプリ起動
# .\scripts\setup.ps1 -RunLint -UpdateData -UpdateTcdData -UpdateEventsData -UpdateEventSignalsData -RunApp
```

手動で順に実行する場合:
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

## Verification

- Focused parser regression for official-event artist/category inference:
  - `uv run python -m pytest tests/test_build_events_artist_inferred.py -q`
- Full local regression suite:
  - `uv run python -m pytest tests -q`
- Docs-only whitespace / merge-marker check:
  - `git diff --check`

## リリースZIP作成
- 実行コマンド: `python make_release_zip.py`
- デフォルトで `data/` フォルダを同梱
- `data/` を除外したい場合: `python make_release_zip.py --without-data`

## 全国イベント情報（会場公式）
- サイドバーの `参考情報` → `全国イベント情報（会場公式）` で表示
- 主要コンサート/イベント会場の公式サイトからイベント日程を定期収集
- データ: `data/events.sqlite`（venues + events テーブル）
- 会場定義: `data/venue_registry.csv`（1行追加で会場追加可能）
- 他アプリで利用する場合は、会場公式に基づく日程の基準データとして扱う
- イベント更新コマンド:
  - `uv run python -m scripts.update_events_data`
  - オプション: `--limit N`, `--only venue_id1,venue_id2`, `--verbose`

## 全国イベント速報（ニュース）
- サイドバーの `参考情報` → `全国イベント速報（ニュース）` で表示
- 速報/検知ソース（MVP）:
  - Venue Web Discovery（公式/準公式ページ本文確認済み）
  - STARTO NEWS（CONCERT）
  - Kstyle（MUSIC）
- 収集対象の前提:
  - 現状は音楽ライブ/コンサート情報を主対象とする（全ジャンル網羅ではない）
  - 他アプリで利用する場合は `event_signals.sqlite` を「ニュース速報（コンサート中心）」として扱い、会場公式データと同じ確度のイベントマスタとして扱わない
- データ: `data/event_signals.sqlite`（signal_sources + signals テーブル）
- 更新コマンド:
  - `uv run python -m scripts.update_event_signals_data`
  - オプション: `--only venue_web_discovery,starto_concert,kstyle_music`, `--verbose`
- 保存方針:
  - ニュース本文は保存しない
  - 保存対象は掲載日時・タイトル・URL・短い抜粋（取得できる場合のみ）
  - `venue_web_discovery` は公式/準公式ページ本文を根拠にした confirmed event のみ保存する
  - 本文抽出は `requests_bs4` が既定。JS生成ページや複雑HTML、アーティスト公式サイトでは optional provider の `crawl4ai` をfallbackとして使える

### Venue Web Discovery optional provider
- `crawl4ai` は必須依存ではない。通常のDB更新とLP出力生成は `uv sync --frozen` の範囲で動く
- Crawl4AIを使う環境だけ、次を実行する:
  - `uv sync --extra crawl4ai`
  - `uv run crawl4ai-setup`
  - `uv run crawl4ai-doctor`
- 抽出helper:
  - `uv run python -m scripts.venue_web_discovery_extract <official-url> --content-extractor requests_bs4`
  - `uv run python -m scripts.venue_web_discovery_extract <official-url> --content-extractor crawl4ai`
- DB更新根拠は Crawl4AI の出力そのものではなく、取得できた公式/準公式URLと本文根拠に限定する

## 外部アプリ向けイベントデータ
- 配布単位: GitHub Release `external-events-latest`
- assets: `events.sqlite`, `event_signals.sqlite`, `lp_events.json`, `manifest.json`
- `manifest.json` には生成時刻、配布元 commit、各 asset の `sha256` と `size_bytes` を保存する
- LPイベント一覧は、重複統合済みの `lp_events.json` を読む
- 外部アプリでは、`events.sqlite` を会場公式日程、`event_signals.sqlite` の `venue_web_discovery` を公式/準公式Web検知、`starto_concert` / `kstyle_music` をニュース速報として扱う
- 同一日程の統合キーは `event_date + canonical venue_name + canonical artist_name` を基本とする
- 表示source優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music`
- 詳細なデータ契約は `docs/spec_data.md` の「外部アプリ向けのイベントデータ契約」を参照

## 旅行・観光消費動向調査（TCD）拡張
- サイドバーの `統計の種類` で以下を切替:
  - `宿泊旅行統計調査`（既存）
  - `旅行・観光消費動向調査`（新規）
- TCDデータ更新コマンド:
  - `uv run python -m scripts.update_tcd_data`
- TCDメタ:
  - `data/meta_tcd.json`

## 自動更新スケジュール
- Core統計 Workflow: `.github/workflows/update_data.yml`
  - `schedule`: `0 3 * * 1`（毎週月曜 03:00 UTC / 日本時間 月曜 12:00）
  - `workflow_dispatch`: 手動実行可
  - 実行順:
    1. `uv run python -m scripts.update_data`
    2. `uv run python -m scripts.update_tcd_data`
- 会場公式イベント Workflow: `.github/workflows/update_events_official.yml`
  - `schedule`: `0 4 */3 * *`（各月1日から3日刻みで 04:00 UTC / 日本時間 13:00）
  - `workflow_dispatch`: 手動実行可
  - 実行順:
    1. `uv run python -m scripts.update_events_data --skip-artist-inference`
    2. `uv run python -m scripts.build_events_artist_inferred`
    3. `uv run python -m scripts.build_lp_events`
- 注記:
  - 取得元サイトの構造変更等により、自動更新が遅れる/失敗する場合があります。
  - その場合は GitHub Actions の実行結果を確認し、必要に応じて手動実行してください。

## 会場起点Web検知と速報データ自動更新
- Codex app automation `msv-venue-discovery` はMacBook Pro上で毎日実行し、公式/準公式本文で確認した候補を `data/venue_discovery_inbox.json` だけに書いてpushする。候補0件でも実行時刻を更新する。
- `.github/workflows/update_signals_venue_web_discovery.yml` はinboxの`main`へのpush、毎日のschedule、手動実行で起動する。inbox適用、DB更新、LP JSON生成、検証を行い、成功後にRelease公開workflowが走る。
- `.github/workflows/update_signals.yml` はニュース（STARTO/Kstyle）を12時間ごとに更新する。
- `.github/workflows/watch_automation_freshness.yml` は毎日、inboxの`run_at_utc`が3日より古い場合に失敗する。
- 詳細なinbox契約と実行順は `docs/spec_update_pipeline.md` を参照。

## ワークスペース索引
- ワークスペース横断の正本: c:/Users/n-kei/dev/SideBiz_HotelRM/00_Admin/workspace_index.md
- 本READMEは当リポジトリ固有情報を主に記載し、横断マッピングは正本を参照してください。

## 常設コンテキスト
- `AGENTS.md`: MSV作業入口、読み順、安全境界、Git/verifyの最小ルール
- `docs/context/PROJECT_CONTEXT.md`: optional upper premise layer（目的、判断原則、非目的、LP掲載優先）
- `docs/context/STATUS.md`: 現在地（最新スナップショット）
- `docs/context/DECISIONS.md`: 意思決定ログ

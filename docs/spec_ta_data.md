# spec_ta_data

## 目的
- 旅行業者取扱額（TA）の各社別内訳を SQLite に取り込み、年度総計および取得可能な月次を可視化に供給する。

## 取得元
- 索引ページ:
  - `https://www.mlit.go.jp/kankocho/tokei_hakusyo/ryokogyotoriatsukaigaku.html`
- 索引ページから年度ページを辿り、年度ページ内の「各社別内訳」Excelを取得。

## テーブル

### `ta_company_amounts`
- `fiscal_year`（例: `2024`）
- `period`（`total` または `YYYY-MM`）
- `company`
- `segment`（`overseas` / `foreign` / `domestic` / `total`）
- `amount`（単位: 千円）

## 抽出ルール（MVP）
- Excelの4ブロック（海外旅行 / 外国人旅行 / 国内旅行 / 合計）から、
  当該ファイルの主期間列（例: `2024年度`, `2025年`）の取扱額を抽出する。
- 会社名を Unicode NFKC で正規化し、半角・全角スペース、改行、タブなどの
  空白を除いた結果が `合計` または `小計` と完全一致する行は除外する。
  `合 計`、`　小　計　` なども同じ集計行として扱う。
- `JTB（6社計）` のように名称の一部に `計` を含む会社・グループ行は残す。
  判定のための正規化で、保存する会社名を置き換えない。
- 各社行のみを格納する。

## 集計・表示で使う行
- 会社集計行の判定は、取込と既存データの読取で共通の `stats.ta` を使う。
  このモジュールは Streamlit に依存しない。
- `filter_ta_company_rows` は会社の合計・小計行だけを除いたコピーを返す。
  元の列と各社の全区分を残すため、区分別内訳にも使える。
- `select_ta_amount_rows` は会社集計行を除いたうえで、金額を集計する区分を
  1つ選ぶ。「すべて」（区分未指定）のKPI・ランキングでは `segment=total`
  の各社行を使い、国内・海外・外国人の内訳をさらに足さない。
- `domestic` / `foreign` / `overseas` / `total` を明示した場合はその区分だけを使う。
  `total` がない会社について内訳の合算で補完せず、該当行なしとして扱う。
- これらの処理はDBを書き換えない。旧DBに残る会社集計行も表示前に除外するが、
  保存済みデータの修正は更新パイプラインが全原本の解析に成功したときに行う。

## メタ
- `data/meta_ta.json`
- 主な項目:
  - `source_index_url`
  - `signature`（収集した各社別内訳ExcelのURLとSHA-256の集合）
  - `extractor_version`（抽出規則の版。初期値 `1`）
  - `last_checked_at`
  - `processed_files`（`excel_url`, `fiscal_year`, `period`, `sha256`, `rows`）
  - `row_count`
  - `fiscal_years`
  - `periods`
  - `segments`
  - `unit`（`thousand_yen`）

## 互換性と再処理
- `ta_company_amounts` の列・単位・期間キーは変更しない。
  `extractor_version` はメタデータへの追加項目とする。
- `extractor_version` がない、または実装と異なるメタデータは、原本の
  `signature` が同じでも次回更新時に再解析する。全原本の解析成功後にのみ
  テーブルとメタデータを更新する。条件と失敗時の保持は
  `docs/spec_ta_update_pipeline.md` に従う。
- コードを戻しても、既に再生成した保存データは元には戻らない。
  保存データの復元が必要な場合は、既知の正常な成果物から別途復元する。


## UI Note Policy
- 一般向け注釈の共通仕様は `docs/spec_app.md` の `Common Footnote Policy (General Users)` に従う。

# spec_tcd_data - 旅行・観光消費動向調査データ仕様

## 目的
- 旅行・観光消費動向調査（TCD）の「宿泊数(8区分)別 延べ泊数」を全国で可視化するためのデータ仕様を定義する。

## ソース
- 観光庁「旅行・観光消費動向調査」ページの `集計表` Excel。
- 対象:
  - 確報（年次・四半期）
  - 2次速報（四半期）

## 抽出ルール
- Excelの `表題` シート A1 を優先し、`period_type` / `period_key` / `release_type` を判定する。
- `T06` シートで列Aが `宿泊数` の行をセクション開始とする。
- 年次ブックは最初の年次 `宿泊数` セクションだけを読む。後続の四半期詳細を年次キーへ重複格納しない。
- セクション直下8行を泊数ビンとして扱い、期間・リリース・系列・ビンの重複を保存前に拒否する。
- `T06!I2` の単位を読んで原表値とともにsource metadataへ記録する。`value` は原表の生値であり、千泊を泊へ換算した値ではない。単位不明なら既存DBを保持して更新に失敗する。
- 取得対象の系列:
  - 列B: `domestic_total`（国内旅行（合計））
  - 列E: `domestic_business`（国内旅行（出張・業務））

## 保存先
- SQLite: `data/market_stats.sqlite`
- table: `tcd_stay_nights`

## カラム
- `period_type` (`annual` / `quarter`)
- `period_key` (`YYYY` or `YYYYQ1`..`YYYYQ4`)
- `period_label`（表示用ラベル）
- `release_type`（`確報` / `2次速報`）
- `segment`（`domestic_total` / `domestic_business`）
- `nights_bin`（`1泊`..`8泊以上`）
- `value`（REAL）
- `source_url`
- `source_title`
- `source_sha256`

## メタ
- `data/meta_tcd.json`
- fields:
  - `source_page_url`
  - `last_checked_at`
  - `processed_files[]`: `{url, sha256, title_a1, source_unit, fetched_at}`。対象外ファイルでは `source_unit` を持たない。
  - `extractor_version`: 旧抽出結果を新ルールで再解析するための版番号。
  - `available_periods`
  - `note`（確報優先ルール）

## 2026-10-04 ローカル再構築検証

- 収録済み41原本を既存メタデータのSHA-256と照合し、全件で一致を確認した。抽出単位はすべて「千泊」。
- 年次2014〜2025年は各16行。旧DBの年次948行は192行になり、四半期455行は同じ値を維持した。TCD全体は1403行から647行。
- 41期間のうち8つの旧四半期には原表セルの欠損があり、14〜15行のみ。公開表示側は16区分が揃わない期間の集計値を保留する。欠損を0に補わない。
- DBコピーで再実行の冪等性と不正入力時の既存DB保全を確認し、バックアップを保持して隔離コピーに反映した。公開・main統合はこの検証に含まない。

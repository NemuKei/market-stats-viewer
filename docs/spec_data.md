# spec_data — データ仕様（取得/正規化/保存）

## 取得元（MVP）
- 観光庁ページから「推移表（Excel）」をダウンロードする
- シート：
  - 延べ宿泊者数（総数）：`1-*`
  - 日本人延べ宿泊者数：`2-*`
  - 外国人延べ宿泊者数：`3-*`
- 観光庁の現行ファイルでは当年分が `1-1/2-1/3-1`、過去年分が `旧1-2/旧2-2/旧3-2` に分かれている。
- 取得スクリプトは固定シート名を前提にせず、数値プレフィックスで current / legacy の両方を解決して結合する。

## 正規化（RAW）
### キー
- ym：YYYY-MM
- pref_code：00（全国）, 01〜47（都道府県）
- pref_name：都道府県名 / 全国

### 値
- total：延べ宿泊者数（総数）
- jp：日本人延べ宿泊者数
- foreign：外国人延べ宿泊者数

## 全国の扱い（ズレ耐性）
- 推移表に全国行があっても、MVPでは **アプリ側生成を正**とする
  - 01〜47の合算で pref_code=00 を生成
  - 推移表由来の00行は採用しない（あれば除外する）

## 保存先
### SQLite
- path：`data/market_stats.sqlite`
- table：`market_stats`
- columns：
  - ym TEXT
  - pref_code TEXT
  - pref_name TEXT
  - total REAL
  - jp REAL
  - foreign REAL
- index：
  - ym
  - pref_code

### meta.json
- path：`data/meta.json`
- fields（例）：
  - source_page_url
  - source_xlsx_url
  - source_sha256
  - fetched_at_utc
  - rows
  - min_ym
  - max_ym

## 追補（2026-02-18）宿泊施設種別 客室稼働率
### 追加データセット
- source sheet: `4-*`（都道府県別、宿泊施設タイプ別 客室稼働率 推移表（月別））
- 観光庁の現行ファイルでは当年分が `4-1`、過去年分が `旧4-2` に分かれている。
- 取得スクリプトは current / legacy の両方を結合して時系列を再構成する。
- scope: 全国（`全 国`）のみを採用
- grain: `ym x facility_type`
- value: `occupancy_rate`（%）

### SQLite 追加テーブル
- table: `stay_facility_occupancy`
- columns:
  - `ym` TEXT
  - `facility_type` TEXT
  - `occupancy_rate` REAL
- index:
  - `ym`
  - `facility_type`

### meta.json 追加フィールド
- `pipeline_version`
- `facility_occupancy_rows`
- `facility_occupancy_min_ym`
- `facility_occupancy_max_ym`

## 追補（2026-02-18）宿泊施設種別 客室稼働率（改）
- 対象は全国（00）に加えて都道府県（01-47）を保持する。
- `stay_facility_occupancy` テーブル列:
  - `ym`, `pref_code`, `pref_name`, `facility_type`, `occupancy_rate`
- UI では全国/都道府県を切替できる前提データとする。

## 追補（2026-02-22）イベントハブ
- SSOT: `data/events.sqlite`（既存の market_stats.sqlite とは分離）
- テーブル `venues`（会場マスタ）:
  - `venue_id` TEXT PK, `venue_name`, `pref_code`, `pref_name`, `capacity`,
    `official_url`, `source_type`, `source_url`, `config_json`, `is_enabled`,
    `last_signature`, `created_at_utc`, `updated_at_utc`
- テーブル `events`（イベント本体）:
  - `event_uid` TEXT PK, `venue_id` FK, `title`, `start_date`, `start_time`,
    `end_date`, `end_time`, `all_day`, `status`, `url`, `description`,
    `performers`, `artist_name_resolved`, `artist_confidence`, `capacity`,
    `source_type`, `source_url`, `source_event_key`, `data_hash`,
    `first_seen_at_utc`, `updated_at_utc`
- `event_uid` 規約: `{venue_id}:{source_event_key}` or `{venue_id}:h:{sha256[:16]}`
- `capacity`: イベント固有があればそれ、なければ会場キャパを COALESCE で利用
- 会場定義: `data/venue_registry.csv`（1行=1会場、追加は1行追加のみ）
- `artist_name_resolved`: BCL/表示向けの解決済みアーティスト名（`performers` は取得元生値を保持）
- タイトル先頭の短い英字単語だけでは出演者を確定しない。6文字以下の英数字aliasは、名称全体との一致、明示的な出演者表記、または名称に続く公演表記を要する。会場語だけでは根拠にしない。例: `LOVE JAZZ TIME` の `LOVE`、`IDOL RUNWAY COLLECTION` の `IDOL` は未解決とし、`LOVE LIVE` や `HANA 1st LIVE TOUR` は公演表記を照合する。
- 辞書照合の修正時は `events_artist_inferred.csv` と解決済み列を再計算し、未解決の旧推定名を残さない。取得元の `performers`、元イベント行、初回取得日時は保持する。例: `水谷千重子の宴ジョインコンサート2026` の旧推定 `ジョイ` は、公式表記で追加した辞書名 `水谷千重子` へ訂正する。表示名の訂正に伴ってLPの統合キー・件数が変わり得るため、JSON再生成・manifest検証・利用側表示確認を同時に行う。保存shapeやsource優先順位は変更しない。ロールバックは照合コード・辞書・導出dataを同じ検証済みrevisionへ戻し、Releaseを再生成する。
- `artist_confidence`: `source` / `source_normalized` / `high` / `medium` / `low`

### 外部アプリ向けのイベントデータ契約
- 外部アプリが利用する配布単位は GitHub Release `external-events-latest` の `events.sqlite` / `event_signals.sqlite` / `lp_events.json` / `manifest.json` とする。
- `data/venue_discovery_inbox.json` はCodex Automationが書く入力ファイルであり、Release assetではない。`schema_version=1`、`run_at_utc`、`automation_id`、`candidates`、`rejected` を持ち、候補が0件でも実行時刻を更新する。候補の項目と検証条件は `docs/spec_update_pipeline.md` に従う。
- `manifest.json` は配布ファイルの鮮度と同一性を確認するためのメタデータであり、利用側は `generated_at_utc`、各 asset の `sha256`、`size_bytes` を確認できる。
- LP向けイベント一覧は、重複統合済みの `lp_events.json` を読む。LP側で同じsource priorityを再実装しない。
- `lp_events.json` のpayloadには `ticketjam_policy`、`discovery_source_ids`、`ticketjam_promoted_held_records`、`summary.ticketjam_*` を含めない。国内所在地を確定できない掲載候補は `location_held_records` にsource_id/record_id/reasonを残し、`summary.location_held_record_count` に件数を保持する。
- `lp_events.json` の通常生成は、生成基準日以降の開催予定に加え、開催終了日が基準日の90日前以降であるイベントを含める。
  - `history_window_days=90` と `history_start_date` をpayloadへ保持し、外部アプリはこの範囲を「直近の開催済みイベント」として扱う。
  - 過去分は元DBに残る公開情報の範囲に限り、sourceごとの保存方針も異なるため、網羅的なイベントアーカイブとは表現しない。
- 外部アプリは、次の3層を同じ意味のイベント情報として混ぜない。
  - `events.sqlite`: 会場公式サイトまたは会場公式に準じる公開スケジュールから取得した日程。会場別の定期予定表として扱う。
  - `event_signals.sqlite` の `venue_web_discovery`: Codex Automation が公式/準公式ページ本文を根拠確認した大型会場イベント検知。LP掲載候補として扱う。
  - `event_signals.sqlite` の `starto_concert` / `kstyle_music`: ニュース記事または公式に近い告知ページから抽出した速報。興行決定や追加公演の早期検知に使う。
- 同一イベントのLP表示source優先順位は `official_events > venue_web_discovery > starto_concert/kstyle_music` とする。
- 公式／準公式の延期・中止が下位sourceの開催予定を抑止する状態契約と `summary.suppressed_event_count` は、`docs/spec_event_status.md` を正本とする。
- 外部アプリが「確定日程」として優先表示する場合は、まず `lp_events.json` を使う。元DBを直接使う場合も、同一日程が公式側に存在する場合は公式側を優先する。
- 外部アプリが速報性を重視する場合は、`event_signals.sqlite` を使ってよい。ただし `source_id` ごとの性質を表示または内部判定に残し、公式/準公式Web検知とニュース由来を同じ信頼度として扱わない。
- `lp_events.json` の同一イベント判定は、次の2段階とする。
  1. 厳密統合: `event_date + canonical venue_name + canonical artist_name`
  2. 補助統合: 厳密統合後も分かれたグループのうち、`event_date` とcanonical会場が同じで、開始時刻が矛盾せず、正規化タイトルが完全一致するか、双方8文字以上かつ `difflib.SequenceMatcher` の類似度が `0.80` 以上のもの
  - 補助統合はcanonical会場の完全一致だけを使い、会場名の文字列類似だけでは統合しない。
  - タイトルはUnicode NFKCとcasefoldを適用し、空白、引用符、括弧、句読点、ハイフンなど表示差の記号を除く。日本語、英数字、長音記号は保持する。
  - 開始時刻はUnicode NFKC後の非空値を比較し、両方に値がある場合は一致したときだけ統合する。片方または両方が空なら矛盾なしとする。
  - 補助統合はsource priority、`updated_at_utc`、`record_id` で決まる代表グループを基準にする。全参加グループが同じ代表グループへ直接一致し、最終グループ内の非空開始時刻が1種類以下の場合だけ統合する。A-B、B-Cだけの連鎖一致ではA-Cを統合しない。
  - 開始時刻が空の代表グループが複数の異なる非空開始時刻へ同時に一致する場合は、任意の時刻を選ばず生成を停止する。
  - 補助統合後の `event_key` は代表グループのキーを使い、入力順を変えても結果を変えない。
- 厳密キー内に異なる非空開始時刻がある場合は、補助統合より前に開始時刻ごとの公演へ分割する。
  - 開始時刻が競合しない既存グループの `event_key` は変えない。
  - 分割対象だけ、従来の厳密キーと正規化開始時刻から決定的な時刻付き `event_key` を生成する。
  - 同じ厳密キーに開始時刻が空のレコードもある場合、そのレコードは各時刻別公演の `supporting_sources` に保持する。表示元のレコードに時刻がなくても、出力の `event_start_time` には時刻別公演の一意な開始時刻を使う。
  - `events.sqlite` 側の `event_date` は `events.start_date` を使う。
  - `events.sqlite` 側の `canonical artist_name` は `artist_name_resolved` を優先し、空の場合のみ `performers` を使う。
  - `event_signals.sqlite` 側の `event_date` / `canonical venue_name` / `canonical artist_name` は `signals.labels_json` の `event_start_date` / `venue_name` / `artist_name` を使う。
- `lp_events.json` は上記判定で同一イベントを統合し、補助統合と開始時刻分割の後に延期・中止抑止とsource priorityを適用する。表示に使うsourceを `display_source_id`、下位根拠を `supporting_sources` として保持し、元DB行は削除しない。
- `lp_events.json.summary` は既存項目に加え、次を保持する。
  - `supplemental_merged_group_count`: 補助統合が発生した最終イベント数
  - `supplemental_merged_record_count`: 補助統合によって表示行ではなくsupporting sourceになった厳密グループ数
  - `start_time_split_group_count`: 異なる非空開始時刻により分割した従来の厳密グループ数
  - `start_time_split_event_count`: 開始時刻分割によって増えた公演数
- この変更のbeforeは厳密キーだけによる統合、afterは開始時刻分割を含む2段階統合である。既存fieldは削除・改名せず、追加summaryは後方互換とするため `schema_version=1` を維持する。consumer側の移行作業は不要で、`lp_events.json` の再生成だけをforward migrationとする。rollbackは実装と生成JSONを同じrevisionへ戻し、DBと旧pathは変更・削除しない。
- 外部アプリがデータ品質を判断する場合、少なくとも次の情報を保持する。
  - `source_id`: `events.sqlite` 由来か、公式/準公式Web検知か、ニュース由来かを判定する。
  - `url`: 利用者が元ページで確認するための参照先。
  - `updated_at_utc` または `first_seen_at_utc`: データ更新または初回検知の時刻。
  - `raw_artist_name` / `raw_venue_name`: `event_signals.sqlite` で正規化前の表記確認が必要な場合に使う。
- イベント文字列の品質契約:
  - `title`、`artist_name`、`raw_artist_name`、`venue_name`、`raw_venue_name`、`pref_name`、`event_category` は Unicode replacement character、禁止control character、または高確度なUTF-8誤decodeを含んではならない。
  - Cyrillic、絵文字、アクセント付きLatin文字、日本語の波ダッシュ・引用符などは、それ単独では不正と判定しない。
  - 品質不良を検出したレコードは自動再変換しない。producer側で保存を停止し、source URLとfield名を含むエラーとして扱う。
  - `build_lp_events` は入力DBをpreflightし、品質不良があれば既存の `lp_events.json` を上書きしない。
  - 外部アプリは配布assetのshape/hash検証に加え、同じ最低限の文字品質検査をconsumer防御として行ってよい。
- 外部アプリ向けの利用例:
  - LPイベント一覧: `lp_events.json` を使い、表示sourceとsupporting sourceをそのまま利用する。
  - BCL などの需要予測支援: `events.sqlite` を基準にし、`event_signals.sqlite` と `lp_events.json` は追加検知と早期注意喚起に使う。
  - イベント監視ダッシュボード: 3層を別ラベルで表示し、会場公式日程、公式/準公式Web検知、ニュース速報を分けて比較する。
  - 辞書メンテナンス支援: `raw_*` と canonical 名の差分、未解決ログを使って artist/venue 辞書候補を抽出する。

## 追補（2026-02-23）イベント速報/参考シグナル
- SSOT: `data/event_signals.sqlite`（`events.sqlite` とは分離）
- 対象範囲（BCL向け注記）:
  - 収集ソースは `venue_web_discovery` / `starto_concert` / `kstyle_music`
  - `venue_web_discovery` は公式/準公式ページ本文確認済み、`starto_concert` / `kstyle_music` はニュース由来
  - 全カテゴリ横断の網羅DBではない（野球/その他イベントの網羅は目的外）
- 保存方針:
  - 本文は保存しない（ニュース全文のDB保存禁止）
  - 保存対象は `掲載日時 / タイトル / URL / 短い抜粋（一覧で取得できる場合のみ）`
  - `venue_web_discovery` は `labels_json` に `event_start_date`、`event_end_date`、`venue_name`、`raw_venue_name`、`artist_name`、`raw_artist_name`、`event_category`、`source_class`、`confidence`、`evidence_url`、`evidence_snippet` を保存する
  - `venue_web_discovery` の `source_class` は `venue_official` / `artist_official` / `promoter_official` / `ticket_official` に限定する
  - `venue_web_discovery` の `content_extractor` は `requests_bs4` / `crawl4ai` / `browser` のどの方法で本文・公式公演表を確認したかを示す監査用ラベルであり、DB採用根拠そのものではない

### テーブル: `signal_sources`
- `source_id` TEXT PRIMARY KEY
- `source_name` TEXT NOT NULL
- `source_url` TEXT NOT NULL
- `source_type` TEXT NOT NULL
- `config_json` TEXT
- `is_enabled` INTEGER NOT NULL DEFAULT 1
- `last_signature` TEXT
- `created_at_utc` TEXT NOT NULL
- `updated_at_utc` TEXT NOT NULL

### テーブル: `signals`
- `signal_uid` TEXT PRIMARY KEY（`sha256(source_id + url)`）
- `source_id` TEXT NOT NULL
- `published_at_utc` TEXT NOT NULL（ISO8601 Z）
- `title` TEXT NOT NULL
- `url` TEXT NOT NULL
- `snippet` TEXT
- `score` INTEGER NOT NULL DEFAULT 0
- `labels_json` TEXT
- `content_hash` TEXT NOT NULL
- `first_seen_at_utc` TEXT NOT NULL
- `updated_at_utc` TEXT NOT NULL

### Index
- `signals(published_at_utc)`
- `signals(source_id)`

## 追補（2026-02-27）イベント名辞書の正規化
- 目的:
  - 会場公式（`events.sqlite`）とニュース（`event_signals.sqlite`）で、同一会場/同一アーティストの表記を揃える。
- 正規化の保存方針（`signals.labels_json`）:
  - `artist_name` / `venue_name`: 正規化後の表示名を保持
  - `raw_artist_name` / `raw_venue_name`: 取得元の原文を保持（監査・辞書更新用）
- アーティスト辞書:
  - 入力ソース: `artist_registry.seed.csv` + `artist_registry.jp.seed.csv` + `artist_registry.manual.csv`
  - マージ優先順: `seed -> jp.seed -> manual`（後勝ち）
- 会場辞書:
  - 正本: `data/venue_registry.csv`（`venue_id` 固定）
  - 別名辞書: `data/venue_aliases.csv`
  - 解決優先順: `venue_registry` の正式名 + `venue_aliases` の別名（`venue_id` 単位で後勝ち）
  - 味の素スタジアムと国立競技場（MUFGスタジアム）は別施設。`mufg_stadium` は既存ID互換のため名称を残すが、取得元・実体は味の素スタジアムでありcanonical名も `味の素スタジアム` とする。`MUFGスタジアム` / `MUFG STADIUM` の別名は `national_stadium`（canonical `国立競技場`）だけに対応させる。2026-09-08の誤対応訂正ではvenue ID・event UIDを保持し、会場マスターとLPを再同期する。元候補に会場不一致が残る場合は公式確認まで非掲載とする。根拠: [味の素スタジアム施設案内](https://www.ajinomotostadium.com/overview/stadium.php)、[MUFGの施設表記](https://www.mufg.jp/profile/japan_rugby_league_one/mufgonepark/index.html)。
  - 対象範囲:
    - 基本対象: `capacity >= 10000` の会場は、会場公式ソースの実装有無に関わらず辞書へ保持する。公式取得未対応でも `is_enabled=0` の辞書用途で先行登録してよい。
    - 重点会場: `1000 <= capacity < 10000` の会場は、会場公式イベントの取得対象、または公式/準公式Web検知と辞書照合に継続的に必要な会場に限定する。
    - 原則対象外: `capacity < 1000` または capacity 不明の小規模会場は、明示的な運用要件が出るまで辞書の常設対象にしない。
- 一意性ルール:
  - 正規化キー（keep/compact）が複数 canonical に衝突する場合、そのキーは自動適用しない。
  - 自動適用は一意に解決できるキーのみ。

#### 国内所在地の完全性

公開LPのpref_nameは国内47都道府県のいずれかを必須とする。公式確認した会場の所在地が省略されている場合は会場マスターの一致する所在地だけを補う。明示値とマスターが矛盾する場合は黙って置換しない。未登録会場は公式住所に基づく明示値が必要。

国内所在地が確定できない上位sourceの行は統合入力から保留し、location_held_recordsにsource_id/record_id/reason、summary.location_held_record_countに件数を持つ。元DBは保持する。会場名らしい文字列やアーティストから所在地を推測しない。公開validatorが欠落・不正な都道府県を拒否し、公開JSONにあるのに国内検索から落ちる状態を防ぐ。

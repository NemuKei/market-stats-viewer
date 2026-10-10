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
- 会場公式DBは取得に含まれない行を自動削除しない。空取得・部分取得・会場ページの月替わりで、保存済み履歴と未来予定を失わない。取得は終了日基準の90日範囲を使い、同一UIDの公式訂正・中止はupsertで維持する。手動の加算復旧・異UID訂正の留保・rollbackは `docs/spec_update_pipeline.md` の「会場公式イベントの履歴保存」を参照する。
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
- `lp_events.json` の候補グループ判定は、次の2段階とする。属性から作る以下のキーは内部候補キーであり、公開する固定IDの訂正対応には使わない。
  1. 厳密統合: `event_date + canonical venue_name + canonical artist_name`
  2. 補助統合: 厳密統合後も分かれたグループのうち、`event_date` とcanonical会場が同じで、開始時刻が矛盾せず、正規化タイトルが完全一致するか、双方8文字以上かつ `difflib.SequenceMatcher` の類似度が `0.80` 以上のもの
  - 補助統合はcanonical会場の完全一致だけを使い、会場名の文字列類似だけでは統合しない。
  - タイトルはUnicode NFKCとcasefoldを適用し、空白、引用符、括弧、句読点、ハイフンなど表示差の記号を除く。日本語、英数字、長音記号は保持する。
  - 開始時刻はUnicode NFKC後の非空値を比較し、両方に値がある場合は一致したときだけ統合する。片方または両方が空なら矛盾なしとする。
  - 補助統合はsource priority、`updated_at_utc`、`record_id` で決まる代表グループを基準にする。全参加グループが同じ代表グループへ直接一致し、最終グループ内の非空開始時刻が1種類以下の場合だけ統合する。A-B、B-Cだけの連鎖一致ではA-Cを統合しない。
  - 開始時刻が空の代表グループが複数の異なる非空開始時刻へ同時に一致する場合は、任意の時刻を選ばず生成を停止する。
  - 補助統合後の内部候補キーは代表グループのキーを使い、入力順を変えても結果を変えない。
- 厳密キー内に異なる非空開始時刻がある場合は、補助統合より前に開始時刻ごとの公演へ分割する。
  - 開始時刻が競合しない既存グループの内部候補キーは変えない。
  - 分割対象だけ、従来の厳密キーと正規化開始時刻から決定的な時刻付き内部候補キーを生成する。
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

### 公開イベントの固定ID台帳

`data/event_identity_registry.json` はGit管理する内部台帳である。DB、追加API、別の公開ID項目は増やさない。上記の候補生成後、台帳で確定したIDを既存 `event_key` に設定する。SideBizはその値を既存 `event_uid` に投影するため、公開23項目とその順序は変えない。初期登録は承認済み公開1,060件の全IDをそのまま保持する。

IDの単位は1開催・公演。複数日展示は1開催、同日の昼夜別公演は別IDとする。時刻不明の旧集合行を個別公演だと断定しない。台帳は `schema_version=1`、`revision`、公開snapshotと元LPのseed hash、seed件数・ID集合・観測のhash、`events`、`relations` を持つ。観測は内部候補キー、日付・終了日・時刻・会場・出演者・タイトル、完全なsource namespace/record ID、fingerprint、active、確認根拠を保存する。fingerprintは不変IDではない。初期登録だけ、同じ公開IDかつhash/基準日/生成時刻で固定した元LPとの対応を使い、表示整形やsource IDの128文字切詰めを吸収する。以後は完全なsource IDを使う。

未変更行は、候補キーと観測属性が完全一致し、登録済みsource recordを少なくとも1つ含む場合だけ同IDになる。追加根拠だけではIDを変えない。source record、日付、類似名、URLだけから訂正・統合対応を推測しない。新規未登録行、変更候補、廃止された旧観測、矛盾する複数候補は `identity_held_records` に理由と関連ID候補を保持して公開を保留する。他の確定行は配布できる。

確認済み登録は公開URL・UTC確認時刻・理由を持つレビュー要求からだけ行う。`new` は旧IDなしで各開催へopaque IDを一度発行する。既存IDとsourceを共有する新規要求は、別開催だと確認した関連ID集合を `acknowledged_related_event_uids` に明記しない限り拒否し、その確認を関係履歴にも保存する。source共有だけでは同一/別開催を断定しない。`correction` は確定した1対1だけ旧IDを継承する。`split` は継続先が確定した子だけ旧ID、他は新ID。`merge` は確定した前身1件だけのIDまたは新IDとする。旧IDと観測履歴を残し、別イベントへ再利用しない。同一要求の再適用は何も発行しない。曖昧な対応はレビューを作らず保留を続ける。

生成中の内部payloadには `identity_registry`（schema/revision/台帳bytes SHA-256）、`identity_held_records`、`summary.identity_held_record_count` を追加する。保存するLP/Release assetでは `identity_held_records` の詳細を除外し、台帳revision/hashと保留件数だけを残す。確認待ちはprivate previewで読む。既存SideBiz public projectionはこれらを公開行に含めない。表示件数・source別件数は確定行だけを数え、統合監査件数は候補生成時点を指す。台帳欠損・不正・重複、生成中のrevision変更、全候補保留、最終行の未確認変更、書込失敗では既存LPを置換しない。候補自体の不正shape/文字品質/日付/時刻/source IDでは生成を停止し、妥当だが未確認の候補だけを保留する。実入力0件と保留0件の場合だけ0件snapshotを許す。入力DB、台帳、利用者のメモは生成から変更しない。

beforeは属性hashを公開IDに再計算する方式、afterは同じ公開fieldを台帳から供給する方式。forward migrationは初期台帳をレビュー付きcommitで保全し、掲載可能な未登録候補の新規/訂正関係を確認した上で、台帳と生成コード・LP・manifest・SideBiz生成物の対応する版を採用する。現行workflowはmainのコードを使うため、停止・backup・ID保全・公開差分の検証後、明示的な採用時だけ同版のcode/台帳/dataを反映する。欠損時の旧hash fallbackは追加しない。

未登録候補のDB履歴復旧と固定IDの確認登録を分離する。DBに復旧した公式根拠付き候補も、旧公開IDとの同一性や新規開催回が確認できるまでprivate pendingへ保持する。既公開IDの補完は、承認済み公開snapshotと同世代の元LPを固定し、SideBizの実投影で全field一致を検査する専用コマンドだけを使う。旧1,060 IDに既公開35 IDを加算する場合も初期seedのID・観測・根拠を変更しない。訂正・分割で旧観測の活動flagを変更しても、そのIDと観測を履歴から消さない。

hashは署名ではなく、偶発的な欠落・改変・版競合を検出する。relationのrequest hashは再適用の識別子で、要求全文を再構成する署名検証ではない。確認根拠とGitのレビュー済み版を正本とする。辞書更新や上位sourceへの切替で属性が変わる場合も確認待ちにし、対応する1対1訂正を確認してから同IDに戻す。曖昧候補だけ保留し他の確定行を配布する採用方針は維持し、今回、任意の件数縮小閾値や訂正batchを追加しない。

rollbackでは採用済み台帳を削除せず、既発行IDと履歴を保全し、対応するコード・台帳revision・LP/manifest・SideBiz snapshotへ一体で戻す。新しいIDを公開した後は、そのIDと観測を履歴に残すforward修正を優先し、単に古い台帳へ戻して発行済みIDを失わない。旧hash方式への黙ったfallbackはしない。利用者のメモ・履歴は別保存のまま、訂正・分割・統合・未収録で自動移動・複製・削除・合併しない。運用コマンドとlockの扱いは `docs/spec_update_pipeline.md` の固定ID節を正本とする。
### イベントデータの品質と利用側検査

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
  - `venue_web_discovery` は終了日経過、取得範囲の縮小、空結果、取得失敗を理由に保存済み行を削除しない。旧設定の `future_only=true`、`prune_missing=true`、`drop_past_events=true` でもこの保存方針を優先する。
  - 同じ `signal_uid` の公式訂正は既存UPSERTで更新し、最初の観測日時を保持する。取得漏れを中止・延期と解釈せず、明示された `event_status` の扱いは `docs/spec_event_status.md` に従う。
  - 同じ取得内の収集UID競合は保存前に拒否する。URL変更による別UIDを自動統合せず、旧行を保持する。取り込み失敗と日時の確認条件は `docs/spec_update_pipeline.md` を参照する。
  - `--rebuild` に `venue_web_discovery` を含めるとDBを開く前に失敗する。履歴の意図的な削除・復旧は通常取り込みから分離し、対象行とバックアップを確認した別の承認作業とする。
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

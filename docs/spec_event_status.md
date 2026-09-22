# spec_event_status — 公式の延期・中止によるLP表示抑止

## 目的

公式または準公式ページで延期・中止が確認されたイベントについて、下位ソースに開催予定の行が残っていても `lp_events.json` へ表示しない。

下位ソースの元データは削除せず、公式の訂正根拠と情報源の食い違いを後から確認できる状態を維持する。

## 正本と更新条件

この文書を、イベント状態、抑止権限、同一イベント判定、LP出力、Release gateの正本とする。

状態値、抑止できるsource、統合キー、`summary`の出力契約、または公開前検証を変える場合は、この文書と実装・テストを同じ変更で更新する。`docs/spec_data.md` と `docs/spec_update_pipeline.md` は詳細を重複せず、この文書を参照する。

## 対象となる状態

イベント状態は次の3値を扱う。

- `scheduled`: 通常開催。状態未指定時もこの扱いとする。
- `postponed`: 元の日程をLP表示から外す。
- `cancelled`: 対象日程をLP表示から外す。

`venue_web_discovery` の通常開催レコードでは `event_status` を省略してよい。未指定を `scheduled` と解釈することで、既存レコードの内容hashを不要に変更しない。

`postponed` または `cancelled` は明示を必須とする。`enabled: false` だけでは延期・中止とはみなさず、他ソースの表示を抑止しない。

## 根拠要件

`venue_web_discovery` が延期・中止の状態レコードを保存できるのは、既存の公式／準公式要件をすべて満たす場合に限る。

- `source_class` が `venue_official` / `artist_official` / `promoter_official` / `ticket_official` のいずれか
- イベント日、会場、アーティストまたはイベント名が特定できる
- 公式／準公式ページ本文に延期または中止の記載がある
- `evidence_url` と短い `evidence_snippet` がある

検索結果、AI概要、一般ニュース、SNS単体、二次流通単体は、延期・中止による自動抑止の根拠にしない。

## 保存方法

DB schemaは変更しない。

- `events.sqlite` の会場公式行は既存の `events.status` を使う。
- `event_signals.sqlite` の `venue_web_discovery` 行は `labels_json.event_status` を使う。
- `venue_web_discovery` の `postponed` / `cancelled` 行は、`enabled: false` であっても状態レコードとして保存する。
- Ticketjamなど下位ソースの行は物理削除しない。

延期・中止の状態レコードは、開催予定を表示するための行ではなく、同一イベントの表示を止めるための監査可能な根拠として扱う。

## 提案からの無公開取込案（PR #21）

`national_event_handoff --prepare-import` は、信頼済みLPの実key/fingerprintまたは実Ticketjam候補を起点に、開催予定から中止・延期だけを変更する案を `add_suppression` として出力する。日付・終了日・開始時刻（不明も含む）・会場・出演者・titleの一致が必要。日時訂正を混ぜた提案、未知の既存公演、別内容の既存IDへの上書きは保留する。旧開催予定行と別のevent_idを使い、元config/DB行を残す。同内容の再入力は `unchanged`。

Ticketjamの旧候補はconfirmedにせずconflictのまま保持し、最新判断の `official_suppression` に検証済み状態eventを添える。既存 `apply_reviews` が純粋な状態差と公式根拠を検証する。LP生成でconflict保留を通過できるのは、元候補snapshot/fingerprintと最新判断に一致し、UID・元key・日時・状態・会場・出演者・title・公式根拠が一致する状態行だけ。古い開催予定行、別の状態行、根拠を書き換えた行は保留する。後続判断に一致する抑止根拠がなければこの例外を適用しない。

既存LP由来では元keyとLP全体fingerprintをconfig案の内部監査項目へ保持し、Ticketjam由来と混同しない。これらはRelease fieldではない。取込案だけではruntime適用・公開を許可しない。承認後の適用前に同じbase/入力hashを再確認し、実DBコピー→LP→manifest/validatorで旧行の保持・対象非表示・別時刻の保持・古いsource再実行で復活しないことを確認する。

互換性: 任意の履歴項目を追加するだけで旧判断は有効。旧コードは新しいconflictの状態行も保留するため、コードと対応するconfig/review stateは一組で検証・適用する。失敗した案は未適用のまま破棄する。適用済みの抑止を解除する場合、コードだけを戻すと開催予定が再表示され得るため、公式根拠を再確認した状態復旧を別途審査し、LP差分を検証する。旧行・履歴は削除せず、一般訂正や抑止解除の自動移行は今回の対象外。

## 同一イベントの判定

同一イベント判定は `docs/spec_data.md` の「厳密統合 + 開始時刻分割 + 補助統合」を正本とする。本仕様では別の曖昧一致を実装しない。

開始時刻分割と補助統合が完了した最終グループに、次のいずれかの状態レコードが含まれる場合、グループ全体を `lp_events.json.events` から除外する。

- `official_events` の `postponed` / `cancelled`
- `venue_web_discovery` の `postponed` / `cancelled`

`starto_concert`、`kstyle_music`、`ticketjam_events` に状態らしい文字列があっても、それだけでは表示を抑止しない。

厳密キー内に異なる開始時刻があり、時刻なしの公式／準公式状態レコードが各時刻別公演のsupporting sourceとして引き継がれた場合は、従来の日付単位の抑止範囲を維持して各公演を抑止する。開始時刻が明示された状態レコードは、互換な時刻の最終グループだけに適用する。

処理順は `入力 -> 厳密統合 -> 開始時刻分割 -> 補助統合 -> 延期・中止抑止 -> source priorityによる表示元選択` とする。アーティスト表記が異なる下位sourceも、補助統合で同一イベントになった後に抑止判定する。

## 振替公演

延期後に新しい日程が決まった場合は、次の2つを別々に保持する。

- 旧日程: `postponed` の状態レコードとして残し、LP表示を抑止する。
- 新日程: 新しい開催日の `scheduled` レコードとして追加し、通常のsource priorityで表示する。

旧日程の状態レコードを削除して新日程へ上書きしない。

## LP出力

抑止対象イベントは `lp_events.json.events` に含めない。

`summary` には次を追加する。

- `suppressed_event_count`: 公式の延期・中止によって除外したイベントグループ数

これは既存payloadへの追加項目であり、既存フィールドの意味やshapeは変えないため `schema_version` は `1` を維持する。

## Post Malone再現ケース

対象:

- 日付: `2026-10-06`
- 会場: `Kアリーナ横浜`
- アーティスト: `Post Malone`
- 公式根拠: Live Nation H.I.P. の延期・全額払い戻し告知

期待結果:

- `venue_web_discovery` の公式状態レコードは `event_signals.sqlite` に残る。
- 同一キーの `ticketjam_events` 行もDBに残る。
- `lp_events.json.events` には旧日程を出さない。
- `summary.suppressed_event_count` が1件増える。

## 検証

最低限、次を確認する。

```bash
uv run python -m pytest \
  tests/test_venue_web_discovery_source.py \
  tests/test_build_lp_events.py
uv run python -m scripts.update_event_signals_data --only venue_web_discovery
uv run python -m scripts.build_lp_events
uv run python -m scripts.build_external_events_manifest \
  --release-tag external-events-latest \
  --output tmp/manifest.json
git diff --check
```

生成後に追加で確認する。

- Post Malone旧日程が `lp_events.json.events` に存在しない。
- Ticketjamの元行が `event_signals.sqlite` に残っている。
- 無関係なイベントの表示元と件数が意図せず変わっていない。
- 変更ファイルがコード、テスト、仕様、対象設定、予定された生成物に限定されている。

## Release gate

次をすべて満たすまで `external-events-latest` を更新しない。

- focused testsが通る。
- Post Malone旧日程の非表示を確認できる。
- 新規追加済みイベントがLP出力に残る。
- `events.sqlite` / `event_signals.sqlite` / `lp_events.json` とmanifestのhash・sizeが一致する。
- 公開assetの更新元commitを確認できる。

## 対象外

- DB schema変更
- Ticketjam行の削除
- ニュースまたは二次流通ページからの延期・中止自動推定
- fuzzy matchingの追加
- 振替日の自動探索
- Release workflow、権限、secretの変更

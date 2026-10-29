# 保存原本からの日別予定（隔離プレビュー）

`scripts.build_archival_schedule_days` はネットワーク・SQLite・通常取得workflowを使わない明示的なオフライン処理。レビュー済み分類目録、保存原本観測、現在公開snapshot、既存台帳を読み、Git repositoryの外にある指定preview-rootの `private-data` へだけ書く。入力SHA256、全原観測の所属、原本題名・会場・日付・source集合を検査する。入力との出力衝突、symlink、親directoryへの遡行、repository配下のrootは書込み前に拒否する。

## 表示単位と保持

- `schedule_day` は同じ物理会場・暦日・番組名の表示束。個々の公演・試合の統合判断ではない。原観測、source UID、記載時刻、原会場表記をprivate-planに全保存する。
- 題名はNFCと空白の連続圧縮・前後trimのみ。語境界、大文字小文字、記号、回次、昼夜、公演名の意味差を消さない。既にレビューした候補キーの互換変換は表示束判定から分離し、異なる題名が同じ旧キーになる場合は拒否して別途レビューする。
- 公演数・試合数はnull、実開催はunverified。記載時刻が開場か開演かも未確認。時刻なしはhasUnknownTimeで明示する。URLは会場calendar粒度とし、各公演の証拠と表現しない。
- 原本間の題名差はobservedTitlesへ全版を保持し、同一公演の証明としない。会場タイプ等の原本会場区分はvenueNotesへ保持し、総称会場名から館内の開催場所を断定しない。
- 原観測日時は時差付きの値をUTCへ変換し、時差なしは拒否する。`first_seen_at_utc`と`updated_at_utc`は明示UTCを要求し、文字列順ではなく時点で比較する。原題の前後空白もmetadataへ残し、会場区分の半角・全角コロンを読む。
- 複数日をまとめた曖昧日程、日付・時刻等の矛盾、取消・延期は追加しない。現在snapshotの最も古い開始日より前の単日だけが対象。原本は変更・削除しない。

## 固定IDと入出力

台帳v2だけが明示的な `record_kind=schedule_day` を持つ観測を許す。v1の既存観測・fingerprint・固定IDは変更せず、旧schemaにoccurrence fieldを追加しない。日別予定は `schedule_day:` namespaceの候補に新UUIDを一度だけ発行する。訂正・分割・統合による異なる種別へのID継承は、登録時と台帳読込時の両方で拒否する。独自メモの移動はしない。

初回要求は `reviewed-day-request.json` に保全し、copied registryとprivate-planへ履歴を残す。再実行は同じcopied registryから解決し、IDを再発行しない。変更された候補が未解決なら停止する。出力assetの台帳schema/revision/SHA256、全IDとmetadata、UTC日時、記載時刻・型・根拠種別を検査する。

既存assetとplanがある再実行では、初回の生成時刻と登録前未解決数を履歴として保ち、入力digest・台帳・行・全補足・planの一致を検査する。一致なら4出力のbytes・mtimeを保持し、不一致や不完全な出力なら上書きせず、新しい明示previewを要求する。

```sh
python -m scripts.build_archival_schedule_days \
  --preview-root /private/isolated-preview \
  --output-dir /private/isolated-preview/private-data \
  --inventory /private/inputs/case-inventory.json --expected-inventory-sha256 REVIEWED_SHA256 \
  --raw-observations /private/inputs/raw-observations.json --expected-raw-sha256 REVIEWED_SHA256 \
  --baseline /private/inputs/published-events.json \
  --base-registry /private/inputs/current-registry.json \
  --review-evidence /private/inputs/review-evidence.json
```

このcommandは公開配備・実DB復旧・実台帳採用ではない。private-plan/registry/要求/保存原本はGit・Release・公開JSONへ含めない。現行のlp_events/lp_events_all、manifest、通常workflowは変更しない。将来の採用にはv2対応codeと対応台帳を同時に検証し、日別assetの配布契約と通常更新の保持経路を別途整備する。旧readerはv2を拒否するため、旧readerだけへのrollbackで台帳を読ませない。

## 分類の訂正候補

保存日程の新規生成は `scripts.events.category.classify_event_category` を使う。材料不足は「未分類」のままにし、artist_name・公演数を補わない。すでに公開した保存日程の分類だけを見直すときは `scripts.prepare_schedule_categories` を明示実行し、旧公開資産のSHAを固定したGit外の候補を作る。元観測provenance・ID・日程・補足は保持し、分類を派生値として新しいpublic asset SHAと理由一覧でレビューする。候補はReleaseや実DBへ自動反映しない。[2026-10-29の候補と採用手順](reviews/schedule-categories-2026-10-29/README.md)を参照。

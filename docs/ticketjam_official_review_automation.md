# Ticketjam公式確認の定期運用

## 成果と責務

Ticketjamは未取得イベントの発見導線に限定する。LP生成ではTicketjamを統合入力から分離し、公式・既存速報の取得済み行だけで公演を組み立てる。公式確認のない候補は確認待ちに残し、時刻や会場を公式行へ補完しない。既存速報の利用可否は利用側の公開source policyが別途判断する。

MSVが候補抽出、根拠確認、履歴、DB、LP、manifest、Releaseを担当する。SideBiz_HotelRMは公開可能なfact fieldsと確認済みdomain/source_typeの許可、公開JSON、build、実LPを担当する。収集ロジックをSideBizへ複製しない。

この定期運用の対象は、確認済みdata/config/review stateの限定更新、検証、mainへのcommit/push、既存Release・LP workflowの実行確認。コード、依存、DB schema、権限、credential、公開field許可範囲、sourceの信頼度、営業文言は定期実行で変更しない。不明点はcandidateの保留理由へ記録する。未確認を非開催と扱わない。

## 1回の実行

1. root AGENTS.md、当文書と該当specを読み、git statusとremoteとの差を確認する。競合する未commit変更があるときは、上書き・stash・force操作せず必要な対応を報告する。cleanならmainをfast-forwardする。別branch/worktree/taskを作らない。
2. `uv run python -m scripts.build_lp_events` で当日のJapan dateのLPと候補一覧を生成する。`data/ticketjam_review_queue.json` は公開assetではない。公式昇格済みでも再確認対象を残す。
3. `uv run python -m scripts.prepare_ticketjam_review --resolve-covered --max-candidates 60 --output /tmp/ticketjam-review-plan.json` を実行する。既存上位sourceと厳密に同一の行だけを機械照合し、Webを新たに確認したとは記録しない。期日到来・内容変更・新規候補だけを選び、近い開催日と大きい会場を優先する。
4. NPB/Zeppは `uv run python -m scripts.ticketjam_official_checks --queue data/ticketjam_review_queue.json --decisions /tmp/ticketjam-auto-decisions.json --receipt /tmp/ticketjam-auto-receipt.json --max-candidates 120` で公式予定表を照合できる。日付区間、会場、公演、出演者またはイベント代表名、STARTを確認する。OPENは使わない。未一致・取得失敗をconfirmedへ変えない。queueの日付が古ければ再生成する。
5. 機械照合結果とplanを読み、未解決の候補を会場・ツアー・公式URLごとにまとめて確認する。確認済みの再チェックは保存した公式URLから始める。検索結果、一般ニュース、SNS、二次流通だけでは採用しない。通常はrequests_bs4、必要なら既存のcrawl4ai、画像化された公式公演表はブラウザの実表示を確認する。所在地は一致する会場マスターまたは公式住所で確認し、二次流通の所在地を推測で採用しない。ブラウザ観測は `content_extractor=browser` と記録し、HTML抽出成功と偽らない。文字化け、別年、開場時刻、公演日違い、中止・延期を確認する。
6. 判断JSONを作る。各行にevent_key、planのcandidate_fingerprint、status、reason、UTCのchecked_at_utc、Japan dateのnext_check_dateを持つ。statusはconfirmed/insufficient/conflict/fetch_failed/duplicate/ancillary。未調査は履歴で埋めない。confirmedはofficial_eventへ本文根拠付きの既存config形式を入れる。conflictは公式の実際の異なる値をofficial_valuesへ記録する（複数時刻は配列）。一致する値を不一致と記録しない。duplicateは対象キーと対象fingerprintを記録する。
7. `uv run python -m scripts.ticketjam_review_state --queue data/ticketjam_review_queue.json --decisions /tmp/ticketjam-decisions.json --state data/ticketjam_review_state.json --config data/venue_web_discovery_config.json --config-output /tmp/ticketjam-verified-config.json` で検証する。事前backupと具体的diffを確認してconfigへ反映する。既存config行の意味を変える場合は、確認済みの同一originに限りreplaces_config_fingerprintで変更前の完全一致を指定する。競合は止める。誤判断の訂正は履歴へ追記し、古い履歴を消さない。
8. `uv run python -m scripts.update_event_signals_data --only venue_web_discovery`、`uv run python -m scripts.build_lp_events`、`uv run python -m scripts.build_external_events_manifest --release-tag external-events-latest` を実行する。新しいconflict/ancillaryに変わったTicketjam起点の公式行はLP保留とする。中止・延期は公式のevent_statusも同期する。元Ticketjam行を消さない。
9. `uv run python -m scripts.validate_external_events --expected-as-of-date YYYY-MM-DD` とfocused testsを実行する。採用件数だけでなく、source URL、artist/event名、都道府県、昼夜分割、重複、保留、カテゴリ、期日、manifest hashesを確認する。元DBへの追加と実LP掲載を別々に数える。期待する変更以外があれば公開しない。
10. commitの署名は認証済みGitHubユーザーのnoreplyをコマンド単位で使い、端末名の自動署名を公開しない。今回の差分だけをcommit/pushし、Release workflowの実際の成功と配布assetのsha256を確認する。pushはReleaseを自動起動するため、その前に検証を完了する。raceでremoteが進んだら入力を更新して再生成し、binary DBをours/theirsで黙って選ばない。
11. 新しい公式domain/source_typeがある場合、SideBizの既存fact-only policyに今回確認した組だけを追加する。根拠はMSVのreviewと公式ページで追跡できること。新しいreuse権利を得た、許諾済みという記載はしない。既存のconditional/unknown権限表示と公開field allowlistを維持し、公式性や適用根拠に疑義があるsourceは保留する。未知domainを一律許可しない。
12. SideBizのpolicy testと限定diffを確認してcommit/pushし、既存Publish market portal workflowを実行・確認する。無関係な未commit作業は触らない。Release取込hash、公開JSON、実LPの公式リンク・件数・保留非表示を確認する。別repoのbuildや秘密情報の実装詳細をMSVへ複製しない。

## 再確認と出力

- 原則、近い開催（7日以内）は翌日、それ以外の確認済みは3日後。失敗は翌日、情報不足は最大3日後。終わった公演を定期検索し続けない。
- URLの到達だけを内容確認としない。取得失敗は最後の成功を取り消す根拠ではないが、新たな不一致は公開保留の根拠となる。
- 原文全文、Cookie、token、個人情報、ブラウザsession、巨大raw logをrepoへ保存しない。短い事実要約、evidence URL、hash、判断を保存する。
- 処理件数、公式登録、既存一致、保留、未確認残数、検証、commit、Release、公開確認を分ける。未確認残数をゼロに見せるために誤分類しない。
- 定期通知は意味のある追加・訂正・失敗・利用者対応が必要な場合だけ。変化のない確認や日付だけの差分を成功ニュースとして繰り返さない。

## 検証と復旧

focused tests: `uv run python -m pytest tests/test_ticketjam_publication.py tests/test_ticketjam_review_state.py tests/test_prepare_ticketjam_review.py tests/test_ticketjam_official_checks.py tests/test_validate_external_events.py tests/test_ticketjam_context_conflict.py -q`

公開側validatorはdiscovery policy、表示source、JSON件数・キー・日付・URL、DB integrity、manifest hash、checkout commitを検証する。失敗時は既存Releaseを上書きしない。復旧は直前の検証済みdiscovery版assetを使う。display/reviewedは移行比較用の互換modeであり、そのまま本番公開しない。

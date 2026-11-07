# イベント公開の段階別復旧案（未配備）

公開承認後の運用手順案。ここにある停止・再開・upload・復元は今回実行していない。既存Gitレビュー、repo-write/release-assets concurrency、ID台帳lock、SideBizの既存publication pauseと再採用を使用する。新しい認証・journal・分散lockは追加しない。

## 公開前に固定するもの

1. producer/consumerの期待main SHA、実Release ID、全asset ID/digest、台帳revision/SHA、4公演のIDとsource record、map/policy/baselineのSHA、進行中/待機runを記録する。予期しない更新があれば開始しない。
2. 直前の正常Releaseを、**最初のDELETEより前に**別のprivate directoryへ保存する。id-scoped asset一覧を取得し、manifestをID指定でダウンロードする。manifestが列挙する6ファイルだけを同じ一覧のasset IDで取得する。名前の重複、未知の名前、size/SHA不一致、取得中のasset一覧変更は停止。manifestもAPIのdigestと照合する。tokenや環境変数は保存しない。
3. backupはevents.sqlite、event_signals.sqlite、lp_events.json、lp_events_all.json、public_schedule_days.json、public_schedule_baseline.json、manifest.json。現在の隔離証拠にはrecovery-cases/last-good-packageとして保存・6資産検証した実バイト列がある。採用時には実Releaseへ再照合する。GitHub runner終了で失わない場所へ保存し、backupがないまま置換を始めない。
4. consumerも正常なcommitと、market_portal.json、events.json、content_freshness.json、イベント/市場の静的ページ・assets、policy、保存日程履歴のheadを固定する。履歴は新旧とも残す。詳細はSideBizのdocs/operations/publication-recovery.mdを正本とする。
5. 4公演用の移行は明示ファイルのみ。コード/workflow/test/docと、event_identity_registry.json、reviewed_event_sources.json、reviewed_event_baseline.json、lp_events.json、consumer policy/レビュー済み採用候補・要求をレビューする。**隔離producer/dataやcasesを丸ごとコピーしない。SQLite2本は変更対象外**で、実Releaseの元digest一致を条件にする。FICTIONAL、新規試験台帳revision 53、PRIVATE preview、注入済みDB、SIMULATED要求を配布しない。

## 失敗点ごとの選択

| 段階 | 検出と保持 | 再試行/復旧 |
|---|---|---|
| ID登録・LP生成前/途中 | 既存のexpected revision、入力hash、非空WAL、台帳lock、atomic write。未確認本文等はv5で旧行保持。安全に保持できないidentity変更や壊れた入力は停止 | 実行結果と台帳履歴を先に確認。同じ登録requestの再実行で別UUIDを作らない。未完了なら同世代の隔離結果を再準備し、履歴をresetしない |
| Git push前/結果不明 | remote main/対象file hashを読み取る。pushエラーだけで未実行と決めない | 到達済みなら二重適用しない。未到達で基準不変の場合だけ通常pushを再試行。競合は既存rebase_data_commitに従い、SQLite衝突をours/forceで解決しない |
| Releaseの資産置換途中 | 一括atomicではない。古いmanifestと新資産の混在やasset欠落が起こる。consumerは整合した旧イベント世代だけを使うか、検証エラーで受入済みruntimeを保持する | 全writerを確認し、単一writerで、同じ検証済みcandidateの7ファイルを最初から再送する。別runのファイルを継ぎ足さない。manifestは最後。別main/別候補へ変わっていたら停止して判断 |
| Releaseを直前へ一時復元 | 先にpublisherの新規起動と実行中runを止め、実際に止まったことを確認。Actions concurrencyだけで手動CLIとの排他が成立したとは扱わない | backupの7ファイルを元bytesで再送しmanifestを最後に置換。全size/digestと6資産の整合を確認。**GitのID台帳や新規relationは巻き戻さない**。旧Releaseの台帳metadataが旧revisionでも、それは旧公開世代の記録。再開前に新台帳を保つforward repairをレビュー |
| consumer準備中 | source asset/manifest/policy/旧runtime/保存日程historyを検査。prepareは公開runtimeを書き換えない | 同じ実Release入力から候補と既存要求を再準備。候補SHA・旧runtime SHA・policy・承認理由/時刻をGitレビュー。公開前の仮要求を流用しない |
| history作成後・runtime置換前 | 原子的なhistory directory保存の後に入力を再照合し、runtimeはatomic replace。失敗時は受入runtimeが残る | 作成済み不変historyを削除しない。同一request/候補/入力bytesなら同じ要求で再実行。入力が変わった場合は旧要求を実行せず再準備 |
| runtime置換後・commit/push前 | 同じ要求はhistory headと全bytesを照合して冪等に終了 | 再採番しない。remoteを読み、未pushの同一候補だけを通常Git運用で反映 |
| consumer公開後の途中障害 | repo commit・Pages/実JSON・source世代を別々に確認。公開検査失敗は自動rollbackを意味しない | SideBizの既存PUBLICATION_PAUSEDを承認範囲で使用。正常commitのruntime/portal/鮮度の該当項目/静的ファイル/policyを一式でforward復元。新しい不変historyと上流ID台帳は残す。鮮度を緑にするための日付変更はしない |

## 再送の具体的な順序

公開権限を持つ既存環境で、candidateまたはbackupの一方を選び、まず同じdirectory内でvalidate_external_eventsを実行する。public scheduleの3 pinsも渡す。expected commitはそのbundleのmanifest参照commitであり、現在mainへ機械的に置換しない。GH_TOKENは既存の実行環境から継承し、値をコマンドや記録へ書かない。

```sh
python -m scripts.upload_release_assets --tag external-events-latest \
  /private/validated-bundle/events.sqlite \
  /private/validated-bundle/event_signals.sqlite \
  /private/validated-bundle/lp_events.json \
  /private/validated-bundle/lp_events_all.json \
  /private/validated-bundle/public_schedule_days.json \
  /private/validated-bundle/public_schedule_baseline.json \
  /private/validated-bundle/manifest.json
```

これは承認後の操作例で、今回未実行。環境のGITHUB_REPOSITORYはNemuKei/market-stats-viewerであることを確認する。uploaderはrelease ID経由でlist/delete/upload/verifyし、422/5xxだけ既存backoffで再試行する。401/403や別世代は、権限を変えたり別認証へ切り替えたりせず止める。

復元後はrelease IDの一覧から7ファイルのdigestを再取得し、bundleと一致することを確認する。consumerでasset/manifest検証、snapshot検証、validate_historyを行う。保存日程が関係する場合、policyとhistory headが同じ受入世代を指すことを確認する。ここまで揃うまで定時publisherを再開しない。

## IDを保つforward復旧

一時的な旧Release復元と、Git上の台帳巻戻しは別である。後者はしない。4IDを一度正式に採用したら、その4IDとrelationは残す。公開後に訂正が必要なら既存apply_reviewのcorrection/merge等で履歴を進め、source mapと公開差分を再レビューする。取消ではないものをcancelledと偽らない。

v5 baselineは承認済みの公開行を保持する。新規4IDについても、明示的にレビューした完全なID集合だけをprevious-baseline/approved-idで追加する。既存行の公開内容が変わる場合、この追加専用操作は拒否する。現在DBの未確認sourceをbaselineへ一律に取り込み直さない。別世代になったら採用を止めて再準備し、本番で新規IDの登録コマンドを再実行しない。

## 隔離で確認した範囲と未確認

実uploaderをin-memory Releaseへ接続し、6資産＋manifestの各upload（削除後）で失敗を注入した。各途中packageは全資産検証で拒否。consumerは旧イベント世代だけを使うか、受入bytesを保持した。同一candidate再送と旧package完全復元を7点すべてで検証。upload成功後の応答喪失も、同じbytesの再送で重複assetなし。

consumerはhistory前・history後/runtime前・history後の入力変更の3点で失敗させ、旧runtime保持、同じ要求での復旧、再実行の冪等性、保存日程history検証、新history保持を確認した。台帳bytesは全試験で不変。

さらに現行consumerコードで正常版と4件追加版をそれぞれNode/TypeScript/Vite buildし、公開範囲の7ファイル（JSON3本、イベント/市場ページ、JS/CSS）を保存した。5か所の途中公開をファイルツリーで模擬し、JSON・静的ページ・policy・保存日程を正常版へ復元した。content_freshnessはmarket/eventsだけを戻し、別feedの進行を保持した。新historyとID台帳は不変。

実GitHubへのupload/push、workflow停止/再開、Pages/CDN、実ユーザーの検索・WebMCP、本番rollbackは未実施。ファイルツリーでの部分置換モデルは実Pagesのatomic性やCDNキャッシュ挙動の検証ではない。本番サイト全体の復旧完了と同一視しない。

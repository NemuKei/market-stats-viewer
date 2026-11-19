# 定時処理の見張り

定時処理の予定をUTCのcronから計算し、15分ごとにGitHub Actionsの実行を読みます。各枠には、予定時刻から次の予定時刻の直前までに作られた `main` の定時実行のうち、最初の1件を対応させます。残る定時実行は朝のまとめに載ります。手動実行やpushによる実行は集計から外れます。

| 観測 | 記録と知らせ |
| --- | --- |
| 作成を予定から30分までに確認 | 予定どおり |
| 予定から30分を過ぎて未作成 | 遅れ。日本時間7:00以上22:00未満ならその場で知らせる |
| 遅れた実行が作成された | 朝のまとめに遅れた秒数と結末を記載 |
| 予定から12時間を過ぎて未作成 | 朝のまとめに「まだ来ません」を1回記載 |
| 次の予定になっても未作成 | 朝のまとめに「来ませんでした」を1回記載 |
| ワークフローが停止 | 枠の知らせを抑え、朝のまとめに記載 |
| GitHubの読み取り失敗 | 失敗を日ごとに記録し、1日1回知らせる |

朝のまとめは日本時間8時台の最初の観測で作り、前日の枠と、前日以降に判明した欠落を載せます。GitHubの予定、作成、開始、完了時の更新、結末を個別に記録します。完了時刻の欄は完了状態の `updated_at` で、実際の終了時刻の近似です。公開の鮮度は任意で、設定で選んだ日付または日時だけを別表に記録します。

通知はD1で枠と通知の種類を一意にし、送信前に記録します。同じ観測で見つかった複数の知らせは1通にまとめます。HTTPで明示的に送信が拒まれた場合、最初の送信を含めて3回まで、15分以上空けて次の送信可能な観測で試します。同日の送信試行は、失敗を含めて日本時間で10回までです。超えた場合は記録し、翌朝のまとめに載せます。Slackが受け取ったか分からない通信切断や処理中断では、自動で再送せずD1の `uncertain` または `sending` に記録を残します。朝のまとめは当日中、即時通知の再試行は最初の観測から24時間以内です。

## ローカル試験

Node.js 24で実行します。追加のnpm依存はありません。HTTP応答はテスト用に差し替えます。

```sh
node --test automation/schedule-watch/test/*.test.mjs
```

## 設定の例

`config.example.json` は架空の対象です。承認後、配備側の設定で `WATCH_CONFIG` に対象を渡します。識別子 `id` は対象の履歴に使うので、別の対象に使い回さないでください。対応するcronはUTCの `分 時 * * *` または `分 時 */n * *` です。両方とも分と時は固定値です。日付の刻みは月初に戻ります。監視対象のcronを変更するときはこの設定も更新します。

任意の `freshness` では公開HTTPS URLと、取り出すフィールドをドット区切りで指定します。値は日付かタイムゾーン付き日時に限ります。各対象の `freshnessFields` に対応する項目のキーを割り当てます。指定のない対象は「対象外」と記録します。

| 変数 | 初期値と動作 |
| --- | --- |
| `WATCH_ENABLED` | `false`。停止中は読み取り・保存・通知を休止 |
| `SEND_NOTICES` | `false`。見張りを有効にしても、これがfalseなら観測と記録のみ |
| `REALTIME_NOTICES` | `true`。通知を有効にしてこの値をfalseにすると朝のまとめのみ |

配備には独立したWorker、15分ごとのCron Trigger、新しいD1、秘密の `GITHUB_READ_TOKEN` と `SLACK_WEBHOOK_URL` が必要です。GitHubの鍵は対象リポジトリだけの Actions読み取りと Metadata読み取りに絞ります。Slackの宛先は承認されたIncoming Webhookを使います。秘密はWorkerの秘密の保管場所に登録します。

Cloudflareの自動トレースは外向きのURL全体を記録するため、Slackの秘密URLを保持しないよう `observability.traces.enabled` はfalseのままにします。 [記録される項目](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/)

導入の承認後、担当者がCloudflareのプランと空きCron枠を確認し、独立したD1に `migrations/0001_init.sql` を適用します。 `wrangler.jsonc.example` を基に配備側で実際の設定を用意し、最初は通知を無効にして数日分の記録を手作業の集計と照合します。通知の有効化にも承認が必要です。停止は `WATCH_ENABLED`、通知だけの停止は `SEND_NOTICES` をfalseに戻します。

[Cloudflare Scheduled Handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/) · [D1 Worker API](https://developers.cloudflare.com/d1/worker-api/d1-database/) · [GitHub Actions REST API](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow) · [Slack Incoming Webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)

# spec_external_events_publish — 外部イベント配布の公開条件

## 位置づけ

この文書は、`.github/workflows/publish_external_events_assets.yml` の起動条件と安全境界に限った狭い正本である。公開トリガーについては、`docs/spec_update_pipeline.md` の `External Events Release Assets` 節にある従来の記述をこの文書が補足・更新する。配布assetの構成や生成処理など、それ以外の更新パイプライン契約は引き続き `docs/spec_update_pipeline.md` を正とする。

## 目的

`data/events.sqlite`、`data/event_signals.sqlite`、`data/lp_events.json` の確定済み更新を、ローカルの Codex Automation から `main` へ直接pushした場合も、個人端末の `gh` 認証に依存せず GitHub Release `external-events-latest` へ自動公開する。

## 起動条件

公開workflowは次の3経路を維持する。

1. `workflow_run`
   - `Update events official data`
   - `Update event signals data (News)`
   - `Update event signals data (Ticketjam)`
   - `Update event signals data (Venue Web Discovery)`
   - 上記が `main` で成功した場合だけ公開する。
2. `push`
   - `main` へのpushのうち、次の配布元または公開処理が変わった場合だけ公開する。
     - `.github/workflows/publish_external_events_assets.yml`
     - `data/events.sqlite`
     - `data/event_signals.sqlite`
     - `data/lp_events.json`
     - `scripts/build_external_events_manifest.py`
   - ローカルAutomationや人の端末からの直接pushを補完する。
   - workflow自身を対象に含め、初回マージ時にも現在の `main` のassetを再公開する。
3. `workflow_dispatch`
   - 障害復旧や検証時の手動再公開経路として残す。

## 公開対象

workflowは対象commitをcheckoutし、manifestをその場で再生成して、次の4 assetを `external-events-latest` へ上書きする。

- `data/events.sqlite`
- `data/event_signals.sqlite`
- `data/lp_events.json`
- `data/manifest.json`

`push` 起動時は、そのpushを発生させたcommit SHAをcheckoutする。`workflow_run` と `workflow_dispatch` では `main` をcheckoutする。

## 安全境界

- PRブランチへのpushでは公開しない。
- `workflow_run` は成功かつ `head_branch == main` の場合だけ通す。
- `push` は配布に関係するpathだけに限定し、docsや通常コードの変更だけでは公開しない。
- 公開workflowはrepoへcommitを返さないため、自身の公開処理からpushが再帰発火することはない。
- GitHub Actions内では `${{ github.token }}` を使い、個人端末の `gh auth` 状態へ依存しない。
- 同時実行は既存のconcurrency groupで直列化し、公開assetの競合を避ける。

## 検証

- workflow YAMLの構造を確認する。
- `tests/test_publish_external_events_workflow.py` で3経路、main/path制限、push時のcheckout、公開assetを回帰確認する。
- マージ後、`Publish external events assets` のpush起動が成功することを確認する。
- 公開 `manifest.json` の `source_commit_sha` がマージ後の `main` と一致し、4 assetのsize/SHA-256がmanifestと一致することを確認する。

## LP影響

`lp_impact=manifest_asset_change`

イベントの内容や表示件数はこの変更だけでは変えない。配布済みassetの鮮度が、ローカルAutomationの直接push後も自動で追随するようになる。

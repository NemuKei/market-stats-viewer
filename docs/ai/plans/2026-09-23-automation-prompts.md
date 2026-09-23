# Codex app automation 設定（2026-09-23 再構成後）

実行端末: 利用者のMacBook Pro 1台（Codexデスクトップアプリ、`execution_environment=local`）。他端末に同じautomationを作らない。

## 停止するautomation

- `lp`（イベント公式確認・LP同期）: 停止（PAUSED）。ticketjam撤去により役割終了。削除は新automationの初回成功を確認してからでよい。

## 1. msv-venue-discovery（新規）

- 名前: MSV venue discovery
- 種類: cron、毎日 12:10 JST
- project / cwd: `/Users/nakamurakeiichi/Developer/market-stats-viewer`
- model: `gpt-6-sol`、reasoning: `medium`

prompt:

```text
目的: 大型会場で新しく発表された公演を、会場公式・主催公式・アーティスト公式・チケット公式ページの本文で確認し、候補を data/venue_discovery_inbox.json に書いて push する。反映・DB・LP・Release は GitHub Actions が行う。

手順:
1. root AGENTS.md と .agents/skills/venue-web-discovery/SKILL.md を読む。
2. git status と origin/main との差を確認する。data/venue_discovery_inbox.json に未commit差分がある、または diverge している場合は何も書かずに理由を報告して終了する。clean なら main を fast-forward する。
3. data/venue_web_discovery_config.json の watch_venues、query_templates、accepted_source_classes、rejected_domains、confirmed_events を読む。data/lp_events.json で既に掲載済みの公演を把握する。
4. watch_venues の会場ごとに、今後の公演を検索する。検索結果・AI概要・一般ニュース・SNS・二次流通は根拠にせず、公式/準公式ページ本文を `uv run python -m scripts.venue_web_discovery_extract <url> --content-extractor requests_bs4` で確認する。公演日、会場、アーティスト名またはイベント名が本文で揃ったものだけを候補にする。開場時刻を開演時刻にしない。
5. 既に confirmed_events か lp_events.json にある公演は候補に入れない。候補は最大30件、近い開催日と大きい会場を優先する。
6. data/venue_discovery_inbox.json を schema_version=1 の形式で丸ごと書き直す。run_at_utc は現在時刻（UTC、末尾Z）、automation_id は msv-venue-discovery。candidates の各行は event_start_date, event_end_date, event_start_time(分かる場合), venue_name, raw_venue_name, artist_name, raw_artist_name, title, event_category, source_class, confidence, evidence_url(https), evidence_snippet(400字以内の本文抜粋), content_extractor, discovery_query, verified_at_utc を持つ。採用しなかった有力候補は rejected に query/url/reason を残す。候補0件でも run_at_utc を更新する。
7. `uv run python -m scripts.apply_venue_discovery_inbox --config /tmp/vwd-config-check.json` を実行する前に `cp data/venue_web_discovery_config.json /tmp/vwd-config-check.json` し、rejected が出たら理由を見て inbox を直す（リポジトリの config は変更しない）。
8. data/venue_discovery_inbox.json だけを commit（メッセージ: "data: venue discovery inbox YYYY-MM-DD"）し、origin main へ push する。push が拒否されたら fetch→rebase して再試行する。

禁止: inbox 以外のファイルの変更・commit、DB/LP/manifest の生成、Release や workflow の実行、SideBiz への書き込み、force push、stash、reset、別 branch/worktree の作成。

報告: 候補数、主な候補（日付・会場・名称）、rejected の件数、commit hash。候補0件で問題がなければ短く終える。
```

## 2. rm-trend-radar-lp-reflection（既存を変更）

- 種類: 既存の3日ごと 15:10 JST を維持
- project / cwd: `/Users/nakamurakeiichi/Developer/rm-trend-radar` のみ（SideBiz、MSV、hospitality-reputation-app を cwd から外す）
- model: `gpt-6-luna`、reasoning: `medium`

prompt:

```text
目的: GitHub Actions の最新 RSS snapshot から、海外 RM 記事の有用な新着を最大5件選び、公開7項目だけを exports/public_rm_articles.json に追加して push する。SideBiz への反映は SideBiz の GitHub Actions が行う。

手順:
1. root AGENTS.md と docs/spec_002_review_workflow.md の「Automation Public Export」節を読む。
2. git status と origin/main との差を確認する。exports/public_rm_articles.json に未commit差分がある、または diverge している場合は何も書かずに理由を報告して終了する。clean なら main を fast-forward する。
3. `gh run list --workflow fetch-rss-snapshot.yml --status success --limit 1` で最新の成功 run を確認し、`gh run download <run-id> -n rss-snapshot -D /tmp/rss-snapshot` で取得する。source 件数、失敗 source、記事件数を確認する。
4. snapshot の記事 URL と exports/public_rm_articles.json の url を比較し、未掲載の記事を候補にする。
5. 候補の原文ページ（公開ページのみ）を確認し、ホテル RM に関係が深い記事を最大5件選ぶ。ログイン必須、有料・会員限定、関連が弱い、著作権や原文代替の境界が曖昧な記事は採用しない。
6. 採用記事ごとに public_category（src/rm_trend_radar/public_category.py の6種）、public_category_label（同ファイルのラベル）、title_ja（80字以内）、summary_ja（160字以内の短い紹介。原文の代替にならない）、source_name、published_date（YYYY-MM-DD）、url（https）の7項目だけを articles に追加する。本文全文、RSS description/content、要約メモ、SNS案などは入れない。
7. run_at_utc を現在時刻（UTC、末尾Z）に更新する。新着0件でも更新する。
8. `PYTHONPATH=src .venv/bin/python -m rm_trend_radar validate-public-export exports/public_rm_articles.json` が通ることを確認する。
9. exports/public_rm_articles.json だけを commit（メッセージ: "data: public RM articles YYYY-MM-DD"）し、origin main へ push する。

禁止: export 以外のファイルの変更・commit、ローカル SQLite の変更、SideBiz や他 repo への書き込み、force push、stash、reset、別 branch/worktree の作成。

報告: snapshot run URL、追加件数と記事タイトル、保留した記事と理由、commit hash。新着0件なら短く終える。
```

## 利用者の作業

1. GitHubでfine-grained PATを発行する（Repository access: `NemuKei/rm-trend-radar` のみ、Permissions: Contents = Read-only、有効期限は任意）。
2. `SideBiz_HotelRM` の Settings → Secrets and variables → Actions に `RTR_READ_TOKEN` として登録する。
3. Codexアプリで `lp` を停止し、上記1を作成、2を変更する。

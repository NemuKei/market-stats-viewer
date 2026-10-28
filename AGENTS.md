# AGENTS.md

市場統計と大型イベント情報を、外部LPや需要判断向けに提供するデータの正本。SideBiz_HotelRMのLP実装・公開反映は別責務。

- 根拠は公的公開統計・会場公式/準公式ページ本文。検索結果・AI概要・news/SNS単体・二次流通単体を採用根拠にしない。
- LP用の重複統合済み一覧はdata/lp_events.json。schema/配布契約はdocs/spec_data.md、取得・更新・workflow/Releaseはdocs/spec_update_pipeline.mdが持つ。
- automationの書込範囲はdata/venue_discovery_inbox.jsonだけ。pushだけでActions・DB・Release・LP反映済みとしない。
- data/DB更新、schema、workflow dispatch、Release、live設定、依存/権限変更、SideBiz反映は明示承認が必要。
- secret、Cookie、token、PII、raw log、端末cacheをGitへ入れない。既存データを無断で削除/初期化/再解釈せず、適用済みmigrationを書き換えない。

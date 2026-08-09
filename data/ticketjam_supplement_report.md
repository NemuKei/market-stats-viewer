# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1254
- additional_unique_schedules: 6
- overlap_unique_schedules: 4
- noise_rate: 0.4
- out_of_scope_rate: 0.992
- ticketjam_category_counts: {"その他": 145, "コンサート": 901, "野球": 208}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 3 | 3 | 0 | 0.0000 | バンテリンドームナゴヤ, ヤンマースタジアム長居 |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | GLAY | 2 | 2 | 0 | 0.0000 | 北海道立総合体育センター 北海きたえーる |
| B | EXILE | 3 | 1 | 2 | 0.6667 | ベルーナドーム, 京セラドーム大阪 |
| B | 福山雅治 | 2 | 0 | 2 | 1.0000 | 京セラドーム大阪 |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |

## Inputs

- ticketjam_source_updated_at_utc: 2026-08-09T04:50:29Z
- starto_source_updated_at_utc: 2026-07-31T13:37:08Z
- kstyle_source_updated_at_utc: 2026-08-09T12:33:47Z
- events_db_modified_at_utc: 2026-08-09T12:27:09Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

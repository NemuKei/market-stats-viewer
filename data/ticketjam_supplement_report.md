# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1206
- additional_unique_schedules: 6
- overlap_unique_schedules: 4
- noise_rate: 0.4
- out_of_scope_rate: 0.9917
- ticketjam_category_counts: {"その他": 147, "コンサート": 889, "野球": 170}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 2 | 2 | 0 | 0.0000 | ヤンマースタジアム長居 |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | EXILE | 4 | 2 | 2 | 0.5000 | ベルーナドーム, 京セラドーム大阪 |
| B | GLAY | 2 | 2 | 0 | 0.0000 | 北海道立総合体育センター 北海きたえーる |
| B | 福山雅治 | 2 | 0 | 2 | 1.0000 | 京セラドーム大阪 |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |

## Inputs

- ticketjam_source_updated_at_utc: 2026-08-22T04:11:16Z
- starto_source_updated_at_utc: 2026-08-18T12:29:21Z
- kstyle_source_updated_at_utc: 2026-08-22T12:22:59Z
- events_db_modified_at_utc: 2026-08-23T00:39:48Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

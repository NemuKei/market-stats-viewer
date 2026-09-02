# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1159
- additional_unique_schedules: 6
- overlap_unique_schedules: 2
- noise_rate: 0.25
- out_of_scope_rate: 0.9931
- ticketjam_category_counts: {"その他": 139, "コンサート": 892, "野球": 128}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 2 | 2 | 0 | 0.0000 | ヤンマースタジアム長居 |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | EXILE | 4 | 2 | 2 | 0.5000 | ベルーナドーム, 京セラドーム大阪 |
| B | GLAY | 2 | 2 | 0 | 0.0000 | 北海道立総合体育センター 北海きたえーる |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |
| B | 福山雅治 | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |

## Inputs

- ticketjam_source_updated_at_utc: 2026-09-01T08:51:42Z
- starto_source_updated_at_utc: 2026-08-30T15:48:00Z
- kstyle_source_updated_at_utc: 2026-09-01T15:49:45Z
- events_db_modified_at_utc: 2026-09-02T01:54:10Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

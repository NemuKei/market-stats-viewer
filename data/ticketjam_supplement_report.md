# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1381
- additional_unique_schedules: 4
- overlap_unique_schedules: 3
- noise_rate: 0.4286
- out_of_scope_rate: 0.9949
- ticketjam_category_counts: {"その他": 86, "コンサート": 986, "野球": 309}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 5 | 2 | 3 | 0.6000 | バンテリンドームナゴヤ, 京セラドーム大阪, 東京ドーム |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | 福山雅治 | 2 | 2 | 0 | 0.0000 | あなぶきアリーナ香川, 東京ドーム |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |
| B | EXILE | 0 | 0 | 0 | 0.0000 |  |
| B | GLAY | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |

## Inputs

- ticketjam_source_updated_at_utc: 2026-06-27T06:52:10Z
- starto_source_updated_at_utc: 2026-06-25T02:19:21Z
- kstyle_source_updated_at_utc: 2026-06-27T13:14:06Z
- events_db_modified_at_utc: 2026-06-27T13:07:39Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

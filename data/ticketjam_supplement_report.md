# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1719
- additional_unique_schedules: 11
- overlap_unique_schedules: 2
- noise_rate: 0.1538
- out_of_scope_rate: 0.9924
- ticketjam_category_counts: {"その他": 135, "コンサート": 1203, "野球": 381}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 2 | 0 | 2 | 1.0000 | MUFGスタジアム |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | 福山雅治 | 7 | 7 | 0 | 0.0000 | あなぶきアリーナ香川, 日本武道館, 朱鷺メッセ 新潟コンベンションセンター, 真駒内セキスイハイムアイスアリーナ |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |
| B | EXILE | 0 | 0 | 0 | 0.0000 |  |
| B | GLAY | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| ヤンマースタジアム長居 | 4 | 4 | 0 | 0.0000 | 1 | weak_schedule |

## Inputs

- ticketjam_source_updated_at_utc: 2026-04-10T05:48:37Z
- starto_source_updated_at_utc: 2026-04-01T13:01:45Z
- kstyle_source_updated_at_utc: 2026-04-09T13:04:10Z
- events_db_modified_at_utc: 2026-04-10T05:32:16Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 2066
- additional_unique_schedules: 10
- overlap_unique_schedules: 2
- noise_rate: 0.1667
- out_of_scope_rate: 0.9942
- ticketjam_category_counts: {"その他": 149, "コンサート": 1446, "野球": 471}

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
| ヤンマースタジアム長居 | 3 | 3 | 0 | 0.0000 | 1 | weak_schedule |

## Inputs

- ticketjam_source_updated_at_utc: 2026-03-20T05:13:20Z
- starto_source_updated_at_utc: 2026-03-16T09:25:31Z
- kstyle_source_updated_at_utc: 2026-03-20T01:16:53Z
- events_db_modified_at_utc: 2026-03-20T04:56:50Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

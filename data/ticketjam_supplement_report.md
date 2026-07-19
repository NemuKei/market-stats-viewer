# Ticketjam Supplement Report

## Summary
- ticketjam_unique_schedules: 1307
- additional_unique_schedules: 3
- overlap_unique_schedules: 4
- noise_rate: 0.5714
- out_of_scope_rate: 0.9946
- ticketjam_category_counts: {"その他": 139, "コンサート": 890, "野球": 278}

## Artist Gap

| tier | artist_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | venues |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S | Mrs. GREEN APPLE | 0 | 0 | 0 | 0.0000 |  |
| S | サザンオールスターズ | 0 | 0 | 0 | 0.0000 |  |
| A | 三代目 J SOUL BROTHERS from EXILE TRIBE | 3 | 2 | 1 | 0.3333 | バンテリンドームナゴヤ, ヤンマースタジアム長居 |
| A | B'z | 0 | 0 | 0 | 0.0000 |  |
| B | 福山雅治 | 1 | 1 | 0 | 0.0000 | 東京ドーム |
| B | EXILE | 2 | 0 | 2 | 1.0000 | 京セラドーム大阪 |
| B | GLAY | 1 | 0 | 1 | 1.0000 | Zepp DiverCity(Tokyo) |
| B | Ado | 0 | 0 | 0 | 0.0000 |  |

## Venue Gap

| venue_name | ticketjam_hits | additional_hits | overlap_hits | noise_rate | official_fetch_candidate | official_gap_reason |
| --- | ---: | ---: | ---: | ---: | --- | --- |

## Inputs

- ticketjam_source_updated_at_utc: 2026-07-18T05:51:17Z
- starto_source_updated_at_utc: 2026-07-13T01:54:56Z
- kstyle_source_updated_at_utc: 2026-07-18T12:56:09Z
- events_db_modified_at_utc: 2026-07-19T01:41:44Z

## Methodology

- baseline_sources: events.sqlite, event_signals.sqlite:starto_concert, event_signals.sqlite:kstyle_music
- schedule_key: event_date + canonical venue_name + canonical artist_name
- additional_hits: Ticketjam schedule key が既存ソース baseline に存在しない件数
- noise_rate: 監視スコープ内 Ticketjam schedule のうち baseline と重複した比率
- out_of_scope_rate: Ticketjam schedule のうち監視アーティスト/会場のどちらにも当てはまらない比率

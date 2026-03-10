from __future__ import annotations

import unittest

from scripts.build_ticketjam_supplement_report import (
    ScheduleRecord,
    build_report_data,
    render_markdown,
)
from scripts.signals.artist_registry import ArtistEntry


class BuildTicketjamSupplementReportTests(unittest.TestCase):
    def test_build_report_data_counts_additional_and_overlap(self) -> None:
        ticketjam_records = [
            ScheduleRecord(
                source_id="ticketjam_events",
                event_date="2026-04-01",
                venue_name="ヤンマースタジアム長居",
                artist_name="B'z",
                pref_name="大阪府",
                event_category="コンサート",
            ),
            ScheduleRecord(
                source_id="ticketjam_events",
                event_date="2026-04-02",
                venue_name="ヤンマースタジアム長居",
                artist_name="B'z",
                pref_name="大阪府",
                event_category="コンサート",
            ),
            ScheduleRecord(
                source_id="ticketjam_events",
                event_date="2026-04-03",
                venue_name="京セラドーム大阪",
                artist_name="その他",
                pref_name="大阪府",
                event_category="コンサート",
            ),
        ]
        news_records = [
            ScheduleRecord(
                source_id="kstyle_music",
                event_date="2026-04-02",
                venue_name="ヤンマースタジアム長居",
                artist_name="B'z",
                pref_name="大阪府",
                event_category="コンサート",
            )
        ]
        official_records = []
        watched_artists = [
            ArtistEntry(
                artist_id="artist_bz",
                canonical_name="B'z",
                aliases=tuple(),
                source="manual",
                is_enabled=True,
                ticketjam_watch=True,
                ticketjam_benchmark_tier="A",
                ticketjam_watch_reason="artist_gap",
            )
        ]
        watched_venues = [
            {
                "venue_name": "ヤンマースタジアム長居",
                "ticketjam_watch": True,
                "official_fetch_candidate": True,
                "official_gap_reason": "weak_schedule",
            }
        ]

        report = build_report_data(
            ticketjam_records=ticketjam_records,
            news_records=news_records,
            official_records=official_records,
            watched_artists=watched_artists,
            watched_venues=watched_venues,
            source_updates={},
            events_db_path=__import__("pathlib").Path("missing.sqlite"),
        )

        self.assertEqual(report["summary"]["ticketjam_unique_schedules"], 3)
        self.assertEqual(report["summary"]["in_scope_unique_schedules"], 2)
        self.assertEqual(report["summary"]["additional_unique_schedules"], 1)
        self.assertEqual(report["summary"]["overlap_unique_schedules"], 1)
        self.assertAlmostEqual(report["summary"]["noise_rate"], 0.5)
        self.assertAlmostEqual(report["summary"]["out_of_scope_rate"], 1 / 3, places=4)

        artist_row = report["artist_gap"]["rows"][0]
        self.assertEqual(artist_row["artist_name"], "B'z")
        self.assertEqual(artist_row["ticketjam_hits"], 2)
        self.assertEqual(artist_row["additional_hits"], 1)
        self.assertEqual(artist_row["overlap_hits"], 1)

        venue_row = report["venue_gap"]["rows"][0]
        self.assertEqual(venue_row["venue_name"], "ヤンマースタジアム長居")
        self.assertEqual(venue_row["ticketjam_hits"], 2)
        self.assertTrue(venue_row["official_fetch_candidate"])

    def test_render_markdown_contains_sections(self) -> None:
        report = {
            "summary": {
                "ticketjam_unique_schedules": 1,
                "additional_unique_schedules": 1,
                "overlap_unique_schedules": 0,
                "noise_rate": 0.0,
                "out_of_scope_rate": 0.0,
                "ticketjam_category_counts": {"コンサート": 1},
            },
            "artist_gap": {"rows": []},
            "venue_gap": {"rows": []},
            "inputs": {
                "ticketjam_source_updated_at_utc": "",
                "starto_source_updated_at_utc": "",
                "kstyle_source_updated_at_utc": "",
                "events_db_modified_at_utc": "",
            },
            "methodology": {
                "baseline_sources": ["events.sqlite"],
                "schedule_key": "event_date + venue + artist",
                "additional_hits": "x",
                "noise_rate": "y",
                "out_of_scope_rate": "z",
            },
        }
        text = render_markdown(report)
        self.assertIn("# Ticketjam Supplement Report", text)
        self.assertIn("## Artist Gap", text)
        self.assertIn("## Venue Gap", text)


if __name__ == "__main__":
    unittest.main()

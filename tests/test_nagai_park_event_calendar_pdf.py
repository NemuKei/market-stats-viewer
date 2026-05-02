from __future__ import annotations

import unittest

from scripts.events.sources.html import (
    _extract_nagai_event_calendar_pdf_entries,
    _parse_nagai_event_calendar_layout_text,
)
from scripts.events.types import VenueRecord


class NagaiParkEventCalendarPdfTests(unittest.TestCase):
    def test_extract_event_calendar_pdf_entries_keeps_current_window(self) -> None:
        html = """
        <html><body>
          <a href="/apps/nagaipark/file/old/イベントカレンダー_2026年4月.pdf">
            2026年度4月度 イベントカレンダー
          </a>
          <a href="/apps/nagaipark/file/current/イベントカレンダー_2026年5月.pdf">
            2026年度5月度 イベントカレンダー
          </a>
          <a href="/apps/nagaipark/file/current/スポーツ施設スケジュール_5月.pdf">
            2026年度5月度 スポーツ施設スケジュール
          </a>
        </body></html>
        """

        entries = _extract_nagai_event_calendar_pdf_entries(
            html,
            "https://nagaipark.com/news/",
            min_year_month=202605,
            max_year_month=202607,
        )

        self.assertEqual(
            entries,
            [
                (
                    "https://nagaipark.com/apps/nagaipark/file/current/イベントカレンダー_2026年5月.pdf",
                    2026,
                    5,
                )
            ],
        )

    def test_parse_event_calendar_layout_text_filters_target_venue(self) -> None:
        venue = VenueRecord(
            venue_id="yanmar_stadium_nagai",
            venue_name="ヤンマースタジアム長居",
            pref_code="27",
            pref_name="大阪府",
            capacity=47816,
            official_url="https://nagaipark.com/guide/stadium/",
            source_type="html",
            source_url="https://nagaipark.com/news/",
            config_json='{"strategy":"nagai_park_event_calendar_pdf"}',
            is_enabled=True,
        )
        layout_text = "\n".join(
            [
                "1 金 11:00 THE MEAT OSAKA 2026 自由広場",
                "15:00 明治安田J1百年構想リーグ 第14節",
                "セレッソ大阪 VS アビスパ福岡 ヤンマーハナサカスタジアム",
                "3 日",
                "10:00 THE MEAT OSAKA 2026 自由広場",
                "18:00 Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜 ヤンマースタジアム長居 関連リンク",
                "4 月 18:00 Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜 ヤンマースタジアム長居",
                "ヤンマーフィールド長居",
            ]
        )

        events = _parse_nagai_event_calendar_layout_text(
            venue=venue,
            layout_text=layout_text,
            source_url="https://example.com/event-calendar.pdf",
            year=2026,
            month=5,
            seen_uids=set(),
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(
            [(event.start_date, event.start_time) for event in events],
            [("2026-05-03", "18:00"), ("2026-05-04", "18:00")],
        )
        for event in events:
            self.assertIn("Mrs. GREEN APPLE", event.title)
            self.assertIn("ゼンジン未到とイ/ミュータブル", event.title)
            self.assertNotIn("関連リンク", event.title)
            self.assertNotIn("ヤンマースタジアム長居", event.title)
            self.assertNotIn("ヤンマーフィールド長居", event.title)


if __name__ == "__main__":
    unittest.main()

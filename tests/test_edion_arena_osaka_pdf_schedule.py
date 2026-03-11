from __future__ import annotations

import unittest

from scripts.events.sources.html import (
    _extract_edion_monthly_pdf_entries,
    _parse_edion_main_arena_layout_text,
)
from scripts.events.types import VenueRecord


def _row(day: int, weekday: str, left: str, right: str = "") -> str:
    left_text = f"{day:>2} {weekday} {left}"
    right_text = f"{day:>2} {weekday} {right}" if right else f"{day:>2} {weekday}"
    return left_text.ljust(136) + right_text


class EdionArenaOsakaPdfScheduleTests(unittest.TestCase):
    def test_extract_monthly_pdf_entries_skips_past_months(self) -> None:
        html = """
        <html><body>
          <a href="/images/facilities/pdf/monthly2602.pdf">2月 行事案内</a>
          <a href="/images/facilities/pdf/monthly2603.pdf">3月 行事案内</a>
          <a href="/images/facilities/pdf/monthly2603.pdf">3月 行事案内 duplicate</a>
        </body></html>
        """

        entries = _extract_edion_monthly_pdf_entries(
            html,
            "https://www.furitutaiikukaikan.ne.jp/",
            min_year_month=202603,
        )

        self.assertEqual(
            entries,
            [
                (
                    "https://www.furitutaiikukaikan.ne.jp/images/facilities/pdf/monthly2603.pdf",
                    2026,
                    3,
                )
            ],
        )

    def test_parse_edion_main_arena_layout_text_keeps_first_arena_only(self) -> None:
        venue = VenueRecord(
            venue_id="edion_arena_osaka",
            venue_name="大阪府立体育会館（エディオンアリーナ大阪）",
            pref_code="27",
            pref_name="大阪府",
            capacity=8000,
            official_url="https://www.furitutaiikukaikan.ne.jp/",
            source_type="html",
            source_url="https://www.furitutaiikukaikan.ne.jp/",
            config_json='{"strategy":"edion_arena_osaka_pdf_schedule"}',
            is_enabled=True,
        )
        layout_text = "\n".join(
            [
                _row(1, "日", "（ 会 場 準 備 ）", "GLORIOUS GATE 2026"),
                _row(5, "木", "公 益 財 団 法 人 日 本 相 撲 協 会", ""),
                _row(8, "日", "大 相 撲 三 月 場 所 （ 初 日 ）", ""),
                _row(26, "木", "（ 会 場 後 始 末 ）", "クラブ活動"),
                _row(31, "火", "", ""),
                " " * 8 + "は 有 料 行 事 (VB=バレーボール)",
                " " * 20 + "相 愛 中 学 校 ・ 高 等 学 校",
            ]
        )

        events = _parse_edion_main_arena_layout_text(
            venue=venue,
            layout_text=layout_text,
            source_url="https://www.furitutaiikukaikan.ne.jp/images/facilities/pdf/monthly2603.pdf",
            year=2026,
            month=3,
            seen_uids=set(),
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.start_date, "2026-03-08")
        self.assertEqual(event.title, "大相撲三月場所(初日)")
        self.assertIn("monthly2603.pdf", event.url or "")


if __name__ == "__main__":
    unittest.main()

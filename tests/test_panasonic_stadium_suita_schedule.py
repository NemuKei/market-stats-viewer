from __future__ import annotations

import unittest

from scripts.events.category import classify_event_category
from scripts.events.sources.html import HtmlSource
from scripts.events.types import VenueRecord


class _DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.apparent_encoding = "utf-8"
        self.encoding = "utf-8"


class _DummySession:
    def __init__(self, html: str):
        self._html = html
        self.urls: list[str] = []

    def get(self, url: str, timeout: int = 30):
        self.urls.append(url)
        return _DummyResponse(self._html)


class PanasonicStadiumSuitaScheduleTests(unittest.TestCase):
    def test_fetch_events_parses_month_table(self) -> None:
        html = """
        <html><body>
        <table>
          <tr><th>日付</th><th>イベントスケジュール</th></tr>
          <tr>
            <th>4(水)</th>
            <td>
              <ul>
                <li>
                  <a href="https://www.gamba-osaka.net/">19:00 ～ AFCチャンピオンズリーグ2 2025/26 準々決勝 ガンバ大阪 VS ラーチャブリーFC</a>
                  <div>[お問い合わせ先] ガンバ大阪</div>
                </li>
              </ul>
            </td>
          </tr>
          <tr>
            <th>5(木)</th>
            <td>
              <ul>
                <li>試合前準備</li>
              </ul>
            </td>
          </tr>
          <tr>
            <th>15(日)</th>
            <td>
              <ul>
                <li>スタジアムツアー 締切</li>
              </ul>
            </td>
          </tr>
        </table>
        </body></html>
        """
        session = _DummySession(html)
        source = HtmlSource(session)
        venue = VenueRecord(
            venue_id="panasonic_stadium_suita",
            venue_name="Panasonic Stadium Suita",
            pref_code="27",
            pref_name="大阪府",
            capacity=40000,
            official_url="https://suitacityfootballstadium.jp/",
            source_type="html",
            source_url="https://suitacityfootballstadium.jp/schedule/",
            config_json='{"strategy":"panasonic_stadium_suita_schedule","months_ahead":0}',
            is_enabled=True,
        )

        events = source.fetch_events(venue)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.title, "AFCチャンピオンズリーグ2 2025/26 準々決勝 ガンバ大阪 VS ラーチャブリーFC")
        self.assertEqual(event.start_date[-5:], "03-04")
        self.assertEqual(event.start_time, "19:00")
        self.assertEqual(event.url, "https://www.gamba-osaka.net/")

    def test_soccer_titles_are_not_classified_as_baseball(self) -> None:
        self.assertEqual(
            classify_event_category(
                "明治安田J1百年構想リーグ ガンバ大阪 VS サンフレッチェ広島",
                "",
                "",
            ),
            "その他",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from scripts.events.sources.html import HtmlSource
from scripts.events.types import VenueRecord


class _FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        apparent_encoding: str,
        status_code: int = 200,
    ) -> None:
        self.content = content
        self.apparent_encoding = apparent_encoding
        self.encoding = "UTF-8"
        self.status_code = status_code

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding)


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requested_urls: list[str] = []

    def get(self, url: str, timeout: int = 30) -> _FakeResponse:
        del timeout
        self.requested_urls.append(url)
        return self.response


class ToyosuPitScheduleTests(unittest.TestCase):
    @staticmethod
    def _venue() -> VenueRecord:
        return VenueRecord(
            venue_id="toyosu_pit",
            venue_name="豊洲PIT",
            pref_code="13",
            pref_name="東京都",
            capacity=3103,
            official_url="https://toyosu.pia-pit.jp/",
            source_type="html",
            source_url="https://toyosu.pia-pit.jp/schedule/",
            config_json='{"strategy":"toyosu_pit_schedule","months_ahead":0}',
            is_enabled=True,
        )

    def test_fetch_events_uses_utf8_bytes_not_apparent_encoding(self) -> None:
        artist = (
            "①ぽかぽか×めざましライブ in めざましWANGANフェス "
            "②めざましライブ モナキ in めざましWANGANフェス"
        )
        subtitle = "めざましWANGANフェス～人気バラエティと夏の最強コラボ～"
        html = f"""
        <html><head><meta charset="utf-8"></head><body>
          <ul class="schedule_block">
            <li>
              <a href="../../../schedule/202604/8452.html" class="schedule_list">
                <div class="schedule_list__date"><p>08.03</p><span>MON</span></div>
                <div class="title"><p>{subtitle}</p><h3>{artist}</h3></div>
              </a>
            </li>
          </ul>
        </body></html>
        """
        session = _FakeSession(
            _FakeResponse(html.encode("utf-8"), apparent_encoding="ptcp154")
        )

        events = HtmlSource(session).fetch_events(self._venue())

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].event_uid,
            "toyosu_pit:../../../schedule/202604/8452.html",
        )
        self.assertEqual(events[0].title, f"{artist} {subtitle}")
        self.assertEqual(events[0].performers, artist)
        self.assertEqual(
            events[0].url,
            "https://toyosu.pia-pit.jp/schedule/202604/8452.html",
        )

    def test_fetch_events_rejects_non_utf8_bytes(self) -> None:
        session = _FakeSession(
            _FakeResponse(b"\x82\xa0", apparent_encoding="shift_jis")
        )

        with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
            HtmlSource(session).fetch_events(self._venue())


if __name__ == "__main__":
    unittest.main()

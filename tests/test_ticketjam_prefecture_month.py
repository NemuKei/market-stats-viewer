import unittest

import requests

from scripts.signals.sources.ticketjam import TicketjamEventsSource


class TicketjamPrefectureMonthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = TicketjamEventsSource(requests.Session())

    def test_extract_candidates_from_prefecture_month_html(self) -> None:
        html = """
<div class='l-box--p0'>
  <ul class='p-event-list'>
    <li class='p-event-list__item'>
      <a class="p-event-list__title" href="/tickets/mrsgreenapple/event/1234567"><h4>Mrs. GREEN APPLE DOME TOUR</h4></a>
      <div class='p-event-list__date'><span>2026/11/15(日) 18:00</span></div>
    </li>
    <script type='application/ld+json'>
      {"@context":"http://schema.org/","@type":"MusicEvent","name":"Mrs. GREEN APPLE DOME TOUR","startDate":"2026-11-15T18:00:00.000+09:00","location":{"@type":"Place","name":"京セラドーム大阪","address":{"@type":"PostalAddress","addressRegion":"大阪府"}},"offers":{"@type":"Offer","url":"https://ticketjam.jp/tickets/mrsgreenapple/event/1234567"},"performer":{"@type":"PerformingGroup","name":"Mrs. GREEN APPLE"}}
    </script>
  </ul>
</div>
<div class='paging clearfix m-2'>
  <div class='paging__button'>
    <ul>
      <li class='active'><span>1</span></li>
      <li><a href="/prefectures/osaka/month?events_page=2">2</a></li>
      <li><a href="/prefectures/osaka/month?events_page=5">5</a></li>
    </ul>
  </div>
</div>
"""
        candidates, total_pages = self.source._load_event_candidates_from_prefecture_month_html(
            html,
            skip_keywords=("駐車場券", "駐車券", "駐車場"),
            allowed_event_types={"Event", "MusicEvent", "SportsEvent"},
            page_param="events_page",
        )

        self.assertEqual(total_pages, 5)
        self.assertIn("1234567", candidates)
        candidate = candidates["1234567"]
        self.assertEqual(
            candidate["event_url"],
            "https://ticketjam.jp/tickets/mrsgreenapple/event/1234567",
        )
        self.assertEqual(candidate["event_start_date"], "2026-11-15")
        self.assertEqual(candidate["event_end_date"], "2026-11-15")
        self.assertEqual(candidate["event_start_time"], "18:00")
        self.assertEqual(candidate["venue_name"], "京セラドーム大阪")
        self.assertEqual(candidate["pref_name"], "大阪府")

    def test_build_prefecture_month_page_url_uses_events_page(self) -> None:
        url = self.source._build_prefecture_month_page_url(
            "https://ticketjam.jp/prefectures/osaka/month?foo=bar",
            page_number=3,
            page_param="events_page",
        )
        self.assertEqual(
            url,
            "https://ticketjam.jp/prefectures/osaka/month?foo=bar&events_page=3",
        )

        first_page_url = self.source._build_prefecture_month_page_url(
            "https://ticketjam.jp/prefectures/osaka/month?foo=bar&events_page=7",
            page_number=1,
            page_param="events_page",
        )
        self.assertEqual(
            first_page_url,
            "https://ticketjam.jp/prefectures/osaka/month?foo=bar",
        )


if __name__ == "__main__":
    unittest.main()

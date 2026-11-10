import copy
import unittest

from scripts import collect_ticket_candidates as c

HTML = "<main>TEST ROUND<br>受付期間：2026年10月13日(火)20:00～10月18日(日)23:59<br>当落発表：2026年10月21日<br>NEXT ROUND<br>当落発表：2026年12月1日</main>"
ROUTE = dict(
    source_id="test",
    url="https://niziu.com/test",
    source_class="artist_official",
    name="Test official",
    section_start="TEST ROUND",
    section_end="NEXT ROUND",
    ticket_round_id="round-1",
    event_uids=["event-a"],
)
NOW = "2026-11-10T04:00:00Z"


class TicketCollectionTests(unittest.TestCase):
    def test_scoped_dates_and_unknown_time(self):
        p = c.extract(HTML, ROUTE)
        self.assertEqual(p["application_open"]["date"], "2026-10-13")
        self.assertEqual(p["application_close"]["time"], "23:59")
        self.assertEqual(p["results"]["date"], "2026-10-21")
        self.assertIsNone(p["results"]["time"])
        self.assertEqual(p["payment_deadline"]["knowledge_status"], "unverified")

    def test_missing_scope_and_duplicate_dates_are_held(self):
        for html in [
            HTML.replace("NEXT ROUND", ""),
            HTML + HTML,
            HTML.replace("当落発表：", "当落発表：2026年10月22日 / "),
        ]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                c.extract(html, ROUTE)

    def test_ambiguous_year_and_invalid_date_are_not_guessed(self):
        for value in [
            "10月21日",
            "2026年2月30日",
            "2026年10月21日頃",
            "2026年10月21日 25:00",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                c.extract(HTML.replace("2026年10月21日", value), ROUTE)

    def test_result_range_preserved(self):
        p = c.extract(
            HTML.replace("2026年10月21日", "2026年10月21日13:00～2026年10月22日18:00"),
            ROUTE,
        )
        self.assertEqual(p["results"]["end_time"], "18:00")
        self.assertEqual(p["results"]["precision"], "range")

    def test_no_cross_year_inference(self):
        html = HTML.replace(
            "2026年10月13日(火)20:00～10月18日(日)23:59",
            "2026年12月30日20:00～1月3日23:59",
        )
        with self.assertRaises(ValueError):
            c.extract(html, ROUTE)

    def test_fetch_failure_retains_previous_observation_and_no_raw_content(self):
        first = c.collect([ROUTE], {"event-a"}, NOW, fetch=lambda _: HTML)
        original = copy.deepcopy(first)
        failed = c.collect(
            [ROUTE],
            {"event-a"},
            "2026-11-11T04:00:00Z",
            previous=first,
            fetch=lambda _: (_ for _ in ()).throw(c.FetchError("access_denied")),
        )
        self.assertEqual(failed["observations"], first["observations"])
        self.assertEqual(failed["results"][0]["status"], "access_denied")
        self.assertEqual(first, original)
        self.assertNotIn("html", str(first))
        self.assertNotIn("TEST ROUND", str(first))

    def test_unchanged_and_changed_history(self):
        first = c.collect([ROUTE], {"event-a"}, NOW, fetch=lambda _: HTML)
        second = c.collect(
            [ROUTE],
            {"event-a"},
            "2026-11-11T04:00:00Z",
            previous=first,
            fetch=lambda _: HTML,
        )
        self.assertEqual(second["results"][0]["status"], "unchanged_requires_review")
        self.assertEqual(len(second["observations"]), 1)
        third = c.collect(
            [ROUTE],
            {"event-a"},
            "2026-11-12T04:00:00Z",
            previous=second,
            fetch=lambda _: HTML.replace("10月21日", "10月22日"),
        )
        self.assertEqual(third["results"][0]["status"], "changed_requires_review")
        self.assertEqual(len(third["observations"]), 2)
        self.assertFalse(third.get("review"))

    def test_unresolved_events_prevent_candidate(self):
        result = c.collect([ROUTE], set(), NOW, fetch=lambda _: HTML)
        self.assertEqual(result["results"][0]["status"], "unresolved_events")
        self.assertFalse(result["observations"])

    def test_unexpected_redirects_and_hosts_disallowed(self):
        for url in [
            "http://niziu.com/test",
            "https://niziu.com.evil.test/",
            "https://user:pass@niziu.com/",
            "https://niziu.com:444/",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                c.validate_url(url)
        self.assertIsNone(
            c.NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://niziu.com/new"
            )
        )

    def test_cancelled_text_held(self):
        with self.assertRaises(ValueError):
            c.extract(HTML.replace("当落発表", "受付中止。当落発表"), ROUTE)

    def test_empty_and_failed_are_distinct(self):
        empty = HTML.replace(
            "受付期間：2026年10月13日(火)20:00～10月18日(日)23:59", ""
        ).replace("当落発表：2026年10月21日", "")
        result = c.collect([ROUTE], {"event-a"}, NOW, fetch=lambda _: empty)
        self.assertEqual(result["results"][0]["status"], "empty_unverified")

    def test_cancellation_outside_scope_keeps_facts_but_requires_status_review(self):
        result = c.collect(
            [ROUTE],
            {"event-a"},
            NOW,
            fetch=lambda _: "<p>本公演の先行受付は中止</p>" + HTML,
        )
        self.assertEqual(
            result["results"][0]["status"], "status_or_applicability_requires_review"
        )
        self.assertEqual(len(result["observations"]), 1)

    def test_general_notice_keeps_candidate_not_automatic_confirmation(self):
        result = c.collect(
            [ROUTE],
            {"event-a"},
            NOW,
            fetch=lambda _: "<p>出演メンバーが変更になる場合があります</p>" + HTML,
        )
        self.assertEqual(
            result["results"][0]["status"], "status_or_applicability_requires_review"
        )
        self.assertEqual(len(result["observations"]), 1)

    def test_previous_extra_fields_and_hash_tampering_rejected(self):
        first = c.collect([ROUTE], {"event-a"}, NOW, fetch=lambda _: HTML)
        for mutate in [
            lambda p: p["observations"][0].update(raw_html="secret"),
            lambda p: p["observations"][0]["candidate"].update(raw_html="secret"),
            lambda p: p["observations"][0]["candidate"]["milestones"]["results"].update(
                date="2026-10-23"
            ),
        ]:
            previous = copy.deepcopy(first)
            mutate(previous)
            with self.assertRaises(ValueError):
                c.collect(
                    [ROUTE], {"event-a"}, NOW, previous=previous, fetch=lambda _: HTML
                )

    def test_page_change_retained_even_if_dates_unchanged(self):
        first = c.collect([ROUTE], {"event-a"}, NOW, fetch=lambda _: HTML)
        second = c.collect(
            [ROUTE],
            {"event-a"},
            NOW,
            previous=first,
            fetch=lambda _: HTML + "<p>New applicability notice</p>",
        )
        self.assertEqual(second["results"][0]["status"], "page_changed_requires_review")
        self.assertEqual(len(second["observations"]), 2)


if __name__ == "__main__":
    unittest.main()

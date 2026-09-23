import copy
import unittest

from scripts.apply_venue_discovery_inbox import InboxSchemaError, apply_inbox

from scripts.signals.entity_aliases import _build_lookup_maps

VENUE_MAPS = _build_lookup_maps([("東京ドーム", ("東京ドーム", "Tokyo Dome"))])
ARTIST_MAPS = ({}, {})
CONFIG = {
    "accepted_source_classes": ["venue_official", "artist_official", "promoter_official", "ticket_official"],
    "rejected_domains": ["ticketjam.jp"],
    "watch_venues": [{"venue_id": "tokyo_dome", "venue_name": "東京ドーム", "aliases": ["東京ドーム", "Tokyo Dome"]}],
    "confirmed_events": [],
}


def cand(**kw):
    row = {"event_start_date": "2026-11-03", "event_end_date": "2026-11-03", "venue_name": "東京ドーム",
           "artist_name": "Example Artist", "title": "Example Artist Dome Tour", "event_category": "concert",
           "source_class": "venue_official", "confidence": "high",
           "evidence_url": "https://www.tokyo-dome.co.jp/event/1", "evidence_snippet": "2026年11月3日 開演18:00",
           "content_extractor": "requests_bs4", "verified_at_utc": "2026-09-24T03:05:00Z"}
    row.update(kw)
    return row


def inbox(*cands):
    return {"schema_version": 1, "run_at_utc": "2026-09-24T03:10:00Z",
            "automation_id": "msv-venue-discovery", "candidates": list(cands), "rejected": []}


def run(ib, config=CONFIG):
    return apply_inbox(ib, config, venue_maps=VENUE_MAPS, artist_maps=ARTIST_MAPS)


class ApplyInboxTest(unittest.TestCase):
    def test_appends_valid_candidate_with_defaults(self):
        result = run(inbox(cand()))
        self.assertEqual(len(result.applied), 1)
        row = result.config["confirmed_events"][0]
        self.assertTrue(row["event_id"].startswith("vwd-"))
        self.assertIs(row["enabled"], True)
        self.assertEqual(row["url"], "https://www.tokyo-dome.co.jp/event/1")

    def test_second_application_is_noop(self):
        first = run(inbox(cand()))
        second = run(inbox(cand()), config=first.config)
        self.assertEqual(second.applied, [])
        self.assertEqual(len(second.duplicates), 1)
        self.assertEqual(second.config, first.config)

    def test_alias_venue_is_stored_as_canonical_name(self):
        row = run(inbox(cand(venue_name="Tokyo Dome"))).config["confirmed_events"][0]
        self.assertEqual(row["venue_name"], "東京ドーム")
        self.assertEqual(row["raw_venue_name"], "Tokyo Dome")

    def test_alias_venue_is_duplicate_of_existing(self):
        first = run(inbox(cand()))
        second = run(inbox(cand(venue_name="Tokyo Dome")), config=first.config)
        self.assertEqual(len(second.duplicates), 1)

    def test_rejects_unaccepted_source_class(self):
        result = run(inbox(cand(source_class="secondary_market")))
        self.assertEqual(result.rejected[0]["reason"], "source_class")
        self.assertEqual(result.config["confirmed_events"], [])

    def test_rejects_rejected_domain_and_http(self):
        result = run(inbox(cand(evidence_url="https://ticketjam.jp/e/1"),
                           cand(evidence_url="http://www.tokyo-dome.co.jp/e", title="B")))
        self.assertEqual(sorted(r["reason"] for r in result.rejected), ["evidence_url", "rejected_domain"])

    def test_rejects_unknown_venue_and_bad_date_and_empty_snippet(self):
        result = run(inbox(cand(venue_name="Unknown Hall"),
                           cand(event_start_date="2026/11/03", title="C"),
                           cand(evidence_snippet="", title="D")))
        self.assertEqual(sorted(r["reason"] for r in result.rejected), ["date", "evidence_snippet", "venue"])

    def test_does_not_mutate_input_config(self):
        config = copy.deepcopy(CONFIG)
        run(inbox(cand()), config=config)
        self.assertEqual(config, CONFIG)

    def test_schema_errors(self):
        for bad in ({}, {"schema_version": 2, "run_at_utc": "x", "candidates": []},
                    {"schema_version": 1, "run_at_utc": "2026-09-24T03:10:00Z", "candidates": "x"},
                    inbox(*[cand(title=str(i)) for i in range(31)])):
            with self.assertRaises(InboxSchemaError):
                run(bad)


if __name__ == "__main__":
    unittest.main()

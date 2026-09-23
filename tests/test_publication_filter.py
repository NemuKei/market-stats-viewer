import unittest

from scripts.publication_filter import select_publishable_records


def rec(source_id, record_id, **kw):
    row = {"source_id": source_id, "record_id": record_id, "venue_name": "東京ドーム",
           "pref_name": "東京都", "source_class": "venue_official",
           "evidence_url": "https://example.jp/e", "evidence_snippet": "2026年11月3日"}
    row.update(kw)
    return row


class PublicationFilterTest(unittest.TestCase):
    def test_drops_non_baseline_sources(self):
        trusted, held = select_publishable_records(
            [rec("official_events", "a"), rec("ticketjam_events", "b")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual([r["record_id"] for r in trusted], ["a"])
        self.assertEqual(held, [])

    def test_unverified_venue_discovery_raises(self):
        with self.assertRaises(ValueError):
            select_publishable_records(
                [rec("venue_web_discovery", "a", evidence_snippet="")],
                venue_prefectures={})

    def test_prefecture_conflict_is_held(self):
        trusted, held = select_publishable_records(
            [rec("official_events", "a", pref_name="大阪府")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual(trusted, [])
        self.assertEqual(held[0]["reason"], "venue_prefecture_conflict")

    def test_missing_prefecture_is_filled_from_registry(self):
        trusted, _ = select_publishable_records(
            [rec("starto_concert", "a", pref_name="")],
            venue_prefectures={"東京ドーム": "東京都"})
        self.assertEqual(trusted[0]["pref_name"], "東京都")

    def test_unresolved_prefecture_is_held(self):
        trusted, held = select_publishable_records(
            [rec("kstyle_music", "a", pref_name="", venue_name="Unknown Hall")],
            venue_prefectures={})
        self.assertEqual(held[0]["reason"], "unresolved_domestic_location")


if __name__ == "__main__":
    unittest.main()

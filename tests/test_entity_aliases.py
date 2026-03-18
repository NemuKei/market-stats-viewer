import unittest

from scripts.signals.entity_aliases import (
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
)


class VenueAliasNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keep_map, cls.compact_map = load_venue_lookup_maps()

    def assertVenueNormalized(self, raw_value: str, expected: str) -> None:
        normalized, matched = normalize_venue_with_lookup(
            raw_value,
            self.keep_map,
            self.compact_map,
        )
        self.assertTrue(matched, msg=raw_value)
        self.assertEqual(expected, normalized)

    def test_strips_location_prefixes_for_known_venues(self) -> None:
        cases = [
            ("東京・東京ガーデンシアター(有明)", "東京ガーデンシアター"),
            ("神戸・GLION ARENA KOBE", "GLION ARENA KOBE"),
            ("○神奈川/Kアリーナ横浜", "Kアリーナ横浜"),
            ("福岡・マリンメッセ福岡 A館", "マリンメッセ福岡"),
            ("〇大阪・京セラドーム大阪", "京セラドーム大阪"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                self.assertVenueNormalized(raw_value, expected)

    def test_matches_manual_venue_aliases(self) -> None:
        cases = [
            ("IGアリーナ", "IGアリーナ"),
            ("愛知/IGアリーナ", "IGアリーナ"),
            ("IG ARENA", "IGアリーナ"),
            (
                "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )",
                "FC LIVE TOKYO HALL",
            ),
            (
                "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                "DREAM SQUARE HALL",
            ),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                self.assertVenueNormalized(raw_value, expected)


if __name__ == "__main__":
    unittest.main()

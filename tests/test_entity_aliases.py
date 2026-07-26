import csv
import json
import unittest
from pathlib import Path

from scripts.signals.artist_registry import normalize_text
from scripts.signals.entity_aliases import (
    load_venue_lookup_maps,
    normalize_venue_with_lookup,
    normalize_with_lookup,
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
            ("MUFG STADIUM(国立競技場)", "MUFGスタジアム"),
            (
                "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )",
                "FC LIVE TOKYO HALL",
            ),
            (
                "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                "DREAM SQUARE HALL",
            ),
            (
                "iBIG HALL(東京都新宿区新宿6-27-12ユニオン新宿ビル1F)",
                "iBIG HALL",
            ),
            ("ZeroBase渋谷(東京都渋谷区道玄坂2丁目5-8)", "ZeroBase渋谷"),
            ("タワーレコード渋谷店5F", "タワーレコード渋谷店5F"),
            ("渋谷モディ 1F カレンダリウム", "渋谷モディ 1F カレンダリウム"),
            ("東京・Club eX", "Club eX"),
            ("NHK大阪ホール", "NHK大阪ホール"),
            ("〇大阪/京セラドーム", "京セラドーム大阪"),
            ("福岡PayPayドーム", "みずほPayPayドーム福岡"),
            ("みずほPayPayドーム", "みずほPayPayドーム福岡"),
            ("MIZUHO PayPay Dome FUKUOKA", "みずほPayPayドーム福岡"),
            (
                "新宿パークタワーホール(東京都新宿区西新宿3-7-1新宿パークタワー 3F)",
                "新宿パークタワーホール",
            ),
            ("サンドーム福井", "サンドーム福井"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                self.assertVenueNormalized(raw_value, expected)

    def test_fukuoka_venue_rename_keeps_id_and_old_name_as_alias(self) -> None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        with (data_dir / "venue_registry.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as f:
            registry = {row["venue_id"]: row for row in csv.DictReader(f)}
        with (data_dir / "venue_aliases.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as f:
            aliases = {row["venue_id"]: row for row in csv.DictReader(f)}

        venue_id = "fukuoka_paypay_dome"
        canonical_name = "みずほPayPayドーム福岡"
        self.assertEqual(canonical_name, registry[venue_id]["venue_name"])
        self.assertEqual(canonical_name, aliases[venue_id]["canonical_name"])
        self.assertIn(
            "福岡PayPayドーム",
            json.loads(aliases[venue_id]["aliases_json"]),
        )


def _artist_lookup(*pairs: tuple[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    keep: dict[str, str] = {}
    compact: dict[str, str] = {}
    for alias, canonical in pairs:
        keep[normalize_text(alias, mode="keep")] = canonical
        compact[normalize_text(alias, mode="compact")] = canonical
    return keep, compact


class ArtistAliasNormalizationTests(unittest.TestCase):
    def test_artist_lookup_can_use_known_parenthetical_base(self) -> None:
        keep, compact = _artist_lookup(("EXILE", "EXILE"), ("エグザイル", "EXILE"))

        self.assertEqual(
            normalize_with_lookup(
                "EXILE（エグザイル）",
                keep,
                compact,
                allow_parenthetical_base=True,
            ),
            ("EXILE", True),
        )

    def test_artist_lookup_does_not_strip_unknown_parenthetical_base(self) -> None:
        keep, compact = _artist_lookup(("EXILE", "EXILE"))

        self.assertEqual(
            normalize_with_lookup(
                "EXILE ATSUSHI（エグザイル アツシ／EXILE）",
                keep,
                compact,
                allow_parenthetical_base=True,
            ),
            ("EXILE ATSUSHI（エグザイル アツシ／EXILE）", False),
        )


if __name__ == "__main__":
    unittest.main()

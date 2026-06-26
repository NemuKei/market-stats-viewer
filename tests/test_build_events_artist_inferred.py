from __future__ import annotations

import unittest

from scripts.build_events_artist_inferred import infer_event_artist
from scripts.events.category import classify_event_category
from scripts.signals.artist_registry import ArtistEntry, build_artist_index


class BuildEventsArtistInferredTests(unittest.TestCase):
    def _artist_index(self) -> dict[str, object]:
        return build_artist_index(
            [
                ArtistEntry(
                    artist_id="manual:jp:mrs_green_apple",
                    canonical_name="Mrs. GREEN APPLE",
                    aliases=("Mrs. GREEN APPLE", "ミセス", "ミセスグリーンアップル"),
                    source="manual",
                    is_enabled=True,
                )
            ]
        )

    def test_infer_artist_when_official_title_starts_with_artist_name(self) -> None:
        title = "Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜"

        inferred = infer_event_artist(title, "", self._artist_index())

        self.assertEqual(
            inferred,
            ("Mrs. GREEN APPLE", "high", "Mrs. GREEN APPLE", "title"),
        )
        self.assertEqual(classify_event_category(title, inferred[0], ""), "コンサート")

    def test_do_not_infer_prefix_artist_when_non_music_exclusion_exists(self) -> None:
        title = "Mrs. GREEN APPLE スポーツフェスティバル"

        inferred = infer_event_artist(title, "", self._artist_index())

        self.assertIsNone(inferred)

    def test_do_not_infer_alias_prefix_without_canonical_prefix_or_music_hint(self) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry(
                    artist_id="seed:life",
                    canonical_name="人生",
                    aliases=("Life",),
                    source="seed",
                    is_enabled=True,
                )
            ]
        )

        inferred = infer_event_artist(
            "LIFE! ON STAGE ～マーベラーに捧げるコント～", "", artist_index
        )

        self.assertIsNone(inferred)

    def test_do_not_infer_short_generic_artist_names_from_title_words(self) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry(
                    artist_id="seed:one",
                    canonical_name="One",
                    aliases=("One",),
                    source="seed",
                    is_enabled=True,
                ),
                ArtistEntry(
                    artist_id="seed:summer",
                    canonical_name="Summer",
                    aliases=("Summer",),
                    source="seed",
                    is_enabled=True,
                ),
                ArtistEntry(
                    artist_id="seed:rsp",
                    canonical_name="RSP",
                    aliases=("RSP",),
                    source="seed",
                    is_enabled=True,
                ),
                ArtistEntry(
                    artist_id="seed:wqwq",
                    canonical_name="wqwq",
                    aliases=("wqwq", "わくわく"),
                    source="seed",
                    is_enabled=True,
                ),
                ArtistEntry(
                    artist_id="seed:kosaka",
                    canonical_name="小坂洋二",
                    aliases=("るい",),
                    source="seed",
                    is_enabled=True,
                ),
            ]
        )

        for title in [
            "TRACK15 Zepp ONE MAN Tour",
            "B&ZAI LIVE 2026 Summer Beat",
            "SHINKANSEN☆RSP 怪奇骨董音楽劇『アケチコ！』",
            "NTPグループ 創業70周年記念 わくわくフェスタ",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(infer_event_artist(title, "", artist_index))


if __name__ == "__main__":
    unittest.main()

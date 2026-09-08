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

    def test_do_not_infer_alias_prefix_without_canonical_prefix_or_music_hint(
        self,
    ) -> None:
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

    def test_do_not_infer_artist_from_inside_a_katakana_word(self) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry("test:joy", "ジョイ", (), "test", True),
                ArtistEntry("test:korn", "コーン", (), "test", True),
            ]
        )

        for title in [
            "水谷千重子の宴ジョインコンサート2026",
            "スーパージョイ LIVE 2026",
            "ジョインコンサート2026",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(infer_event_artist(title, "", artist_index))

    def test_infer_katakana_artist_when_the_name_is_separated(self) -> None:
        artist_index = build_artist_index(
            [ArtistEntry("test:joy", "ジョイ", (), "test", True)]
        )

        for title in ["ジョイ LIVE 2026", "ジョイ コンサート", "ジョイ・コンサート"]:
            with self.subTest(title=title):
                self.assertEqual(
                    infer_event_artist(title, "", artist_index),
                    ("ジョイ", "high", "ジョイ", "title"),
                )

    def test_do_not_promote_another_ambiguous_title_word_after_rejecting_a_match(
        self,
    ) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry("test:bright", "BRIGHT", (), "test", True),
                ArtistEntry("test:amaterasu", "天照", (), "test", True),
                ArtistEntry("test:yohan", "ヨハン", (), "test", True),
            ]
        )

        for title in [
            "シャインポスト BRiGHT STARS FESTIVAL 2026 TINGS LIVE JOURNEY",
            "キズ Zepp TOUR 『天照焔巡』",
            "ウィーン・ヨハン・シュトラウス管弦楽団 ニューイヤーコンサート",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(infer_event_artist(title, "", artist_index))

        self.assertEqual(
            infer_event_artist("BRIGHT LIVE 2026", "", artist_index),
            ("BRIGHT", "high", "BRIGHT", "title"),
        )

    def test_year_and_venue_category_prefix_do_not_hide_the_performer(self) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry("test:ini", "INI", (), "test", True),
                ArtistEntry("test:nct127", "NCT 127", (), "test", True),
            ]
        )
        for title, artist in [
            ("2026 INI 5TH ANNIVERSARY DOME TOUR", "INI"),
            ("コンサート NCT 127 5TH TOUR", "NCT 127"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    infer_event_artist(title, "", artist_index),
                    (artist, "high", artist, "title"),
                )

    def test_short_english_prefix_needs_performer_context(self) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry("test:" + name, name, (), "test", True)
                for name in [
                    "IDOL", "LOVE", "Ado", "HANA", "Nissy", "Chage", "angela", "tuki.",
                    "KAI", "JUJU", "TWICE", "CORTIS", "ReoNa", "HAGANE"
                ]
            ]
        )
        for title in [
            "IDOL RUNWAY COLLECTION 2026 AUTUMN/WINTER AGESTOCK2026 in 横浜アリーナ",
            "IDOL RUNWAY COLLECTION in YOKOHAMA ARENA",
            "LOVE JAZZ TIME 2026",
            "KAI YOSHIHIRO ホームカミングツアー 2026",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(infer_event_artist(title, "", artist_index))
        for title, artist in [
            ("LOVE", "LOVE"),
            ("LOVE LIVE 2026", "LOVE"),
            ("Ado WORLD TOUR 2026", "Ado"),
            ("HANA 1st LIVE TOUR 2026", "HANA"),
            ("Nissy Nissy Entertainment Variety Show", "Nissy"),
            ("ChageLiveTour2026 One Love", "Chage"),
            ("angela政府公認路上ライヴ", "angela"),
            ("tuki.『秋の修学旅行〜天体観測〜』", "tuki."),
            ("JUJU HALL TOUR 2026", "JUJU"),
            ("TWICE ＜THIS IS FOR＞ WORLD TOUR IN JAPAN", "TWICE"),
            ("CORTIS 2026 CORTIS TOUR <PUT YOUR PHONE DOWN> IN JAPAN", "CORTIS"),
            ("ReoNa ReoNa ONE-MAN Concert 2027", "ReoNa"),
            ("HAGANE New Album Release Tour", "HAGANE"),
        ]:
            with self.subTest(title=title):
                confidence = "medium" if title == "ChageLiveTour2026 One Love" else "high"
                self.assertEqual(
                    infer_event_artist(title, "", artist_index),
                    (artist, confidence, artist, "title"),
                )

    def test_explicit_performer_attribution_preserves_short_canonical_names(
        self,
    ) -> None:
        artist_index = build_artist_index(
            [
                ArtistEntry("test:" + name, name, (), "test", True)
                for name in ["sumika", "toe", "PEDRO", "LOVE"]
            ]
        )
        for title, artist in [
            ("テレビ朝日presents sumika × 瑠東東一郎 CINEMA＆LIVE “SCENE”", "sumika"),
            ("街を嚥む、今宵の月 - HARVEST SPECIAL LIVE NIGHT WITH toe -", "toe"),
            ("This is PEDRO TOUR final 「ROMANTIC PLANET」", "PEDRO"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(
                    infer_event_artist(title, "", artist_index),
                    (artist, "high", artist, "title"),
                )
        self.assertIsNone(
            infer_event_artist(
                "From AG! with Love 〜ライブハウスより愛を込めて〜", "", artist_index
            )
        )


if __name__ == "__main__":
    unittest.main()

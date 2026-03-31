import json
import unittest

import requests
from bs4 import BeautifulSoup

from scripts.signals.sources.kstyle import KstyleMusicSource
from scripts.signals.types import SignalSourceRecord


class _FakeResponse:
    def __init__(self, url: str, text: str, status_code: int = 200) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}: {self.url}")


class _FakeSession:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    def get(self, url: str, **kwargs):
        del kwargs
        self.requested_urls.append(url)
        if "searchWord=%E2%96%A0%E5%85%AC%E6%BC%94%E6%83%85%E5%A0%B1" in url:
            return _FakeResponse(url, "<html><body><div>no results</div></body></html>")
        if "searchWord=%E2%96%A0%E9%96%8B%E5%82%AC%E6%A6%82%E8%A6%81" in url:
            return _FakeResponse(url, "<html><body><div>no results</div></body></html>")
        if url.endswith("/assets/sitemap/sitemaps/recent_news.xml"):
            return _FakeResponse(
                url,
                """<?xml version='1.0' encoding='UTF-8'?>
                <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'
                        xmlns:news='http://www.google.com/schemas/sitemap-news/0.9'>
                  <url>
                    <loc>https://kstyle.com/article.ksn?articleNo=2276697</loc>
                    <news:news>
                      <news:publication>
                        <news:name>Kstyle</news:name>
                        <news:language>ja</news:language>
                      </news:publication>
                      <news:publication_date>2026-03-16T19:05:00+09:00</news:publication_date>
                      <news:title>BABYMONSTER、日本初のドーム公演が決定！ワールドツアーの開催地を発表</news:title>
                    </news:news>
                    <lastmod>2026-03-16T19:14:08+09:00</lastmod>
                  </url>
                </urlset>
                """,
            )
        raise AssertionError(f"unexpected url requested: {url}")


class _StubKstyleMusicSource(KstyleMusicSource):
    def _fetch_article_detail(self, article_url: str, fallback_title: str):
        del article_url
        return ["■開催概要"], fallback_title, fallback_title

    def _extract_occurrences(self, section_lines, default_year=None):
        del section_lines, default_year
        return [("2026-07-08", "GLION ARENA KOBE", "2026年7月8日", "兵庫県")]

    def _is_japan_occurrence(self, section_lines, occurrences):
        del section_lines, occurrences
        return True


class KstyleMusicSourceTests(unittest.TestCase):
    def test_fetch_signals_uses_secondary_search_marker(self) -> None:
        source = _StubKstyleMusicSource(_FakeSession())
        source_record = SignalSourceRecord(
            source_id="kstyle_music",
            source_name="Kstyle MUSIC",
            source_url="https://kstyle.com/search.ksn?searchWord=%E2%96%A0%E5%85%AC%E6%BC%94%E6%83%85%E5%A0%B1",
            source_type="html_list",
            config_json=json.dumps(
                {"pages": 1, "category": "music"}, ensure_ascii=False
            ),
            is_enabled=True,
        )

        records = source.fetch_signals(source_record)

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0].url, "https://kstyle.com/article.ksn?articleNo=2276697"
        )
        self.assertTrue(
            any(
                "searchWord=%E2%96%A0%E5%85%AC%E6%BC%94%E6%83%85%E5%A0%B1" in url
                for url in source.session.requested_urls
            )
        )
        self.assertTrue(
            any(
                "searchWord=%E2%96%A0%E9%96%8B%E5%82%AC%E6%A6%82%E8%A6%81" in url
                for url in source.session.requested_urls
            )
        )
        self.assertTrue(
            any(
                url.endswith("/assets/sitemap/sitemaps/recent_news.xml")
                for url in source.session.requested_urls
            )
        )

    def test_extract_article_lines_normalizes_compatibility_ideographs(self) -> None:
        source = KstyleMusicSource(requests.Session())
        soup = BeautifulSoup(
            """
            <div id='articleBody'>
              <p>■開催概要</p>
              <p>「2026-27 BABYMONSTER WORLD TOUR IN JAPAN」</p>
              <p>【⽇程・会場】</p>
              <p>7⽉8⽇（⽔）神⼾・GLION ARENA KOBE</p>
              <p>9⽉22⽇（⽕・祝）⼤阪・京セラドーム⼤阪</p>
            </div>
            """,
            "html.parser",
        )

        lines = source._extract_article_lines(soup)
        section_lines = source._extract_concert_info_section(lines)
        occurrences = source._extract_occurrences(
            section_lines or [], default_year=2026
        )

        self.assertIn("【日程・会場】", lines)
        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [
                ("2026-07-08", "神戸・GLION ARENA KOBE"),
                ("2026-09-22", "大阪・京セラドーム大阪"),
            ],
        )

    def test_resolve_artist_avoids_short_false_positive_inside_city_name(self) -> None:
        source = KstyleMusicSource(requests.Session())

        artist_name, artist_labels = source._resolve_artist_from_title(
            "ASC2NT、3月と4月に東京&大阪でライブイベントを開催決定！新曲のステージ披露に期待 - Kstyle",
            "ASC2NT SPECIAL LIVE EVENT STILL : I",
        )

        self.assertEqual("ASC2NT", artist_name)
        self.assertEqual("high", artist_labels.get("artist_confidence"))
        self.assertEqual("ASC2NT", artist_labels.get("artist_matched_alias"))

    def test_resolve_artist_handles_descriptive_titles_and_concert_titles(self) -> None:
        source = KstyleMusicSource(requests.Session())
        cases = [
            (
                "日本発インディーロックバンドLET ME KNOW、12月に再び韓国で公演決定...2Days開催 - Kstyle",
                "LET ME KNOW ONEMAN LIVE - SCENE_2526 -",
                "LET ME KNOW",
            ),
            (
                "「ボイプラ2」出演の4人が所属...TUNEXX、初来日イベントが4月に開催決定！サイン会&2ショット撮影会も - Kstyle",
                "1stミニアルバム「SET BY US ONLY」発売記念イベント",
                "TUNEXX",
            ),
            (
                "新人ボーイズグループADAP、日本プロモーションが大反響！5月東京と大阪でファンミーティング開催決定 - Kstyle",
                "ADAPファンミーティング",
                "ADAP",
            ),
            (
                "NINE.i ジホ&イドゥン、3月に東京でファンミーティングを開催決定！ - Kstyle",
                "JIHO&EDEN FANMEETING IN JAPAN SWEET DATE:WHITE DAY",
                "JIHO&EDEN",
            ),
            (
                "韓国ミュージカル俳優エノク、2026年2月に日本初の単独コンサート開催決定! - Kstyle",
                "エノク 1st コンサート in Japan",
                "エノク",
            ),
        ]

        for article_title, concert_title, expected in cases:
            with self.subTest(expected=expected):
                artist_name, artist_labels = source._resolve_artist_from_title(
                    article_title,
                    concert_title,
                )
                self.assertEqual(expected, artist_name)
                self.assertTrue(
                    str(artist_labels.get("artist_matched_alias", "")).strip()
                )

    def test_extract_occurrences_handles_pref_block_with_late_venue_line(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "「ASC2NT SPECIAL LIVE EVENT STILL : I」",
            "<日時・会場>",
            "●東京",
            "2026年3月20日(祝・金)、21日(土)、22日(日)",
            "1部 開演15:00(開場14:30)",
            "2部 開演19:00(開場18:30)",
            "会場:FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )",
            "●大阪",
            "2026年4月3日(金)",
            "1部 開演15:00(開場14:30)",
            "2部 開演19:00(開場18:30)",
            "2026年4月4日(土)、5日(日)",
            "1部 開演13:00(開場12:30)",
            "2部 開演17:00(開場16:30)",
            "会場:DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
            "<チケット代金>",
            "前売:5,500円(税込)/ 全席自由・整理番号順入場",
            "<チケット販売期間>",
            "2026年3月2日(月)12:00~各公演4日前23:59まで",
        ]

        occurrences = source._extract_occurrences(section_lines, default_year=2026)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [
                ("2026-03-20", "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )"),
                ("2026-03-21", "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )"),
                ("2026-03-22", "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )"),
                (
                    "2026-04-03",
                    "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                ),
                (
                    "2026-04-04",
                    "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                ),
                (
                    "2026-04-05",
                    "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                ),
            ],
        )

    def test_extract_occurrences_ignores_headliner_lines_as_venues(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "K-POP音楽祭「Kstyle PARTY 2026」",
            "【出演アーティスト】",
            "2026年5月9日(土)ヘッドライナー:BOYNEXTDOOR / TWS、TAEMIN",
            "2026年5月10日(日)ヘッドライナー:RIIZE / SUPER JUNIOR-D&E、AHOF",
            "【日時】",
            "2026年5月9日(土) 16:00開場 / 17:30開演",
            "2026年5月10日(日) 14:00開場 / 15:30開演",
            "【場所】",
            "Kアリーナ横浜",
        ]

        occurrences = source._extract_occurrences(section_lines)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [
                ("2026-05-09", "Kアリーナ横浜"),
                ("2026-05-10", "Kアリーナ横浜"),
            ],
        )

    def test_extract_occurrences_stops_before_ticket_sections(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■公演情報",
            "「2025 CNBLUE Special Fanmeeting in JAPAN - Happy Xmas Memories -」",
            "<会場・公演日時>",
            "横浜/パシフィコ横浜国立大ホール",
            "2025年12月25日(木)",
            "<券種・料金>",
            "〇一般",
            "入金期間:2025年11月13日(木)18:00~11月19日(水)23:59まで",
        ]

        occurrences = source._extract_occurrences(section_lines)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [("2025-12-25", "横浜/パシフィコ横浜国立大ホール")],
        )

    def test_extract_occurrences_keeps_explicit_venue_for_date_ranges(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "「BLACKPINK 3rd MINI ALBUM[DEADLINE]POP-UP STORE」",
            "会期:2026年2月27日(金)~3月8日(日)",
            "会場:ZeroBase渋谷(東京都渋谷区道玄坂2丁目5-8)",
            "<豪華購入特典(先着順)>",
        ]

        occurrences = source._extract_occurrences(section_lines)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [
                ("2026-02-27", "ZeroBase渋谷(東京都渋谷区道玄坂2丁目5-8)"),
                ("2026-03-08", "ZeroBase渋谷(東京都渋谷区道玄坂2丁目5-8)"),
            ],
        )

    def test_extract_occurrences_ignores_resale_periods(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "「第42回 マイナビ 東京ガールズコレクション 2026 SPRING/SUMMER」",
            "【場所】",
            "国立代々木競技場 第一体育館",
            "【日時】",
            "2026年3月1日(日) 開場12:00 / 開演14:00",
            "〇公式リセール",
            "2026年2月20日(金)10:00~2月23日(月・祝)23:59",
        ]

        occurrences = source._extract_occurrences(section_lines)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [("2026-03-01", "国立代々木競技場 第一体育館")],
        )

    def test_extract_pref_venue_from_date_line_ignores_day_markers_and_both_days(
        self,
    ) -> None:
        source = KstyleMusicSource(requests.Session())
        cases = [
            "〇DAY1<12/13(土)>",
            "2025年12月13日(土)、14日(日)両日 開場15:00/開演17:00 (予定)",
        ]

        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(
                    ("", ""), source._extract_pref_venue_from_date_line(line)
                )

    def test_extract_occurrences_handles_english_pref_headings(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "ADAPファンミーティング",
            "<日時・会場>",
            "〇TOKYO",
            "2026年5月13日(水)",
            "会場:FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )",
            "〇OSAKA",
            "2026年5月15日(金)",
            "会場:DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
        ]

        occurrences = source._extract_occurrences(section_lines)

        self.assertEqual(
            [
                (event_date, venue_name, pref_name)
                for event_date, venue_name, _, pref_name in occurrences
            ],
            [
                (
                    "2026-05-13",
                    "FC LIVE TOKYO HALL(東京都新宿区大久保2-18-14 )",
                    "東京都",
                ),
                (
                    "2026-05-15",
                    "DREAM SQUARE HALL(大阪府吹田市江坂町1-18-8 江坂パークサイドスクエア2F)",
                    "大阪府",
                ),
            ],
        )

    def test_extract_occurrences_skips_foreign_blocks_in_mixed_article(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "アジアツアー開催",
            "<日時・会場>",
            "〇東京",
            "2026年5月1日(金)",
            "会場:Kアリーナ横浜",
            "〇ソウル",
            "2026年5月3日(日)",
            "会場:KSPO DOME",
        ]

        occurrences = source._extract_occurrences(section_lines, default_year=2026)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [("2026-05-01", "Kアリーナ横浜")],
        )

    def test_extract_occurrences_does_not_treat_generic_text_as_venue(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "イベント概要",
            "【日時】",
            "2026年5月1日(金)",
            "先着受付",
        ]

        occurrences = source._extract_occurrences(section_lines, default_year=2026)

        self.assertEqual(occurrences, [])

    def test_extract_occurrences_does_not_treat_decorated_live_label_as_venue(
        self,
    ) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "【日時】",
            "2026年4月17日",
            "★LIVE",
        ]

        occurrences = source._extract_occurrences(section_lines, default_year=2026)

        self.assertEqual(occurrences, [])

    def test_extract_occurrences_uses_later_ascii_venue_section(self) -> None:
        source = KstyleMusicSource(requests.Session())
        section_lines = [
            "■開催概要",
            "「2026 BXB SPECIAL LIVE IN JAPAN The Last Story」",
            "<日時>",
            "★FREE SHOWCASE",
            "2026年4月17日（金）",
            "1部 開演15:00（開場14:30）",
            "★LIVE",
            "2026年4月17日（金）",
            "2部 開演19:00（開場18:30）",
            "2026年4月18日（土）、4月19日（日）",
            "1部 開演15:00（開場14:30） 2部 開演19:00（開場18:30）",
            "<会場>",
            "FCLIVE TOKYO HALL（東京都新宿区大久保2-18-14）",
        ]

        occurrences = source._extract_occurrences(section_lines, default_year=2026)

        self.assertEqual(
            [(event_date, venue_name) for event_date, venue_name, _, _ in occurrences],
            [
                ("2026-04-17", "FCLIVE TOKYO HALL(東京都新宿区大久保2-18-14)"),
                ("2026-04-18", "FCLIVE TOKYO HALL(東京都新宿区大久保2-18-14)"),
                ("2026-04-19", "FCLIVE TOKYO HALL(東京都新宿区大久保2-18-14)"),
            ],
        )


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual("low", artist_labels.get("artist_confidence"))

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


if __name__ == "__main__":
    unittest.main()

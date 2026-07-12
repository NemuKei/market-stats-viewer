import unittest

from scripts.signals.text_quality import (
    EventTextQualityError,
    text_quality_issue,
    validate_event_text_fields,
)


class EventTextQualityTests(unittest.TestCase):
    def test_rejects_ticketjam_ptcp154_mojibake_regression(self) -> None:
        good = "GRe4N BOYZ イマーシブライブシアター2026 「“The ZA” 〜溢れる想いが止まらない〜」"
        bad = good.encode("utf-8").decode("ptcp154")

        self.assertEqual(text_quality_issue(bad), "probable_utf8_mojibake")
        with self.assertRaisesRegex(EventTextQualityError, "title=probable_utf8_mojibake"):
            validate_event_text_fields({"title": bad}, context="event/1063773")

    def test_allows_japanese_emoji_symbols_and_cyrillic(self) -> None:
        values = {
            "title": "公演🎤 「“The ZA” 〜想い〜」 café",
            "artist_name": "Оркестр Японии",
            "raw_artist_name": "GRe4N BOYZ（旧GReeeeN）",
            "venue_name": "KT Zepp Yokohama",
            "pref_name": "神奈川県",
            "event_category": "コンサート",
        }

        validate_event_text_fields(values, context="valid fixture")

    def test_rejects_replacement_and_forbidden_control_characters(self) -> None:
        self.assertEqual(text_quality_issue("broken\ufffdtext"), "forbidden_unicode_codepoint")
        self.assertEqual(text_quality_issue("broken\x00text"), "forbidden_unicode_codepoint")


if __name__ == "__main__":
    unittest.main()

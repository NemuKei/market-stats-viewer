from __future__ import annotations

from collections.abc import Mapping

EVENT_TEXT_FIELDS = (
    "title", "artist_name", "raw_artist_name", "venue_name",
    "raw_venue_name", "pref_name", "event_category",
)
_MOJIBAKE_CODECS = ("ptcp154", "latin1", "cp1252", "shift_jis")


class EventTextQualityError(ValueError):
    pass


def _japanese_char_count(value: str) -> int:
    return sum(
        1 for char in value
        if "\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff"
    )


def _contains_forbidden_codepoint(value: str) -> bool:
    for char in value:
        codepoint = ord(char)
        if char == "\ufffd":
            return True
        if 0xD800 <= codepoint <= 0xDFFF or codepoint in {0xFFFE, 0xFFFF}:
            return True
        if codepoint < 0x20 and char not in {"\t", "\n", "\r"}:
            return True
    return False


def _looks_like_utf8_mojibake(value: str) -> bool:
    original_japanese = _japanese_char_count(value)
    for codec in _MOJIBAKE_CODECS:
        try:
            repaired = value.encode(codec).decode("utf-8", errors="strict")
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            continue
        repaired_japanese = _japanese_char_count(repaired)
        if repaired != value and repaired_japanese >= 4 and repaired_japanese >= original_japanese + 4:
            return True
    return False


def text_quality_issue(value: object) -> str | None:
    text = str(value or "")
    if not text:
        return None
    if _contains_forbidden_codepoint(text):
        return "forbidden_unicode_codepoint"
    if _looks_like_utf8_mojibake(text):
        return "probable_utf8_mojibake"
    return None


def validate_event_text_fields(values: Mapping[str, object], *, context: str) -> None:
    issues: list[str] = []
    for field in EVENT_TEXT_FIELDS:
        issue = text_quality_issue(values.get(field))
        if issue:
            issues.append(f"{field}={issue}")
    if issues:
        raise EventTextQualityError(f"{context}: " + ", ".join(issues))

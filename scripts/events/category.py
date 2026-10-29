"""Event category classification helpers.

Categories are persisted into events.sqlite so downstream consumers can
filter without re-implementing app-layer rules.
"""

from __future__ import annotations

import re
import unicodedata

EVENT_CATEGORY_CONCERT = "コンサート"
EVENT_CATEGORY_BASEBALL = "野球"
EVENT_CATEGORY_OTHER = "その他"
EVENT_CATEGORY_UNKNOWN = "未分類"


def classify_event_category(title: object, artist_name: object, description: object) -> str:
    return classify_event_category_with_reason(title, artist_name, description)[0]


def classify_event_category_with_reason(title: object, artist_name: object, description: object) -> tuple[str, str]:
    """Return the stored category and the first matching rule, without guessing names."""
    text = " ".join([str(title or ""), str(artist_name or ""), str(description or "")])
    normalized_text = unicodedata.normalize("NFKC", text).lower()

    baseball_keywords = [
        "野球",
        "ベースボール",
        "baseball",
        "npb",
        "プロ野球",
        "甲子園",
        "侍ジャパン",
        "オープン戦",
        "公式戦",
        "ファーム",
        "クライマックスシリーズ",
        "日本シリーズ",
        "セ・リーグ",
        "パ・リーグ",
        "交流戦",
    ]
    baseball_team_keywords = [
        "オリックス",
        "バファローズ",
        "阪神",
        "タイガース",
        "巨人",
        "ジャイアンツ",
        "ヤクルト",
        "スワローズ",
        "広島",
        "カープ",
        "中日",
        "ドラゴンズ",
        "dena",
        "ベイスターズ",
        "ベイス",
        "ソフトバンク",
        "ホークス",
        "日本ハム",
        "日ハム",
        "ファイターズ",
        "楽天",
        "イーグルス",
        "西武",
        "ライオンズ",
        "ロッテ",
        "マリーンズ",
    ]
    versus_keywords = ["vs", "対", "×"]
    non_music_keywords = [
        "就活",
        "就職",
        "説明会",
        "展示会",
        "見本市",
        "expo",
        "フェア",
        "学会",
        "式典",
        "授与式",
        "卒業式",
        "入学式",
        "サッカー",
        "j1",
        "acl",
        "チャンピオンズリーグ",
        "フットサル",
        "マラソン",
        "グランプリ",
        "大会",
        "カップ",
        "m-1",
        "スポーツフェスティバル",
        "アメリカンフットボール",
        "アメフト",
        "ハンドメイド",
        "ランニング",
        "プロレス",
    ]
    concert_keywords = [
        "ライブ",
        "コンサート",
        "音楽イベント",
        "単独公演",
        "音楽フェス",
        "ミュージック",
        "軽音",
        "吹奏楽",
        "ツアー",
        "リサイタル",
        "オーケストラ",
        "交響楽団",
        "フィルハーモニー",
        "演奏会",
        "concert",
        "live",
        "tour",
        "oneman",
        "one man",
        "world tour",
        "fan meeting",
        "showcase",
        "弾き語り",
        "ワンマン",
        "ワールドツアー",
        "ドームツアー",
        "アリーナツアー",
    ]
    concert_match = next((k for k in concert_keywords if k in normalized_text), None)
    extended_match = concert_match in {"単独公演", "音楽フェス", "ミュージック", "軽音", "吹奏楽"}
    if concert_match is None:
        phrase = re.search(r"(?<![a-z0-9_])(?:music\s+(?:&\s*entertainment\s+)?(?:festival|fes)(?![a-z_])|k[ -]pop\s+festival(?![a-z_]))|(?<!\w)(?:gig|band)(?!\w)", normalized_text)
        concert_match = phrase.group() if phrase else None
        extended_match = phrase is not None
    # A generic solo performance may also be theatre or comedy; keep the conflict explicit.
    performance_conflict = re.search(r"漫才|お笑い|コント|演劇|劇団|歌舞伎|バレエ|ミュージカル", normalized_text)
    if extended_match and performance_conflict:
        return EVENT_CATEGORY_UNKNOWN, "conflicting_evidence:" + concert_match + "/" + performance_conflict.group()
    other_match = next((k for k in non_music_keywords if k in normalized_text), None)
    sports = re.search(r"j[123](?:リーグ|league|百年構想リーグ)|b[.]league|sv[.]league|なでしこリーグ|jfl|fc東京|東京ヴェルディ|バスケットボール|バスケ|サッカー|フットサル|ラグビー|バレーボール", normalized_text)
    has_versus = any(k in normalized_text for k in versus_keywords)
    sports_match = sports and (has_versus or re.search(r"第\s*\d+\s*節|ホームゲーム|試合|season", normalized_text))
    baseball_match = next((k for k in baseball_keywords if k in normalized_text), None)
    if concert_match and (other_match or sports_match or baseball_match):
        return EVENT_CATEGORY_UNKNOWN, "conflicting_evidence:" + concert_match + "/" + (other_match or baseball_match or sports.group())
    ambiguous = next((k for k in ("expo", "党大会", "卒業式") if k in normalized_text), None)
    if ambiguous:
        return EVENT_CATEGORY_UNKNOWN, "ambiguous_non_music:" + ambiguous
    if sports_match:
        return EVENT_CATEGORY_OTHER, "sports_match:" + sports.group()
    # Non-baseball sports can also say オープン戦; do not let that generic word win.
    non_baseball = next((k for k in ("アメリカンフットボール", "アメフト", "プロレス", "ランニング", "ハンドメイド") if k in normalized_text), None)
    if non_baseball:
        return EVENT_CATEGORY_OTHER, "non_music_keyword:" + non_baseball
    if baseball_match:
        return EVENT_CATEGORY_BASEBALL, "baseball_keyword:" + baseball_match
    if other_match and has_versus:
        return EVENT_CATEGORY_OTHER, "non_music_matchup"
    team_match = next((k for k in baseball_team_keywords if k in normalized_text), None)
    if team_match and has_versus:
        return EVENT_CATEGORY_BASEBALL, "baseball_team_matchup:" + team_match
    if other_match:
        return EVENT_CATEGORY_OTHER, "non_music_keyword:" + other_match
    if str(artist_name or "").strip():
        return EVENT_CATEGORY_CONCERT, "artist_name"
    if concert_match:
        return EVENT_CATEGORY_CONCERT, "concert_keyword:" + concert_match
    return EVENT_CATEGORY_UNKNOWN, "insufficient_evidence"

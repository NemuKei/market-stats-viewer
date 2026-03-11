"""Event category classification helpers.

Categories are persisted into events.sqlite so downstream consumers can
filter without re-implementing app-layer rules.
"""

from __future__ import annotations

EVENT_CATEGORY_CONCERT = "コンサート"
EVENT_CATEGORY_BASEBALL = "野球"
EVENT_CATEGORY_OTHER = "その他"


def classify_event_category(title: object, artist_name: object, description: object) -> str:
    text = " ".join([str(title or ""), str(artist_name or ""), str(description or "")])
    normalized_text = text.lower()

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
    versus_keywords = ["vs", "ｖｓ", "対", " 対戦 "]
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
    ]
    has_non_music_keyword = any(keyword in normalized_text for keyword in non_music_keywords)
    has_versus = any(keyword in normalized_text for keyword in versus_keywords)
    if has_non_music_keyword and has_versus:
        return EVENT_CATEGORY_OTHER
    if any(keyword in normalized_text for keyword in baseball_keywords):
        return EVENT_CATEGORY_BASEBALL
    has_team_keyword = any(keyword in normalized_text for keyword in baseball_team_keywords)
    if has_team_keyword and has_versus:
        return EVENT_CATEGORY_BASEBALL

    concert_keywords = [
        "ライブ",
        "コンサート",
        "音楽イベント",
        "公演",
        "ツアー",
        "フェス",
        "リサイタル",
        "オーケストラ",
        "music",
        "concert",
        "festival",
        "band",
        "gig",
        "live",
        "tour",
        "dome",
        "arena",
        "hall",
        "zepp",
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
    has_concert_keyword = any(keyword in normalized_text for keyword in concert_keywords)
    if has_non_music_keyword and not str(artist_name or "").strip():
        return EVENT_CATEGORY_OTHER
    if has_non_music_keyword and not has_concert_keyword:
        return EVENT_CATEGORY_OTHER

    if str(artist_name or "").strip():
        return EVENT_CATEGORY_CONCERT
    if has_concert_keyword:
        return EVENT_CATEGORY_CONCERT
    return EVENT_CATEGORY_OTHER

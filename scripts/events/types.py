"""Data types for event hub."""
from __future__ import annotations

from dataclasses import dataclass, field


JAPAN_PREFECTURES = frozenset("""
北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県
新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県
奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県
熊本県 大分県 宮崎県 鹿児島県 沖縄県
""".split())


@dataclass
class VenueRecord:
    """One row from venue_registry.csv."""

    venue_id: str
    venue_name: str
    pref_code: str
    pref_name: str
    capacity: int | None
    official_url: str
    source_type: str
    source_url: str
    config_json: str | None
    is_enabled: bool
    ticketjam_watch: bool = False
    official_fetch_candidate: bool = False
    official_gap_reason: str | None = None


@dataclass
class EventRecord:
    """Normalised event ready for DB upsert."""

    event_uid: str
    venue_id: str
    title: str
    start_date: str  # YYYY-MM-DD
    start_time: str | None  # HH:MM
    end_date: str | None
    end_time: str | None
    all_day: bool
    status: str  # scheduled / cancelled / postponed / unknown
    url: str | None
    description: str | None
    performers: str | None
    capacity: int | None
    source_type: str
    source_url: str
    source_event_key: str | None
    data_hash: str = field(default="", init=False)

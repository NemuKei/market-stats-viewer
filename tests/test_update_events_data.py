from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.events.sources.base import compute_data_hash
from scripts.events.types import EventRecord
from scripts.update_events_data import init_db, upsert_events


class UpdateEventsDataTests(unittest.TestCase):
    def test_upsert_events_updates_derived_fields_even_when_data_hash_is_same(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "events.sqlite"
            conn = init_db(db_path)
            conn.execute(
                """
                INSERT INTO events (
                    event_uid, venue_id, title, start_date, start_time,
                    end_date, end_time, all_day, status, url,
                    description, performers, artist_name_resolved, artist_confidence, event_category,
                    capacity, source_type, source_url, source_event_key, data_hash,
                    first_seen_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "panasonic:event1",
                    "panasonic_stadium_suita",
                    "明治安田J1百年構想リーグ ガンバ大阪 VS サンフレッチェ広島",
                    "2026-05-10",
                    None,
                    None,
                    None,
                    1,
                    "scheduled",
                    None,
                    None,
                    None,
                    "",
                    "low",
                    "野球",
                    None,
                    "html",
                    "https://suitacityfootballstadium.jp/schedule/",
                    "event1",
                    "hash1",
                    "2026-03-11T00:00:00Z",
                    "2026-03-11T00:00:00Z",
                ),
            )
            conn.commit()

            event = EventRecord(
                event_uid="panasonic:event1",
                venue_id="panasonic_stadium_suita",
                title="明治安田J1百年構想リーグ ガンバ大阪 VS サンフレッチェ広島",
                start_date="2026-05-10",
                start_time=None,
                end_date=None,
                end_time=None,
                all_day=True,
                status="scheduled",
                url=None,
                description=None,
                performers=None,
                capacity=None,
                source_type="html",
                source_url="https://suitacityfootballstadium.jp/schedule/",
                source_event_key="event1",
            )
            event.data_hash = "hash1"

            changed = upsert_events(conn, [event], {}, {})
            self.assertEqual(changed, 1)

            row = conn.execute(
                "SELECT event_category FROM events WHERE event_uid = ?",
                ("panasonic:event1",),
            ).fetchone()
            self.assertEqual(row[0], "その他")
            conn.close()


if __name__ == "__main__":
    unittest.main()

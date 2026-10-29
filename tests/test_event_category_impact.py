import hashlib
import sqlite3

from scripts.audit_event_category_impact import audit


def test_audit_reports_concert_drops_without_modifying_database(tmp_path):
    path = tmp_path / 'events.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE events (event_uid TEXT, title TEXT, start_date TEXT, artist_name_resolved TEXT, description TEXT, event_category TEXT)')
        connection.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', [
            ('a', 'DEEN LIVE', '2026-01-01', '', '', 'コンサート'),
            ('b', 'BOOSTランニングフェスタ', '2026-01-02', '', '', 'コンサート'),
        ])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = audit(path)
    assert result['row_count'] == 2
    assert result['changed_count'] == result['concert_drop_count'] == 1
    assert result['changes'][0]['event_uid'] == 'b'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before == result['database_sha256']

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.check_automation_freshness import check_freshness

NOW = datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)


class FreshnessTest(unittest.TestCase):
    def write(self, payload):
        d = tempfile.mkdtemp()
        p = Path(d) / "inbox.json"
        p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        return p

    def test_fresh(self):
        ok, _ = check_freshness(self.write({"run_at_utc": "2026-09-25T00:00:00Z"}), max_age_days=3, now=NOW)
        self.assertTrue(ok)

    def test_stale(self):
        ok, msg = check_freshness(self.write({"run_at_utc": "2026-09-23T23:59:00Z"}), max_age_days=3, now=NOW)
        self.assertFalse(ok)
        self.assertIn("stale", msg)

    def test_missing_file(self):
        ok, msg = check_freshness(Path("/nonexistent/inbox.json"), max_age_days=3, now=NOW)
        self.assertFalse(ok)

    def test_broken_json_or_missing_field(self):
        for payload in ("{", {"schema_version": 1}):
            ok, _ = check_freshness(self.write(payload), max_age_days=3, now=NOW)
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()

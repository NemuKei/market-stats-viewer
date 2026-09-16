"""Offline, synthetic-fixture tests; never contact sources or update runtime data."""
from __future__ import annotations
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.audit_national_event_coverage import audit, read_inputs


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.venues = [
            dict(venue_id='arena_a', venue_name='テストアリーナ', pref_code='01',
                 capacity='10000', is_enabled='1', official_url='https://a.example.test/'),
            dict(venue_id='arena_b', venue_name='別の体育館', pref_code='47',
                 capacity='', is_enabled='0', official_url='https://b.example.test/'),
        ]
        self.discovery = dict(watch_venues=[dict(venue_id='arena_a',
            venue_name='テストアリーナ', aliases=['Test Arena'])])
        self.ticketjam = [dict(venue_id='arena_b', venue_name='別の体育館', is_enabled='1')]

    def run_audit(self):
        return audit(self.venues, self.discovery, self.ticketjam)

    def test_counts_and_no_runtime_claim(self):
        report = self.run_audit()
        self.assertEqual(report['summary']['registered_venues'], 2)
        self.assertEqual(report['summary']['official_enabled'], 1)
        self.assertEqual(report['summary']['web_watch_configured'], 1)
        self.assertEqual(report['summary']['ticketjam_enabled'], 1)
        self.assertFalse(report['runtime_coverage_verified'])

    def test_all_47_prefectures_are_accounted_for(self):
        report = self.run_audit()
        self.assertEqual(len(report['prefectures']), 47)
        self.assertEqual(report['prefectures'][1]['registered'], 0)
        self.assertEqual(report['prefectures'][1]['review_status'], 'not_assessed')

    def test_disabled_and_unknown_capacity_are_retained(self):
        row = self.run_audit()['venues'][1]
        self.assertFalse(row['official_enabled'])
        self.assertIsNone(row['capacity_from_registry'])
        self.assertEqual(row['scope_review'], 'required')

    def test_absent_ticketjam_is_not_success(self):
        self.ticketjam = []
        self.assertEqual(self.run_audit()['summary']['ticketjam_enabled'], 0)

    def test_unknown_discovery_id_is_reported(self):
        self.discovery['watch_venues'][0]['venue_id'] = 'unknown'
        self.assertEqual(self.run_audit()['orphan_web_watch_ids'], ['unknown'])

    def test_unknown_ticketjam_id_is_reported(self):
        self.ticketjam[0]['venue_id'] = 'unknown'
        self.assertEqual(self.run_audit()['orphan_ticketjam_ids'], ['unknown'])

    def test_duplicate_registry_id_rejected(self):
        self.venues.append(copy.deepcopy(self.venues[0]))
        with self.assertRaises(ValueError): self.run_audit()

    def test_duplicate_watch_id_rejected(self):
        self.discovery['watch_venues'] *= 2
        with self.assertRaises(ValueError): self.run_audit()

    def test_duplicate_ticketjam_id_rejected(self):
        self.ticketjam *= 2
        with self.assertRaises(ValueError): self.run_audit()

    def test_invalid_enabled_flag_rejected(self):
        self.venues[0]['is_enabled'] = 'yes'
        with self.assertRaises(ValueError): self.run_audit()

    def test_invalid_prefecture_rejected(self):
        self.venues[0]['pref_code'] = '48'
        with self.assertRaises(ValueError): self.run_audit()

    def test_invalid_capacity_rejected(self):
        self.venues[0]['capacity'] = '-100'
        with self.assertRaises(ValueError): self.run_audit()

    def test_missing_watch_list_rejected(self):
        self.discovery = {}
        with self.assertRaises(ValueError): self.run_audit()

    def test_missing_aliases_does_not_drop_venue(self):
        del self.discovery['watch_venues'][0]['aliases']
        self.assertEqual(self.run_audit()['summary']['web_watch_configured'], 1)

    def test_cross_id_alias_is_blocking(self):
        self.discovery['watch_venues'][0]['aliases'].append('別の体育館')
        issue = self.run_audit()['identity_conflicts'][0]
        self.assertEqual(issue['owner_id'], 'arena_a')
        self.assertEqual(issue['other_id'], 'arena_b')

    def test_alias_collision_across_watch_ids_is_blocking(self):
        self.discovery['watch_venues'].append(dict(venue_id='arena_b',
            venue_name='別の体育館', aliases=['Ｔｅｓｔ　Ａｒｅｎａ']))
        self.assertTrue(self.run_audit()['identity_conflicts'])

    def test_name_difference_is_review_not_auto_correction(self):
        self.discovery['watch_venues'][0]['venue_name'] = '旧テスト名'
        report = self.run_audit()
        self.assertTrue(report['name_reviews'])
        self.assertEqual(report['venues'][0]['venue_name'], 'テストアリーナ')

    def test_known_nonofficial_url_flagged_without_network(self):
        self.venues[0]['official_url'] = 'https://ticketjam.jp/venues/0'
        self.assertIn('reference_only_domain', self.run_audit()['venues'][0]['url_review'])

    def test_inputs_are_not_modified(self):
        before = copy.deepcopy((self.venues, self.discovery, self.ticketjam))
        self.run_audit()
        self.assertEqual(before, (self.venues, self.discovery, self.ticketjam))

    def test_deterministic_across_row_order(self):
        first = self.run_audit()
        self.venues.reverse()
        self.assertEqual(first, self.run_audit())

    def test_files_read_and_hashed_and_cli_stdout_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            vp, dp, tp = root/'v.csv', root/'d.json', root/'t.csv'
            for path, rows in [(vp, self.venues), (tp, self.ticketjam)]:
                with path.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader(); writer.writerows(rows)
            dp.write_text(json.dumps(self.discovery), encoding='utf-8')
            original = {p.name:p.read_bytes() for p in root.iterdir()}
            report = read_inputs(vp, dp, tp)
            self.assertEqual(len(report['input_sha256']['registry']), 64)
            proc = subprocess.run([sys.executable, '-m', 'scripts.audit_national_event_coverage',
                '--registry',str(vp),'--discovery',str(dp),'--ticketjam',str(tp)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['summary']['registered_venues'],2)
            self.assertEqual(original,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_missing_csv_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.csv'; p.write_text('venue_id\nx\n',encoding='utf-8')
            with self.assertRaises(ValueError): read_inputs(p,p,p)

    def test_malformed_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); v=root/'v.csv'; j=root/'d.json'; t=root/'t.csv'
            v.write_text('venue_id,venue_name,pref_code,capacity,is_enabled,official_url\n'
                         'a,A,01,1,1,https://a.test\n',encoding='utf-8')
            j.write_text('{',encoding='utf-8')
            t.write_text('venue_id,venue_name,is_enabled\n',encoding='utf-8')
            with self.assertRaises(ValueError): read_inputs(v,j,t)

if __name__ == '__main__':
    unittest.main()

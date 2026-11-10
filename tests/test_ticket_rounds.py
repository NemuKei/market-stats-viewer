import copy
import hashlib
import json
import unittest
from scripts.ticket_rounds import build, validate

NOW = '2026-11-10T09:00:00Z'
EVENTS = b'{"events":[{"event_key":"event-a"},{"event_key":"event-b"}]}'

def fixture():
    source = dict(url='https://example.org/official', name='Synthetic official', source_class='artist_official', checked_at_utc=NOW)
    milestone = dict(kind='results', knowledge_status='confirmed', precision='date', date='2026-11-20', time=None, end_date=None, end_time=None, timezone='Asia/Tokyo', source=source)
    r = dict(ticket_round_id='round-001', title='Synthetic fan club lottery', sale_method='lottery', round_type='fan_club', eligibility_label='Synthetic members', status='active', revision=1, first_seen_at_utc=NOW, last_verified_at_utc=NOW, milestones=[milestone])
    return dict(schema_version=1, generated_at_utc=NOW, event_generation_sha256=hashlib.sha256(EVENTS).hexdigest(), rounds=[r], links=[dict(ticket_round_id='round-001', event_uid=e) for e in ('event-a', 'event-b')])

def check(p):
    return validate(p, event_generation_sha256=hashlib.sha256(EVENTS).hexdigest(), event_uids={'event-a', 'event-b'})

class TicketTests(unittest.TestCase):
    def test_multiple_events_one_round_date_only(self):
        p = fixture(); old = copy.deepcopy(p)
        self.assertEqual(check(p), p); self.assertEqual(p, old)
        self.assertIsNone(p['rounds'][0]['milestones'][0]['time'])

    def test_unknown_states(self):
        for state in ('unannounced', 'unverified', 'not_applicable', 'conflict'):
            p = fixture(); m = p['rounds'][0]['milestones'][0]
            m.update(knowledge_status=state, date=None, precision=None)
            check(p)
            m['date'] = '2026-11-20'
            with self.assertRaises(ValueError): check(p)

    def test_bad_mutations(self):
        mutations = [lambda p: p.update(private_note='secret'), lambda p: p.update(schema_version=True),
            lambda p: p.update(event_generation_sha256='0'*64),
            lambda p: p['links'].append(p['links'][0]),
            lambda p: p['links'][0].update(event_uid='schedule-day'),
            lambda p: p['rounds'].append(p['rounds'][0]),
            lambda p: p['rounds'][0].update(revision=True),
            lambda p: p['rounds'][0].update(sale_method='first_come'),
            lambda p: p['rounds'][0]['milestones'][0].update(time='00:00'),
            lambda p: p['rounds'][0]['milestones'][0].update(source=None),
            lambda p: p['rounds'][0]['milestones'][0].update(date='2026-02-30'),
            lambda p: p['rounds'][0]['milestones'][0]['source'].update(url='javascript:alert(1)'),
            lambda p: p['rounds'][0]['milestones'][0]['source'].update(source_class='news')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                p = fixture(); mutate(p)
                with self.assertRaises(ValueError): check(p)

    def test_range(self):
        p = fixture(); m = p['rounds'][0]['milestones'][0]
        m.update(precision='range', time='12:00', end_date='2026-11-20', end_time='18:00')
        check(p); m['end_time'] = '11:59'
        with self.assertRaises(ValueError): check(p)

    def test_review_projection_and_no_source_mutation(self):
        p = fixture(); facts = {k:p[k] for k in ('rounds', 'links')}
        digest = hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        ledger = dict(schema_version=1, history=[], **facts, review=dict(status='reviewed', facts_sha256=digest, reviewed_at_utc=NOW))
        original = copy.deepcopy(ledger)
        self.assertEqual(build(ledger, EVENTS, generated_at_utc=NOW), p)
        self.assertEqual(ledger, original)
        ledger['rounds'][0]['title'] = 'Changed'
        with self.assertRaises(ValueError): build(ledger, EVENTS, generated_at_utc=NOW)


class ManifestTests(unittest.TestCase):
    def test_optional_manifest_and_generation_failure(self):
        import tempfile
        from pathlib import Path
        from scripts.build_external_events_manifest import _build_manifest
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for name in ('events.sqlite', 'event_signals.sqlite'): (folder/name).write_bytes(b'fixture')
            (folder/'lp_events.json').write_bytes(EVENTS)
            (folder/'lp_events_all.json').write_bytes(EVENTS)
            (folder/'ticket_rounds.json').write_text(json.dumps(fixture()))
            self.assertNotIn('ticket_rounds.json', _build_manifest(folder, 'fixture')['assets'])
            self.assertIn('ticket_rounds.json', _build_manifest(folder, 'fixture', include_ticket_rounds=True)['assets'])
            (folder/'lp_events_all.json').write_bytes(EVENTS+b' ')
            with self.assertRaises(ValueError): _build_manifest(folder, 'fixture', include_ticket_rounds=True)

class CliTests(unittest.TestCase):
    def test_invalid_ledger_preserves_output_and_inputs(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); ledger = folder/'ledger.json'; events = folder/'lp.json'; out = folder/'out.json'
            ledger.write_text('{}'); events.write_bytes(EVENTS); out.write_text('accepted')
            result = subprocess.run([sys.executable, '-m', 'scripts.build_ticket_rounds', '--ledger', str(ledger), '--events', str(events), '--output', str(out), '--generated-at-utc', NOW], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(out.read_text(), 'accepted')
            self.assertEqual(events.read_bytes(), EVENTS)
            self.assertEqual(ledger.read_text(), '{}')

class HistoryTests(unittest.TestCase):
    def ledger(self):
        from scripts.ticket_review_history import facts_hash
        p = fixture(); s = {k:p[k] for k in ('rounds','links')}
        s['review'] = dict(status='reviewed',facts_sha256=facts_hash(s),reviewed_at_utc=NOW)
        return dict(schema_version=1, history=[], **s)

    def test_correction_keeps_history_and_requires_revision(self):
        from scripts.ticket_review_history import facts_hash, validate_history
        ledger=self.ledger(); validate_history(ledger)
        ledger['history'].append(copy.deepcopy({k:ledger[k] for k in ('rounds','links','review')}))
        ledger['rounds'][0]['title']='Reviewed correction'
        ledger['review']['facts_sha256']=facts_hash(ledger)
        with self.assertRaises(ValueError): validate_history(ledger)
        ledger['rounds'][0]['revision']=2
        ledger['review']['facts_sha256']=facts_hash(ledger)
        validate_history(ledger)
        self.assertEqual(ledger['history'][0]['rounds'][0]['revision'],1)
        ledger['rounds']=[]; ledger['links']=[]; ledger['review']['facts_sha256']=facts_hash(ledger)
        with self.assertRaises(ValueError): validate_history(ledger)

    def test_link_change_requires_reviewed_revision(self):
        from scripts.ticket_review_history import facts_hash, validate_history
        ledger=self.ledger()
        ledger['history'].append(copy.deepcopy({k:ledger[k] for k in ('rounds','links','review')}))
        ledger['links'].pop(); ledger['review']['facts_sha256']=facts_hash(ledger)
        with self.assertRaises(ValueError): validate_history(ledger)
        ledger['rounds'][0]['revision']=2; ledger['review']['facts_sha256']=facts_hash(ledger)
        validate_history(ledger)

class WorkflowTests(unittest.TestCase):
    def test_disabled_by_default_and_separate_failure(self):
        from pathlib import Path
        content=Path('.github/workflows/publish_external_events_assets.yml').read_text()
        self.assertIn("vars.TICKET_ROUNDS_ENABLED == 'true'", content)
        self.assertIn('--events data/lp_events_all.json',content)
        self.assertIn('Ticket update failed; event publication continues',content)
        self.assertIn('${TICKET_ROUNDS_READY:-false}',content)

if __name__ == '__main__':
    unittest.main()

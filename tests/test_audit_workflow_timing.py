import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'audit_workflow_timing.py'


def audit(**kwargs):
    assert SCRIPT.exists(), 'read-only timing auditor is missing'
    spec = importlib.util.spec_from_file_location('audit_workflow_timing', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit(**kwargs)


def args():
    return dict(expected_at='2026-11-07T04:00:00Z', now='2026-11-07T12:00:00Z',
                workflow_path='.github/workflows/update_events_official.yml', branch='main',
                run=None, jobs=[], history_complete=True)


def run():
    return dict(id=42365550510, path='.github/workflows/update_events_official.yml',
                event='schedule', head_branch='main', created_at='2026-11-07T10:49:14Z',
                run_attempt=1, status='completed', conclusion='failure')


def test_missing_after_four_hours_is_not_success():
    result = audit(**args())
    assert result['state'] == 'not_created'
    assert result['overdue'] is True


def test_partial_history_is_unknown_not_missing():
    kw = args()
    kw['history_complete'] = False
    assert audit(**kw)['state'] == 'unconfirmed'


def test_creation_latency_separate_from_runner_delay():
    kw = args()
    kw['run'] = run()
    kw['jobs'] = [{'started_at': '2026-11-07T10:49:17Z'}]
    result = audit(**kw)
    assert result['creation_delay_seconds'] == 24554
    assert result['runner_delay_seconds'] == 3
    assert result['state'] == 'failure'


def test_different_workflow_is_rejected():
    kw = args()
    kw['run'] = run()
    kw['run']['path'] = '.github/workflows/update_signals.yml'
    assert audit(**kw)['state'] == 'unconfirmed'


def test_manual_run_is_not_scheduled_success():
    kw = args()
    kw['run'] = run()
    kw['run']['event'] = 'workflow_dispatch'
    assert audit(**kw)['state'] == 'unconfirmed'


def test_retry_does_not_misstate_original_runner_delay():
    kw = args()
    kw['run'] = run()
    kw['run']['run_attempt'] = 2
    kw['jobs'] = [{'started_at': '2026-11-07T11:20:00Z'}]
    assert audit(**kw)['runner_delay_seconds'] is None


def test_naive_time_is_rejected():
    kw = args()
    kw['expected_at'] = '2026-11-07T04:00:00'
    assert audit(**kw)['state'] == 'unconfirmed'


def test_wrong_branch_is_rejected():
    kw = args()
    kw['run'] = run()
    kw['run']['head_branch'] = 'test'
    assert audit(**kw)['state'] == 'unconfirmed'


def test_pre_due_missing_is_not_overdue():
    kw = args()
    kw['now'] = '2026-11-07T03:00:00Z'
    assert audit(**kw)['overdue'] is False


def test_notification_key_ignores_poll_time_but_changes_on_status():
    kw = args()
    kw['run'] = run()
    first = audit(**kw)
    kw['now'] = '2026-11-07T13:00:00Z'
    assert audit(**kw)['notification_key'] == first['notification_key']
    kw['run']['conclusion'] = 'success'
    assert audit(**kw)['notification_key'] != first['notification_key']

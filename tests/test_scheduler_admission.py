from urllib.parse import parse_qs, urlparse
import pytest
from scripts.scheduler_admission import admit


def env():
    return dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ATTEMPT='1',
                GITHUB_REPOSITORY='NemuKei/market-stats-viewer', GITHUB_REF='refs/heads/main',
                SCHEDULER_ORIGIN='https://scheduler.example.test',
                EXPECTED_AT='2026-11-10T04:00:00.000Z', DISPATCH_NONCE='a'*32,
                ACTIONS_ID_TOKEN_REQUEST_URL='https://pipelines.actions.githubusercontent.com/token?api-version=2.0',
                ACTIONS_ID_TOKEN_REQUEST_TOKEN='synthetic-request-token')


def test_admission_uses_exact_audience_and_keeps_tokens_out_of_body():
    calls = []
    def fetch(url, headers, body):
        calls.append((url, headers, body))
        return {'value': 'synthetic-jwt'} if len(calls) == 1 else {'allowed': True}
    assert admit(env(), fetch)
    assert parse_qs(urlparse(calls[0][0]).query)['audience'] == ['https://scheduler.example.test']
    assert calls[1][0] == 'https://scheduler.example.test/admit'
    assert calls[1][1]['Authorization'] == 'Bearer synthetic-jwt'
    assert calls[1][2] == {'expected_at': env()['EXPECTED_AT'], 'dispatch_nonce': 'a'*32}


@pytest.mark.parametrize('key,value', [('GITHUB_EVENT_NAME','schedule'), ('GITHUB_RUN_ATTEMPT','2'),
    ('GITHUB_REPOSITORY','other/repo'), ('GITHUB_REF','refs/heads/other'),
    ('SCHEDULER_ORIGIN','http://scheduler.example.test'), ('SCHEDULER_ORIGIN','https://user:pw@host'),
    ('SCHEDULER_ORIGIN','https://host/path'), ('DISPATCH_NONCE','bad')])
def test_invalid_context_is_rejected_without_network(key,value):
    inputs=env()
    inputs[key]=value
    with pytest.raises(ValueError):
        admit(inputs, lambda *_: pytest.fail('unexpected network'))


def test_refused_admission_is_false():
    count=0
    def fetch(*_):
        nonlocal count
        count+=1
        return {'value':'synthetic'} if count==1 else {'allowed':False}
    assert not admit(env(),fetch)

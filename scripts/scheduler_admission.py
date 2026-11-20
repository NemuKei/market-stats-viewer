"""Fail-closed admission for externally scheduled official event collection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(url: str, headers: dict, body: dict | None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, headers=headers)
    with build_opener(NoRedirect).open(request, timeout=15) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError('response too large')
    return json.loads(payload)


def admit(env: dict, fetch=fetch_json) -> bool:
    required = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_RUN_ATTEMPT': '1',
                'GITHUB_REPOSITORY': 'NemuKei/market-stats-viewer', 'GITHUB_REF': 'refs/heads/main'}
    if any(env.get(k) != v for k, v in required.items()):
        raise ValueError('unapproved workflow context')
    origin = env.get('SCHEDULER_ORIGIN', '')
    parts = urlsplit(origin)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.path or parts.query or parts.fragment or parts.port):
        raise ValueError('invalid scheduler origin')
    slot, nonce = env.get('EXPECTED_AT', ''), env.get('DISPATCH_NONCE', '')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T04:00:00\.000Z', slot) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('invalid slot or nonce')
    token_url = urlsplit(env.get('ACTIONS_ID_TOKEN_REQUEST_URL', ''))
    request_token = env.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
    if (token_url.scheme != 'https' or not token_url.hostname or token_url.username or token_url.password or token_url.fragment or token_url.port
            or not token_url.hostname.endswith('.actions.githubusercontent.com') or not request_token):
        raise ValueError('missing runner identity')
    query = dict(parse_qsl(token_url.query))
    query['audience'] = origin
    url = urlunsplit(token_url._replace(query=urlencode(query)))
    jwt = fetch(url, {'Authorization': f'Bearer {request_token}'}, None).get('value')
    if not isinstance(jwt, str) or not jwt:
        raise ValueError('missing signed identity')
    result = fetch(f'{origin}/admit', {'Authorization': f'Bearer {jwt}', 'Content-Type': 'application/json'},
                   {'expected_at': slot, 'dispatch_nonce': nonce})
    return result.get('allowed') is True


def main() -> int:
    try:
        allowed = admit(dict(os.environ))
    except Exception:
        allowed = False
    if output := os.environ.get('GITHUB_OUTPUT'):
        with Path(output).open('a', encoding='utf-8') as handle:
            handle.write(f"admitted={'true' if allowed else 'false'}\n")
    print('Official collection admitted.' if allowed else 'Official collection NOT admitted; no automatic retry.')
    return 0 if allowed else 1


if __name__ == '__main__':
    raise SystemExit(main())

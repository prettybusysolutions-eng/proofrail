"""The real GitHub client's request construction and failure mapping, without a network.

Only the URL opener is replaced, so GitHubAPI.request runs its own code: URL,
method, body encoding, headers, timeout, redirect refusal and error mapping.
Before these tests, swapping how GET and POST bodies are built left the whole
suite green, because no test ever let the client build a request.
"""
import io
import os
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler

import pytest

DEMO = Path(__file__).resolve().parents[1] / 'buyer_demo'
sys.path.insert(0, str(DEMO))
import enforcing_dispatcher  # noqa: E402
from enforcing_dispatcher import GitHubAPI, NoRedirect  # noqa: E402

TOKEN = 'ghs_unit-test-token-0123456789'


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, reply=b'{"ok": true}', error=None):
        self.reply, self.error, self.seen = reply, error, []

    def open(self, request, timeout=None):
        self.seen.append((request, timeout))
        if self.error:
            raise self.error
        return Response(self.reply)


@pytest.fixture
def api(tmp_path):
    path = tmp_path / 'token'
    path.write_text(TOKEN + '\n')
    path.chmod(0o600)
    client = GitHubAPI(path)
    client._opener = Opener()
    return client


def test_get_has_no_body_and_fixed_headers(api):
    assert api.request('GET', '/repos/o/r/git/ref/heads/trial/emergence-x') == {'ok': True}
    request, timeout = api._opener.seen[0]
    assert request.full_url == 'https://api.github.com/repos/o/r/git/ref/heads/trial/emergence-x'
    assert request.get_method() == 'GET'
    assert request.data is None
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers['authorization'] == 'Bearer ' + TOKEN
    assert headers['accept'] == 'application/vnd.github+json'
    assert headers['x-github-api-version'] == '2026-03-10'
    assert headers['user-agent'] == 'ProofRail-Pilot'
    assert timeout == 20


@pytest.mark.parametrize('method', ['POST', 'PATCH'])
def test_write_sends_exact_json_body(api, method):
    body = {'sha': 'a' * 40, 'force': False}
    api.request(method, '/repos/o/r/git/refs/heads/trial/emergence-x', body)
    request, _ = api._opener.seen[0]
    assert request.get_method() == method
    assert request.data == json.dumps(body).encode()
    assert json.loads(request.data) == body


@pytest.mark.parametrize('error', [
    HTTPError('https://api.github.com/x', 422, 'Unprocessable', {}, io.BytesIO(b'{"message":"' + TOKEN.encode() + b'"}')),
    URLError('connection reset'),
    TimeoutError('timed out'),
    ValueError('provider_redirect_rejected'),
    json.JSONDecodeError('bad', 'x', 0),
])
def test_every_failure_is_an_unknown_outcome_without_details(api, error):
    api._opener = Opener(error=error)
    with pytest.raises(RuntimeError) as exc:
        api.request('PATCH', '/repos/o/r/git/refs/heads/trial/emergence-x', {'sha': 'a' * 40, 'force': False})
    assert str(exc.value) == 'provider_outcome_unknown'
    assert exc.value.__cause__ is None and exc.value.__suppress_context__ is True
    assert TOKEN not in repr(exc.value) and TOKEN not in str(exc.value)


def test_malformed_json_reply_is_unknown(api):
    api._opener = Opener(reply=b'not json')
    with pytest.raises(RuntimeError, match='provider_outcome_unknown'):
        api.request('GET', '/repos/o/r/git/commits/' + 'a' * 40)


def test_only_the_refusing_redirect_handler_is_installed(tmp_path):
    path = tmp_path / 'token'
    path.write_text(TOKEN)
    path.chmod(0o600)
    handlers = GitHubAPI(path)._opener.handlers
    redirects = [h for h in handlers if isinstance(h, HTTPRedirectHandler)]
    assert redirects and all(isinstance(h, NoRedirect) for h in redirects)


def test_token_is_not_exposed_by_the_client_object(api):
    assert TOKEN not in repr(api) and TOKEN not in str(vars(api).get('_opener'))


# ------------------------------------------------------------------ recovery reporting

def test_recovery_write_count_is_measured_and_guarded(tmp_path, monkeypatch):
    """recovery_writes is counted from calls issued; a recovery that writes is refused."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import run_demo as demo
    from local_git_provider import create_repository
    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    git_dir = tmp_path / 'repo.git'
    base, tree = create_repository(git_dir, demo.BRANCH, {'README.md': 'x\n'})
    handoff, contract, trust = demo.approve(keys, artifact=demo.APPROVED_ARTIFACT, parent_sha=base,
                                            base_tree=tree, task_id='count')
    d, provider = demo.service(tmp_path, 'svc', keys, trust, git_dir)
    result = d.dispatch(handoff, contract)
    assert result['recovery_writes'] == 0 and result['execution_authorized'] is False
    assert d.write_calls == 3                      # tree, commit, ref update
    real = enforcing_dispatcher.verify_tree_change

    def writes_during_recovery(*args):
        d.call('POST', '/git/trees', {'base_tree': tree, 'tree': []})  # a regression that writes
        return real(*args)
    monkeypatch.setattr(enforcing_dispatcher, 'verify_tree_change', writes_during_recovery)
    with pytest.raises(Exception) as exc:
        d.recover(handoff, contract)
    assert str(exc.value) == 'recovery_issued_write'


def test_contents_with_non_base64_characters_refused(tmp_path):
    """Strict decoding: characters outside the alphabet are an error, not silently dropped."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import run_demo as demo
    from local_git_provider import LocalGitProvider, create_repository
    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    git_dir = tmp_path / 'repo.git'
    base, tree = create_repository(git_dir, demo.BRANCH, {'README.md': 'x\n'})
    handoff, contract, trust = demo.approve(keys, artifact=demo.APPROVED_ARTIFACT, parent_sha=base,
                                            base_tree=tree, task_id='b64')
    d, _ = demo.service(tmp_path, 'svc', keys, trust, git_dir)
    d.dispatch(handoff, contract)
    provider = LocalGitProvider(git_dir, demo.REPOSITORY)

    class Junk:
        def request(self, method, path, body=None):
            result = provider.request(method, path, body)
            if '/contents/' in path:
                text = ''.join(result['content'].split())
                result = {**result, 'content': '*'.join(text[i:i + 4] for i in range(0, len(text), 4))}
            return result
    d.api = Junk()
    with pytest.raises(Exception):
        d.recover(handoff, contract)
    assert provider.writes() == []


# ------------------------------------------------------------------ retained journal file

def test_retained_journal_is_created_owner_only(tmp_path):
    from enforcing_dispatcher import Journal
    old = os.umask(0)          # the mode must come from the code, not from a strict umask
    try:
        Journal.initialize(tmp_path / 'journal.db')
    finally:
        os.umask(old)
    assert (tmp_path / 'journal.db').stat().st_mode & 0o777 == 0o600


def test_deleted_journal_is_never_recreated_by_an_open_service(tmp_path):
    """mode=rw: a journal removed underneath a running service is not silently replaced."""
    from enforcing_dispatcher import Journal
    path = tmp_path / 'journal.db'
    journal = Journal.initialize(path)
    path.unlink()
    with pytest.raises(Exception):
        journal.get('any-nonce')
    assert not path.exists()

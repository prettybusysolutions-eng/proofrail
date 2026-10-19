"""Synthetic provider fault injection, not a live dispatcher deployment."""
import base64
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from acceptance_bridge import Trust, full_digest
from execution_binding import ExecutionLedger
from enforcing_dispatcher import Dispatcher, Journal, GitHubAPI, NoRedirect
from live_github_trial import prepare

class Provider:
    def __init__(self):
        self.calls = []
        self.head = 'a' * 40
        self.parent_tree = 'b' * 40
        self.content = None
        self.fail_after_effect = False
        self.fail_before_effect = False

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == 'GET':
            if '/git/ref/' in path:
                return {'object': {'sha': self.head}}
            if '/git/commits/' in path:
                return {'sha': path.rsplit('/', 1)[1], 'tree': {'sha': self.parent_tree},
                        'parents': [{'sha': 'a' * 40}] if self.head != 'a' * 40 else []}
            if '/contents/' in path:
                if self.content is None:
                    raise RuntimeError('absent')
                return {'encoding': 'base64', 'content': base64.b64encode(self.content.encode()).decode()}
        if method == 'POST' and path.endswith('/trees'):
            self.content = body['tree'][0]['content']
            return {'sha': 'd' * 40}
        if method == 'POST' and path.endswith('/commits'):
            return {'sha': 'c' * 40}
        if method == 'PATCH':
            assert body['force'] is False
            if self.fail_before_effect:
                raise TimeoutError('before effect')
            self.head = body['sha']
            if self.fail_after_effect:
                raise TimeoutError('response lost after effect')
            return {'object': {'sha': self.head}}
        raise AssertionError((method, path))

@pytest.fixture
def setup(tmp_path):
    directory = tmp_path / 'fixture'
    prepare(directory, 'fixture/repo', 'trial/emergence-test', 'a' * 40, 'b' * 40)
    evidence = json.loads((directory / 'public-evidence.json').read_text())
    keys = {n: Ed25519PrivateKey.from_private_bytes(bytes.fromhex(v)) for n, v in
            json.loads((directory / 'private.json').read_text()).items()}
    env, contract = evidence['handoff'], evidence['contract']
    authority = env['payload']['authority']
    trust = Trust(evidence['public_keys']['sender'], keys['issuer'].public_key(), 'issuer-key',
                  full_digest(authority), authority['issuer'], keys['observer'].public_key(),
                  'observer-key', authority['roots'], authority['approval_digest'])
    ledger = ExecutionLedger(tmp_path / 'service.db', keys['consumer'], 'consumer-key')
    journal = Journal.initialize(tmp_path / 'retained.db')
    api = Provider()
    dispatcher = Dispatcher(ledger, journal, api, repository='fixture/repo',
                            branch='trial/emergence-test', path=contract['parameters']['path'], trust=trust)
    return dispatcher, env, contract, api

def test_dispatch_and_read_only_recovery(setup):
    d, env, contract, api = setup
    assert d.dispatch(env, contract)['outcome'] == 'MATCH'
    start = len(api.calls)
    assert d.recover(env, contract)['outcome'] == 'MATCH'
    assert all(m == 'GET' for m, _, _ in api.calls[start:])
    with pytest.raises(ValueError, match='already_reserved'):
        d.dispatch(env, contract)

def test_lost_success_response_reconciles_without_second_write(setup):
    d, env, contract, api = setup
    api.fail_after_effect = True
    with pytest.raises(TimeoutError):
        d.dispatch(env, contract)
    d.journal = Journal(d.journal.path)
    assert d.recover(env, contract)['outcome'] == 'MATCH'
    assert sum(m == 'PATCH' for m, _, _ in api.calls) == 1
    with pytest.raises(ValueError):
        d.dispatch(env, contract)

def test_timeout_before_effect_never_retries_write(setup):
    d, env, contract, api = setup
    api.fail_before_effect = True
    with pytest.raises(TimeoutError):
        d.dispatch(env, contract)
    with pytest.raises(ValueError):
        d.recover(env, contract)
    assert sum(m == 'PATCH' for m, _, _ in api.calls) == 1

def test_restored_registry_blocks_consumed_permit(setup, tmp_path):
    d, env, contract, api = setup
    backup = tmp_path / 'old.db'
    with sqlite3.connect(d.ledger.path) as src, sqlite3.connect(backup) as dest:
        src.backup(dest)
    d.dispatch(env, contract)
    with sqlite3.connect(backup) as src, sqlite3.connect(d.ledger.path) as dest:
        src.backup(dest)
    start = len(api.calls)
    with pytest.raises(ValueError, match='execution_not_found'):
        d.dispatch(env, contract)
    assert len(api.calls) == start

def test_restored_dispatch_flag_blocks_admission(setup):
    d, env, contract, api = setup
    d.dispatch(env, contract)
    with sqlite3.connect(d.ledger.path) as db:
        db.execute('UPDATE emergence_executions SET dispatch_started=0')
    with pytest.raises(ValueError, match='recovery_checkpoint_mismatch'):
        d.dispatch(env, contract)

def test_wrong_base_tree_fails_before_provider_write(setup):
    d, env, contract, api = setup
    api.parent_tree = 'e' * 40
    with pytest.raises(ValueError, match='base_tree_not_parent_tree'):
        d.dispatch(env, contract)
    assert all(m == 'GET' for m, _, _ in api.calls)

@pytest.mark.parametrize('field', ['repository', 'branch', 'path'])
def test_service_scope_cannot_be_changed_by_request(setup, field):
    d, env, contract, api = setup
    contract = copy.deepcopy(contract)
    contract['parameters'][field] = 'other'
    with pytest.raises(ValueError, match='scope_mismatch'):
        d.dispatch(env, contract)
    assert not api.calls

def test_invalid_signed_task_has_no_provider_calls(setup):
    d, env, contract, api = setup
    env['payload']['task']['artifact'] = 'changed'
    with pytest.raises(ValueError):
        d.dispatch(env, contract)
    assert not api.calls

def test_parallel_dispatch_has_one_writer(setup):
    d, env, contract, api = setup
    def attempt(_):
        try:
            return d.dispatch(env, contract)['outcome']
        except ValueError:
            return 'REJECTED'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(outcomes) == ['MATCH', 'REJECTED']
    assert sum(m == 'PATCH' for m, _, _ in api.calls) == 1

def test_missing_journal_not_reinitialized(setup):
    d, *_ = setup
    d.journal.path.unlink()
    with pytest.raises(ValueError, match='retained_journal_missing'):
        Journal(d.journal.path)

def test_journal_exclusive_init(setup):
    d, *_ = setup
    with pytest.raises(FileExistsError):
        Journal.initialize(d.journal.path)

def test_credentials_require_private_file(tmp_path):
    p = tmp_path / 'token'
    p.write_text('fake-token')
    p.chmod(0o644)
    with pytest.raises(ValueError, match='credential_permissions'):
        GitHubAPI(p)
    p.chmod(0o600)
    assert GitHubAPI(p)

def test_redirect_never_forwards_credentials():
    with pytest.raises(ValueError, match='redirect_rejected'):
        NoRedirect().redirect_request(None, None, 302, '', {}, 'https://attacker.test')

class DurableProvider(Provider):
    """Synthetic destination persisted across an abrupt worker exit."""
    def __init__(self, state, kill=False):
        super().__init__()
        self.state, self.kill = state, kill
        if state.exists():
            saved = json.loads(state.read_text())
            self.head, self.content = saved['head'], saved['content']

    def request(self, method, path, body=None):
        result = super().request(method, path, body)
        if method == 'PATCH':
            import os
            with self.state.open('w') as stream:
                json.dump({'head': self.head, 'content': self.content}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if self.kill:
                os._exit(73)
        return result


def test_abrupt_process_death_after_effect_recovers_read_only(setup, tmp_path):
    import multiprocessing
    d, env, contract, _ = setup
    state = tmp_path / 'provider.json'
    d.api = DurableProvider(state, kill=True)
    process = multiprocessing.get_context('fork').Process(target=d.dispatch, args=(env, contract))
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail('worker did not exit')
    assert process.exitcode == 73
    d.api = DurableProvider(state)
    assert d.recover(env, contract)['outcome'] == 'MATCH'
    assert all(method == 'GET' for method, _, _ in d.api.calls)


def test_incomplete_checkpoint_blocks_following_work(setup):
    from acceptance_bridge import verify_handoff
    import time
    d, env, contract, api = setup
    binding = verify_handoff(env, contract, d.trust, now=int(time.time()))
    d.journal.reserve(env['payload']['authority'], binding)
    with pytest.raises(ValueError, match='incomplete_checkpoint'):
        d.dispatch(env, contract)
    assert not api.calls


def test_cli_service_loads_only_pinned_operator_trust(setup, tmp_path):
    from dispatcher_cli import load_service
    from smatp import encode_public
    from cryptography.hazmat.primitives import serialization
    d, env, contract, _ = setup
    key = tmp_path / 'consumer.key'
    key.write_text(d.ledger.private_key.private_bytes(serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex())
    token = tmp_path / 'github.token'
    token.write_text('synthetic-no-live-access')
    trust = dict(vars(d.trust))
    for name in ('authority_public', 'observer_public'):
        trust[name] = encode_public(trust[name])
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(trust=trust, consumer_key_file=str(key),
        consumer_key_id=d.ledger.key_id, journal_path=str(d.journal.path),
        registry_path=str(d.ledger.path), github_token_file=str(token),
        repository=d.repository, branch=d.branch, path=d.path)))
    for path in (config, key, token):
        path.chmod(0o600)
    service = load_service(config)
    assert service.trust.authority_digest == d.trust.authority_digest
    assert service.repository == d.repository

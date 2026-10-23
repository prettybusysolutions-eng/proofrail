"""One test per safety check on the pilot dispatcher path, pinned to its exact reason.

Removing any single require(...) used to leave the suite green for 78 of 110
checks: earlier tests asserted only that *something* raised, so a later layer
could silently stand in for a missing one. Each test here builds the specific
input a check exists to reject, enters through the dispatcher wherever that is
reachable (direct calls only where earlier layers make it unreachable), and
asserts that exact reason, plus zero provider writes on dispatch paths.
"""
import base64
import copy
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEMO = Path(__file__).resolve().parents[1] / 'buyer_demo'
sys.path.insert(0, str(DEMO))
import run_demo as demo  # noqa: E402
from acceptance_bridge import Trust, full_digest, verify_handoff  # noqa: E402
from enforcing_dispatcher import Dispatcher, GitHubAPI, Journal  # noqa: E402
from execution_binding import ExecutionLedger  # noqa: E402
from github_artifact import prepare_commit, verify_commit, verify_tree_change  # noqa: E402
from local_git_provider import LocalGitProvider, create_repository, git  # noqa: E402
from proofrail.envelope import mint_action_authority_envelope  # noqa: E402
from smatp import encode_public, make_envelope, sign, unsigned  # noqa: E402

R, B, P = demo.REPOSITORY, demo.BRANCH, demo.PATH
# A schema-valid checkpoint block (action_authority_envelope.schema.json 'trust').
CHECKPOINT_TRUST = {'replay_root': 'a' * 64, 'checkpoint_root': 'b' * 64,
                    'observation_root': 'c' * 64, 'minimum_checkpoint_epoch': 0,
                    'monotonic_counter': 0}


def reason(exc_info):
    return str(exc_info.value)


class World:
    """A valid approval, dispatcher and real local repository; tests perturb one thing."""

    def __init__(self, tmp_path, **variant):
        self.tmp = tmp_path
        self.keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
        self.git_dir = tmp_path / 'repo.git'
        self.base, self.base_tree = create_repository(self.git_dir, B, {'README.md': 'base\n'})
        self.handoff, self.contract, self.trust = self.approve(**variant)
        self.dispatcher, self.provider = demo.service(tmp_path, 'svc', self.keys, self.trust, self.git_dir)

    def approve(self, *, artifact=demo.APPROVED_ARTIFACT, params=None, target=None, expected=None,
                subject='dispatcher', issued_in=0, authority_extra=None, contract_edit=None):
        params = params or dict(repository=R, branch=B, path=P, parent_sha=self.base, base_tree=self.base_tree)
        task = {'artifact': artifact}
        roots = {n: full_digest({'root': n}) for n in ('identity', 'evidence', 'policy', 'state')}
        approval = full_digest({'approve': True, **params})
        contract = dict(kind='emergence.acceptance.v1', tenant='demo-team', task_id='reasons',
                        sender='report-agent', recipient='dispatcher', capability='publish-artifact',
                        task_digest=full_digest(task), action_type='github_artifact_commit',
                        target=target or 'github:%s:%s:%s' % (R, B, P), parameters=params,
                        expected_sha256=expected or hashlib.sha256(str(artifact).encode()).hexdigest(),
                        observer='dispatcher-readback', observer_key_id='observer-key',
                        max_observation_age_seconds=3600)
        if contract_edit:
            contract_edit(contract)
        now = int(time.time())
        authority = mint_action_authority_envelope(
            roots=roots, approval_digest=approval, action_type=contract['action_type'],
            target=contract['target'], parameters=params, subject_principal_id=subject,
            subject_role='executor', issuer_principal_id='report-approver', issuer_role='verifier',
            adapter_contract={'name': 'github-git-data', 'version': 'v1', 'idempotency_required': True},
            observation_contract={'name': 'emergence.acceptance', 'version': 'v1', 'minimum_confirmations': 1,
                                  'success_predicate_digest': full_digest(contract)},
            nonce=secrets.token_hex(32), expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            private_key=self.keys['approver'], key_id='approver-key',
            now=datetime.fromtimestamp(now + issued_in, timezone.utc), **(authority_extra or {}))
        handoff = make_envelope('report-agent', 'dispatcher', 'publish-artifact',
                                {'task': task, 'contract': contract, 'authority': authority},
                                self.keys['agent'], now=now, ttl=3600)
        trust = Trust(encode_public(self.keys['agent'].public_key()), self.keys['approver'].public_key(),
                      'approver-key', full_digest(authority), authority['issuer'],
                      self.keys['observer'].public_key(), 'observer-key', roots, approval)
        return handoff, contract, trust

    def resign(self, edit):
        """The agent re-signs a handoff it changed, with its own valid key."""
        fields = unsigned(copy.deepcopy(self.handoff))
        edit(fields)
        return sign(fields, self.keys['agent'])

    def with_trust(self, **changes):
        self.dispatcher.trust = Trust(**{**vars(self.trust), **changes})

    def dispatch_refused(self, handoff=None, contract=None, **kw):
        handoff = handoff or self.handoff
        contract = contract if contract is not None else handoff['payload']['contract']
        with pytest.raises(Exception) as exc:
            self.dispatcher.dispatch(handoff, contract, **kw)
        assert self.provider.writes() == [], 'refused dispatch reached a provider write'
        return reason(exc)

    def dispatched(self):
        result = self.dispatcher.dispatch(self.handoff, self.contract)
        assert result['outcome'] == 'MATCH'
        return result

    def journal_sql(self, sql, *args):
        with sqlite3.connect(self.dispatcher.journal.path) as db:
            db.execute(sql, args)

    def registry_sql(self, sql, *args):
        with sqlite3.connect(self.dispatcher.ledger.path) as db:
            db.execute(sql, args)


# ------------------------------------------------------------------ credential client

def token_file(tmp_path, text, mode=0o600):
    path = tmp_path / 'token'
    path.write_text(text)
    path.chmod(mode)
    return path


def test_credential_file_must_not_be_a_symlink(tmp_path):
    real = token_file(tmp_path, 'secret-token')
    link = tmp_path / 'link'
    os.symlink(real, link)
    with pytest.raises(Exception) as exc:
        GitHubAPI(link)
    assert reason(exc) == 'credential_file_required'


@pytest.mark.parametrize('text', ['', '   \n', 'abc\ndef', 'abc\rdef'])
def test_credential_must_be_one_line(tmp_path, text):
    with pytest.raises(Exception) as exc:
        GitHubAPI(token_file(tmp_path, text))
    assert reason(exc) == 'invalid_credential'


@pytest.mark.parametrize('path', ['/user', '/repos/a/b\r\nX-Injected: 1', 'repos/a/b'])
def test_api_path_is_fixed_to_repository_routes(tmp_path, path):
    api = GitHubAPI(token_file(tmp_path, 'secret-token'))
    with pytest.raises(Exception) as exc:
        api.request('GET', path)        # refused before any network I/O
    assert reason(exc) == 'invalid_api_path'


# ------------------------------------------------------------------ service configuration

def test_registry_and_journal_must_be_separate_files(tmp_path):
    w = World(tmp_path)
    shared = tmp_path / 'shared.db'
    journal = Journal.initialize(shared)
    ledger = ExecutionLedger(shared, w.keys['consumer'], 'consumer-key')
    with pytest.raises(Exception) as exc:
        Dispatcher(ledger, journal, w.provider, repository=R, branch=B, path=P, trust=w.trust)
    assert reason(exc) == 'separate_journal_required'


@pytest.mark.parametrize('field,value,expected', [
    ('repository', 'owner/repo/extra', 'invalid_repository'),
    ('repository', 'owner repo', 'invalid_repository'),
    ('branch', 'main', 'invalid_branch'),
    ('branch', 'trial/emergence-x/../main', 'invalid_branch'),
    ('path', 'src/app.py', 'invalid_path'),
    ('path', 'evidence/../src/app.py', 'invalid_path'),
    ('path', 'evidence/a..json', 'invalid_path'),
])
def test_service_scope_is_validated_at_construction(tmp_path, field, value, expected):
    w = World(tmp_path)
    args = dict(repository=R, branch=B, path=P, trust=w.trust)
    args[field] = value
    ledger = ExecutionLedger(tmp_path / 'r.db', w.keys['consumer'], 'consumer-key')
    with pytest.raises(Exception) as exc:
        Dispatcher(ledger, Journal.initialize(tmp_path / 'j.db'), w.provider, **args)
    assert reason(exc) == expected


# ------------------------------------------------------------------ dispatch admission

def test_unsupported_action_refused(tmp_path):
    w = World(tmp_path)
    contract = {**w.contract, 'capability': 'merge-pull-request'}
    assert w.dispatch_refused(contract=contract) == 'unsupported_dispatch_action'


def test_git_object_ids_must_be_full_hex(tmp_path):
    w = World(tmp_path)
    contract = copy.deepcopy(w.contract)
    contract['parameters']['parent_sha'] = w.base[:12]
    assert w.dispatch_refused(contract=contract) == 'invalid_git_object'


def test_checkpoint_bearing_authority_refused_before_reservation(tmp_path):
    w = World(tmp_path, authority_extra={'trust': CHECKPOINT_TRUST})
    assert w.dispatch_refused() == 'checkpoint_authority_not_supported'
    with sqlite3.connect(w.dispatcher.journal.path) as db:
        assert db.execute('SELECT COUNT(*) FROM dispatches').fetchone()[0] == 0


def test_moved_branch_refused_before_any_write(tmp_path):
    from local_git_provider import commit_file
    w = World(tmp_path)
    commit_file(w.git_dir, B, 'README.md', 'moved\n', 'Someone else')
    assert w.dispatch_refused() == 'branch_parent_changed'


def test_base_tree_must_be_the_parent_tree(tmp_path):
    w = World(tmp_path)
    other = create_repository(tmp_path / 'other.git', B, {'x': 'y\n'})[1]
    git(w.git_dir, 'fetch', '-q', str(tmp_path / 'other.git'), B)  # make the object exist
    params = dict(repository=R, branch=B, path=P, parent_sha=w.base, base_tree=other)
    w.handoff, w.contract, w.trust = w.approve(params=params)
    w.dispatcher.trust = w.trust
    assert w.dispatch_refused() == 'base_tree_not_parent_tree'


# ------------------------------------------------------------------ commit preparation

def test_extra_signed_parameter_refused_before_write(tmp_path):
    w = World(tmp_path)
    params = dict(repository=R, branch=B, path=P, parent_sha=w.base, base_tree=w.base_tree, mode='100755')
    w.handoff, w.contract, w.trust = w.approve(params=params)
    w.dispatcher.trust = w.trust
    assert w.dispatch_refused() == 'github_scope_fields'


def test_target_must_name_repository_branch_and_path(tmp_path):
    w = World(tmp_path, target='github:%s:%s:evidence/other.json' % (R, B))
    assert w.dispatch_refused() == 'github_target_changed'


def test_artifact_must_be_text(tmp_path):
    w = World(tmp_path, artifact={'text': 'not a string'}, expected='a' * 64)
    assert w.dispatch_refused() == 'artifact_text_required'


def test_artifact_must_match_approved_digest(tmp_path):
    w = World(tmp_path, expected=hashlib.sha256(b'something else').hexdigest())
    assert w.dispatch_refused() == 'artifact_digest_changed'


@pytest.mark.parametrize('edit,expected', [
    (lambda c: c.update(action_type='artifact_write'), 'wrong_github_action'),
    (lambda c: c['parameters'].update(branch='main'), 'trial_branch_required'),
    (lambda c: c['parameters'].update(path='src/app.py'), 'evidence_path_required'),
])
def test_prepare_commit_guards_hold_when_called_directly(tmp_path, edit, expected):
    """Unreachable through Dispatcher (its scope check runs first); kept as defence in depth."""
    w = World(tmp_path)
    contract = copy.deepcopy(w.contract)
    edit(contract)
    with pytest.raises(Exception) as exc:
        prepare_commit(w.dispatcher.ledger, 'unused', w.handoff, contract, w.trust)
    assert reason(exc) == expected


# ------------------------------------------------------------------ recovery

def test_recover_without_reservation(tmp_path):
    w = World(tmp_path)
    with pytest.raises(Exception) as exc:
        w.dispatcher.recover(w.handoff, w.contract)
    assert reason(exc) == 'journal_reservation_missing'


def test_recover_with_incomplete_reservation(tmp_path):
    w = World(tmp_path)
    binding = verify_handoff(w.handoff, w.contract, w.trust, now=int(time.time()))
    w.dispatcher.journal.reserve(w.handoff['payload']['authority'], binding)
    with pytest.raises(Exception) as exc:
        w.dispatcher.recover(w.handoff, w.contract)
    assert reason(exc) == 'reservation_incomplete_no_retry'


@pytest.mark.parametrize('column,expected', [('authority', 'journal_authority_changed'),
                                             ('binding', 'journal_binding_changed')])
def test_recover_detects_tampered_journal_row(tmp_path, column, expected):
    w = World(tmp_path)
    w.dispatched()
    w.journal_sql('UPDATE dispatches SET %s=?' % column, 'f' * 64)
    with pytest.raises(Exception) as exc:
        w.dispatcher.recover(w.handoff, w.contract)
    assert reason(exc) == expected
    assert w.provider.writes()[-1][0] == 'PATCH'  # no write after the original dispatch


def test_recover_detects_reset_dispatch_flag(tmp_path):
    w = World(tmp_path)
    w.dispatched()
    w.registry_sql('UPDATE emergence_executions SET dispatch_started=0')
    with pytest.raises(Exception) as exc:
        w.dispatcher.recover(w.handoff, w.contract)
    assert reason(exc) == 'restored_dispatch_state'


class Rewrite:
    def __init__(self, provider, match, edit):
        self.provider, self.match, self.edit = provider, match, edit

    def request(self, method, path, body=None):
        result = self.provider.request(method, path, body)
        return self.edit(copy.deepcopy(result)) if method == 'GET' and self.match(path) else result


@pytest.mark.parametrize('match,edit,expected', [
    (lambda p: '/git/ref/' in p, lambda r: {**r, 'object': {'sha': 'z' * 40}}, 'invalid_provider_sha'),
    (lambda p: '/git/commits/' in p, lambda r: {**r, 'tree': {'sha': 'z' * 40}}, 'invalid_provider_sha'),
    (lambda p: '/contents/' in p, lambda r: {**r, 'encoding': 'utf-8'}, 'provider_encoding'),
    (lambda p: '/contents/' in p, lambda r: {**r, 'content': base64.b64encode(json.dumps(
        {**json.loads(base64.b64decode(''.join(r['content'].split()))), 'tenant': 'other'},
        sort_keys=True, indent=2).encode() + b'\n').decode()}, 'github_content_or_provenance_changed'),
    (lambda p: '/contents/' in p, lambda r: {**r, 'content': base64.b64encode(json.dumps(
        json.loads(base64.b64decode(''.join(r['content'].split()))), sort_keys=True).encode()).decode()},
     'github_exact_bytes_changed'),
    (lambda p: '/git/trees/' in p, lambda r: {**r, 'tree': [{'path': 'x'}]}, 'tree_entry_invalid'),
    (lambda p: '/git/trees/' in p, lambda r: {**r, 'tree': r['tree'] + r['tree'][:1]}, 'tree_entry_duplicate'),
    (lambda p: '/git/trees/' in p, lambda r: {**r, 'truncated': True}, 'tree_listing_incomplete'),
])
def test_recover_refuses_each_corrupted_response_for_its_own_reason(tmp_path, match, edit, expected):
    w = World(tmp_path)
    w.dispatched()
    provider = LocalGitProvider(w.git_dir, R)
    w.dispatcher.api = Rewrite(provider, match, edit)
    with pytest.raises(Exception) as exc:
        w.dispatcher.recover(w.handoff, w.contract)
    assert reason(exc) == expected
    assert provider.writes() == []


def test_verify_commit_requires_started_dispatch(tmp_path):
    """recover checks the flag first; verify_commit keeps its own guard."""
    w = World(tmp_path)
    claim = w.dispatcher.ledger.consume(w.handoff, w.contract, w.trust)
    with pytest.raises(Exception) as exc:
        verify_commit(w.dispatcher.ledger, claim['execution_id'], w.handoff, w.contract, w.trust,
                      commit={'sha': w.base, 'parents': []}, file_content='', repository=R, path=P,
                      observed_ref=w.base)
    assert reason(exc) == 'dispatch_not_started'


def test_verify_commit_rejects_another_approval_for_this_execution(tmp_path):
    w = World(tmp_path)
    first = w.dispatched()
    h2, c2, t2 = w.approve()
    with pytest.raises(Exception) as exc:
        verify_commit(w.dispatcher.ledger, first['execution_id'], h2, c2, t2,
                      commit={'sha': first['commit_sha'], 'parents': [{'sha': w.base}]},
                      file_content='', repository=R, path=P, observed_ref=first['commit_sha'])
    assert reason(exc) == 'consumption_binding_changed'


def test_verify_commit_checks_approved_digest_of_written_text(tmp_path):
    """prepare_commit refuses this before writing; verify_commit keeps its own guard."""
    w = World(tmp_path, expected=hashlib.sha256(b'other').hexdigest())
    ledger = w.dispatcher.ledger
    claim = ledger.consume(w.handoff, w.contract, w.trust)
    consumption = ledger.begin_dispatch(claim['execution_id'], w.handoff, w.contract, w.trust)
    content = json.dumps({'kind': 'emergence.github-artifact.v1', 'execution_id': claim['execution_id'],
                          'consumption_digest': full_digest(consumption), 'tenant': w.contract['tenant'],
                          'task_id': w.contract['task_id'], 'artifact': demo.APPROVED_ARTIFACT},
                         sort_keys=True, indent=2) + '\n'
    with pytest.raises(Exception) as exc:
        verify_commit(ledger, claim['execution_id'], w.handoff, w.contract, w.trust,
                      commit={'sha': 'c' * 40, 'parents': [{'sha': w.base}]}, file_content=content,
                      repository=R, path=P, observed_ref='c' * 40)
    assert reason(exc) == 'artifact_digest_changed'


# ------------------------------------------------------------------ retained journal

def test_double_prepare_refused(tmp_path):
    w = World(tmp_path)
    binding = verify_handoff(w.handoff, w.contract, w.trust, now=int(time.time()))
    j = w.dispatcher.journal
    j.reserve(w.handoff['payload']['authority'], binding)
    nonce = w.handoff['payload']['authority']['nonce']
    j.prepared(nonce, 'e1', {'consumption_digest': 'x'}, 'root')
    with pytest.raises(Exception) as exc:
        j.prepared(nonce, 'e2', {'consumption_digest': 'y'}, 'root')
    assert reason(exc) == 'journal_prepare_conflict'


@pytest.mark.parametrize('column', ['nonce', 'authority'])
def test_journal_row_must_name_the_consumed_permit(tmp_path, column):
    w = World(tmp_path)
    w.dispatched()
    w.journal_sql('UPDATE dispatches SET %s=?' % column, 'f' * 64)
    with pytest.raises(Exception) as exc:
        w.dispatcher.journal.verify_recovery_state(w.dispatcher.ledger)
    assert reason(exc) == 'recovery_claim_mismatch'


# ------------------------------------------------------------------ registry records

@pytest.mark.parametrize('edit,expected', [
    (lambda r: r.update(kind='other'), 'consumption_kind'),
    (lambda r: r.update(execution_id='other'), 'consumption_execution_changed'),
    (lambda r: r['signature'].update(key_id='other-key'), 'consumption_key_changed'),
])
def test_registry_record_tampering_named_before_signature_check(tmp_path, edit, expected):
    w = World(tmp_path)
    claim = w.dispatcher.ledger.consume(w.handoff, w.contract, w.trust)
    with sqlite3.connect(w.dispatcher.ledger.path) as db:
        body = json.loads(db.execute('SELECT body FROM emergence_executions').fetchone()[0])
        edit(body)
        db.execute('UPDATE emergence_executions SET body=?', (json.dumps(body),))
    with pytest.raises(Exception) as exc:
        w.dispatcher.ledger.get(claim['execution_id'])
    assert reason(exc) == expected


def test_begin_dispatch_rejects_a_different_approval(tmp_path):
    w = World(tmp_path)
    claim = w.dispatcher.ledger.consume(w.handoff, w.contract, w.trust)
    h2, c2, t2 = w.approve()
    with pytest.raises(Exception) as exc:
        w.dispatcher.ledger.begin_dispatch(claim['execution_id'], h2, c2, t2)
    assert reason(exc) == 'dispatch_handoff_digest_changed'


def test_ledger_refuses_checkpoint_bearing_authority(tmp_path):
    w = World(tmp_path, authority_extra={'trust': CHECKPOINT_TRUST})
    with pytest.raises(Exception) as exc:
        w.dispatcher.ledger.consume(w.handoff, w.contract, w.trust)
    assert reason(exc) == 'checkpoint_authority_not_supported'


# ------------------------------------------------------------------ handoff verification

def test_integer_clock_required(tmp_path):
    w = World(tmp_path)
    with pytest.raises(Exception) as exc:
        verify_handoff(w.handoff, w.contract, w.trust, now=time.time())
    assert reason(exc) == 'integer_clock_required'


def test_parameters_must_be_an_object(tmp_path):
    w = World(tmp_path)
    with pytest.raises(Exception) as exc:
        verify_handoff(w.handoff, {**w.contract, 'parameters': []}, w.trust, now=int(time.time()))
    assert reason(exc) == 'invalid_parameters'


@pytest.mark.parametrize('edit,expected', [
    (lambda c: c.update(extra=1), 'invalid_contract_fields'),
    (lambda c: c.update(kind='emergence.acceptance.v2'), 'contract_version'),
    (lambda c: c.update(tenant=''), 'invalid_tenant'),
    (lambda c: c.update(task_digest='A' * 64), 'invalid_task_digest'),
    (lambda c: c.update(max_observation_age_seconds=0), 'invalid_observation_age'),
    (lambda c: c.update(max_observation_age_seconds=True), 'invalid_observation_age'),
    (lambda c: c.update(observer_key_id='other-observer'), 'observer_key_changed'),
])
def test_contract_shape_checks(tmp_path, edit, expected):
    w = World(tmp_path)
    contract = copy.deepcopy(w.contract)
    edit(contract)
    assert w.dispatch_refused(contract=contract) == expected


@pytest.mark.parametrize('edit,expected', [
    (lambda h: h.update(extra='x'), 'invalid_handoff_fields'),
    (lambda h: h.update(version='smatp/0.2'), 'handoff_version'),
    (lambda h: h.update(message_id=''), 'invalid_message_id'),
    (lambda h: h.update(nonce='n' * 129), 'invalid_nonce'),
    (lambda h: h.update(created_at=str(h['created_at'])), 'invalid_handoff_time'),
    (lambda h: h.update(expires_at=h['created_at'] + 90000), 'handoff_expired_or_future'),
    (lambda h: h.update(recipient='someone-else'), 'recipient_changed'),
    (lambda h: h.update(sender_key_id='0' * 24), 'sender_key_changed'),
    (lambda h: h['payload'].update(extra={}), 'invalid_payload'),
])
def test_agent_resigned_handoff_shape_checks(tmp_path, edit, expected):
    w = World(tmp_path)
    handoff = w.resign(edit)
    assert w.dispatch_refused(handoff=handoff, contract=w.contract) == expected


@pytest.mark.parametrize('change,expected', [
    ({'authority_key_id': 'other-key'}, 'authority_key_changed'),
    ({'issuer': {'principal_id': 'someone-else', 'role': 'verifier'}}, 'issuer_changed'),
])
def test_misconfigured_trust_refused(tmp_path, change, expected):
    w = World(tmp_path)
    w.with_trust(**change)
    assert w.dispatch_refused() == expected


def test_authority_for_another_executor_refused(tmp_path):
    w = World(tmp_path, subject='another-executor')
    assert w.dispatch_refused() == 'subject_changed'


def test_authority_issued_in_the_future_refused(tmp_path):
    w = World(tmp_path, issued_in=600)
    assert w.dispatch_refused() == 'authority_not_yet_valid'


def test_tree_change_helper_rejects_non_list_listing():
    with pytest.raises(Exception) as exc:
        verify_tree_change({'truncated': False, 'tree': None}, {'truncated': False, 'tree': []}, P, '')
    assert reason(exc) == 'tree_listing_incomplete'

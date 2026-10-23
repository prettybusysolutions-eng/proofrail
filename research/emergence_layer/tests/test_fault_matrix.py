"""Exhaustive interruption and malformed-response matrices for the pilot dispatcher.

Against a real local git repository (buyer_demo/local_git_provider.py):

1. Interrupt dispatch at every step boundary, local and provider-side. After a
   restart over the same stores, for every point: recovery issues no write;
   recovery reports MATCH if and only if the branch update took effect; the
   permit can never be used again; at most one dispatcher commit exists.
2. Corrupt each provider response the dispatcher reads. A corrupted response
   must never yield MATCH, and recovery must never write.

This is not GitHub and not transport-level fault injection.
"""
import base64
import copy
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEMO = Path(__file__).resolve().parents[1] / 'buyer_demo'
sys.path.insert(0, str(DEMO))
import run_demo as demo  # noqa: E402
import enforcing_dispatcher  # noqa: E402
from enforcing_dispatcher import Dispatcher, Journal  # noqa: E402
from execution_binding import ExecutionLedger  # noqa: E402
from local_git_provider import LocalGitProvider, create_repository, git  # noqa: E402


class Crash(Exception):
    """Stands in for the process dying at this point; stores keep what was committed."""


class Installation:
    def __init__(self, tmp_path):
        self.keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
        self.git_dir = tmp_path / 'repo.git'
        self.base, tree = create_repository(self.git_dir, demo.BRANCH, {'README.md': 'base\n'})
        self.handoff, self.contract, self.trust = demo.approve(
            self.keys, artifact=demo.APPROVED_ARTIFACT, parent_sha=self.base, base_tree=tree, task_id='matrix')
        self.dispatcher, self.provider = demo.service(tmp_path, 'svc', self.keys, self.trust, self.git_dir)

    def restart(self, api=None):
        """A new process over the same registry and retained journal."""
        api = api or LocalGitProvider(self.git_dir, demo.REPOSITORY)
        d = Dispatcher(ExecutionLedger(self.dispatcher.ledger.path, self.keys['consumer'], 'consumer-key'),
                       Journal(self.dispatcher.journal.path), api, repository=demo.REPOSITORY,
                       branch=demo.BRANCH, path=demo.PATH, trust=self.trust)
        return d, api

    def head(self):
        return git(self.git_dir, 'rev-parse', 'refs/heads/' + demo.BRANCH).decode().strip()

    def dispatcher_commits(self):
        log = git(self.git_dir, 'log', '--format=%s', self.base + '..refs/heads/' + demo.BRANCH).decode()
        return [line for line in log.splitlines() if line.startswith('ProofRail execution ')]


class CrashAtCall:
    """Provider wrapper: on call number `n`, crash before or after the real call."""
    def __init__(self, provider, n, after):
        self.provider, self.n, self.after, self.count = provider, n, after, 0

    def request(self, method, path, body=None):
        self.count += 1
        if self.count == self.n and not self.after:
            raise Crash('before call %d (%s)' % (self.n, method))
        result = self.provider.request(method, path, body)
        if self.count == self.n:
            raise Crash('after call %d (%s)' % (self.n, method))
        return result


# Dispatch issues: 1 GET ref, 2 GET commit, 3 POST tree, 4 POST commit, 5 PATCH ref, then readback.
PROVIDER_POINTS = [(n, after) for n in range(1, 6) for after in (False, True)]
LOCAL_POINTS = ['before_consume', 'before_begin_dispatch', 'after_begin_dispatch', 'after_journal_prepared']


def crash_locally(inst, monkeypatch, point):
    d = inst.dispatcher
    if point == 'before_consume':
        monkeypatch.setattr(d.ledger, 'consume', lambda *a, **k: (_ for _ in ()).throw(Crash(point)))
    elif point == 'before_begin_dispatch':
        monkeypatch.setattr(d.ledger, 'begin_dispatch', lambda *a, **k: (_ for _ in ()).throw(Crash(point)))
    elif point == 'after_begin_dispatch':
        real = enforcing_dispatcher.prepare_commit

        def prepare(*a, **k):
            real(*a, **k)
            raise Crash(point)
        monkeypatch.setattr(enforcing_dispatcher, 'prepare_commit', prepare)
    elif point == 'after_journal_prepared':
        real = d.journal.prepared

        def prepared(*a, **k):
            real(*a, **k)
            raise Crash(point)
        monkeypatch.setattr(d.journal, 'prepared', prepared)


def check_after_crash(inst):
    effect = inst.head() != inst.base
    recovered, api = inst.restart()
    try:
        outcome = recovered.recover(inst.handoff, inst.contract)['outcome']
    except Exception:  # noqa: BLE001 - refusal is acceptable; false MATCH is not
        outcome = 'REFUSED'
    assert api.writes() == [], 'recovery issued a write'
    assert (outcome == 'MATCH') == effect, 'MATCH must mean exactly that the branch update took effect'
    again, api2 = inst.restart()
    with pytest.raises(Exception):
        again.dispatch(inst.handoff, inst.contract)
    assert api2.writes() == [], 'a used or burned permit reached a provider write'
    assert len(inst.dispatcher_commits()) == (1 if effect else 0)


@pytest.mark.parametrize('n,after', PROVIDER_POINTS,
                         ids=['%s call %d' % ('after' if a else 'before', n) for n, a in PROVIDER_POINTS])
def test_interrupted_at_provider_call(tmp_path, n, after):
    inst = Installation(tmp_path)
    inst.dispatcher.api = CrashAtCall(inst.provider, n, after)
    with pytest.raises(Crash):
        inst.dispatcher.dispatch(inst.handoff, inst.contract)
    check_after_crash(inst)


@pytest.mark.parametrize('point', LOCAL_POINTS)
def test_interrupted_before_any_provider_call(tmp_path, monkeypatch, point):
    inst = Installation(tmp_path)
    crash_locally(inst, monkeypatch, point)
    with pytest.raises(Crash):
        inst.dispatcher.dispatch(inst.handoff, inst.contract)
    monkeypatch.undo()
    assert inst.provider.writes() == []
    check_after_crash(inst)


def test_interrupted_during_readback_after_effect(tmp_path):
    """Crash after the branch update, during dispatch's own confirmation reads."""
    inst = Installation(tmp_path)
    inst.dispatcher.api = CrashAtCall(inst.provider, 6, after=False)
    with pytest.raises(Crash):
        inst.dispatcher.dispatch(inst.handoff, inst.contract)
    check_after_crash(inst)


# ---------------------------------------------------------------- malformed responses

def other_sha(inst):
    return inst.base


def b64(text):
    return base64.encodebytes(text.encode()).decode()


def set_path(obj, keys, value):
    target = obj
    for k in keys[:-1]:
        target = target[k]
    if value is DELETE:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value


DELETE = object()

# (label, which GET in recovery, mutation(response, inst) -> response)
RECOVERY_MUTATIONS = [
    ('ref points elsewhere', 'ref', lambda r, i: {**r, 'object': {'sha': i.base}}),
    ('ref sha not hex', 'ref', lambda r, i: {**r, 'object': {'sha': 'z' * 40}}),
    ('ref object missing', 'ref', lambda r, i: {k: v for k, v in r.items() if k != 'object'}),
    ('commit has no parent', 'commit', lambda r, i: {**r, 'parents': []}),
    ('commit has two parents', 'commit', lambda r, i: {**r, 'parents': r['parents'] * 2}),
    ('commit reports base tree', 'commit', lambda r, i: {**r, 'tree': {'sha': i.base_tree}}),
    ('commit tree not hex', 'commit', lambda r, i: {**r, 'tree': {'sha': 'z' * 40}}),
    ('commit sha differs', 'commit', lambda r, i: {**r, 'sha': i.base}),
    ('contents not base64', 'contents', lambda r, i: {**r, 'encoding': 'utf-8'}),
    ('contents one byte changed', 'contents', lambda r, i: {**r, 'content': b64(
        base64.b64decode(''.join(r['content'].split())).decode().replace('99.95', '99.96'))}),
    ('contents empty', 'contents', lambda r, i: {**r, 'content': ''}),
    ('contents invalid base64', 'contents', lambda r, i: {**r, 'content': '@@@@'}),
    ('head tree truncated', 'head_tree', lambda r, i: {**r, 'truncated': True}),
    ('head tree truncated missing', 'head_tree', lambda r, i: {k: v for k, v in r.items() if k != 'truncated'}),
    ('head tree truncated as string', 'head_tree', lambda r, i: {**r, 'truncated': 'false'}),
    ('head tree extra file', 'head_tree', lambda r, i: {**r, 'tree': r['tree'] + [
        {'path': 'deploy/run.sh', 'mode': '100755', 'type': 'blob', 'sha': 'e' * 40}]}),
    ('head tree file executable', 'head_tree', lambda r, i: {**r, 'tree': [
        {**e, 'mode': '100755'} if e['path'] == demo.PATH else e for e in r['tree']]}),
    ('head tree file as symlink', 'head_tree', lambda r, i: {**r, 'tree': [
        {**e, 'mode': '120000'} if e['path'] == demo.PATH else e for e in r['tree']]}),
    ('head tree file blob differs', 'head_tree', lambda r, i: {**r, 'tree': [
        {**e, 'sha': 'e' * 40} if e['path'] == demo.PATH else e for e in r['tree']]}),
    ('head tree duplicate entry', 'head_tree', lambda r, i: {**r, 'tree': r['tree'] + [
        next(e for e in r['tree'] if e['path'] == demo.PATH)]}),
    ('head tree missing file', 'head_tree', lambda r, i: {**r, 'tree': [
        e for e in r['tree'] if e['path'] != demo.PATH]}),
    ('head tree not a list', 'head_tree', lambda r, i: {**r, 'tree': None}),
    ('base tree lost an entry', 'base_tree', lambda r, i: {**r, 'tree': [
        e for e in r['tree'] if e['path'] != 'README.md']}),
    ('base tree gained an entry', 'base_tree', lambda r, i: {**r, 'tree': r['tree'] + [
        {'path': 'extra.txt', 'mode': '100644', 'type': 'blob', 'sha': 'e' * 40}]}),
    ('base tree truncated', 'base_tree', lambda r, i: {**r, 'truncated': True}),
]


class Mutating:
    def __init__(self, provider, inst, kind, mutate):
        self.provider, self.inst, self.kind, self.mutate = provider, inst, kind, mutate

    def kind_of(self, method, path):
        if method != 'GET':
            return None
        if '/git/ref/' in path:
            return 'ref'
        if '/git/commits/' in path:
            return 'commit'
        if '/contents/' in path:
            return 'contents'
        if '/git/trees/' in path:
            return 'base_tree' if path.split('/git/trees/')[1].startswith(self.inst.base_tree) else 'head_tree'
        return None

    def request(self, method, path, body=None):
        result = self.provider.request(method, path, body)
        if self.kind_of(method, path) == self.kind:
            return self.mutate(copy.deepcopy(result), self.inst)
        return result


@pytest.mark.parametrize('label,kind,mutate', RECOVERY_MUTATIONS, ids=[m[0] for m in RECOVERY_MUTATIONS])
def test_corrupted_recovery_response_is_never_match(tmp_path, label, kind, mutate):
    inst = Installation(tmp_path)
    inst.base_tree = inst.contract['parameters']['base_tree']
    assert inst.dispatcher.dispatch(inst.handoff, inst.contract)['outcome'] == 'MATCH'
    provider = LocalGitProvider(inst.git_dir, demo.REPOSITORY)
    recovered, _ = inst.restart(Mutating(provider, inst, kind, mutate))
    with pytest.raises(Exception):
        recovered.recover(inst.handoff, inst.contract)
    assert provider.writes() == []
    # Control: the same recovery with honest responses confirms.
    honest, _ = inst.restart()
    assert honest.recover(inst.handoff, inst.contract)['outcome'] == 'MATCH'


DISPATCH_MUTATIONS = [
    ('head read reports another commit', 'ref', lambda r, i: {**r, 'object': {'sha': 'f' * 40}}),
    ('parent reports another tree', 'commit', lambda r, i: {**r, 'tree': {'sha': 'f' * 40}}),
]


@pytest.mark.parametrize('label,kind,mutate', DISPATCH_MUTATIONS, ids=[m[0] for m in DISPATCH_MUTATIONS])
def test_corrupted_preflight_response_blocks_before_any_write(tmp_path, label, kind, mutate):
    inst = Installation(tmp_path)
    inst.base_tree = inst.contract['parameters']['base_tree']
    inst.dispatcher.api = Mutating(inst.provider, inst, kind, mutate)
    with pytest.raises(Exception):
        inst.dispatcher.dispatch(inst.handoff, inst.contract)
    assert inst.provider.writes() == []
    assert inst.head() == inst.base


class LyingWrites:
    """A provider that acknowledges writes with object IDs other than what it stored."""
    def __init__(self, provider, inst, route):
        self.provider, self.inst, self.route = provider, inst, route

    def request(self, method, path, body=None):
        result = self.provider.request(method, path, body)
        if method == 'POST' and path.endswith(self.route):
            if self.route == '/git/trees':
                return {**result, 'sha': self.inst.base_tree}
            return {**result, 'sha': self.inst.base}
        return result


@pytest.mark.parametrize('route', ['/git/trees', '/git/commits'])
def test_provider_misreporting_written_objects_is_never_match(tmp_path, route):
    inst = Installation(tmp_path)
    inst.base_tree = inst.contract['parameters']['base_tree']
    inst.dispatcher.api = LyingWrites(inst.provider, inst, route)
    try:
        outcome = inst.dispatcher.dispatch(inst.handoff, inst.contract)['outcome']
    except Exception:  # noqa: BLE001
        outcome = 'REFUSED'
    assert outcome != 'MATCH'
    recovered, api = inst.restart()
    with pytest.raises(Exception):
        recovered.recover(inst.handoff, inst.contract)
    assert api.writes() == []


def test_matrix_counts():
    assert len(PROVIDER_POINTS) == 10 and len(LOCAL_POINTS) == 4 and len(RECOVERY_MUTATIONS) == 25
    json.dumps([m[0] for m in RECOVERY_MUTATIONS])

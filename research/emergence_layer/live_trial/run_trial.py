"""Gate-3 live dispatcher trial: real write, application-level response loss, and
registry rollback, against one dedicated GitHub repository.

    # Local self-test (no network, disposable git repo):
    python live_trial/run_trial.py --local --evidence /tmp/trial-evidence

    # Live (prerequisites below), prepared but intended to be witnessed:
    python live_trial/run_trial.py --config /etc/proofrail/trial.json \
        --evidence /srv/proofrail/trial-evidence

The dispatcher code under test (`enforcing_dispatcher.Dispatcher`) is unchanged.
Three scenarios:

  A. Approve exact bytes on the repository's current head; dispatch; confirm the
     commit by read-back.
  B. Approve again; dispatch through an in-process fault that forwards the real
     GitHub call, lets the branch update complete on the server, then discards
     the response and raises the unknown-outcome error (see app_fault.py). Then
     read-only recovery must confirm the exact approved tree with zero write
     calls, and reusing the permit must be refused.
  C. Back up the registry; dispatch (consuming a permit); restore the older
     registry while keeping the retained journal; a further dispatch must be
     blocked before any provider write.

Evidence is public only: the pinned source commit, repository and commit
identifiers, outcomes, provider call counts and verification results. No key,
token, request body or response body is exported.

Live prerequisites, none satisfied here: a dedicated throwaway repository; a
restricted GitHub App installation token in a service-owned 0600 file; confirmed
branch controls (no force-push, no deletion, restricted writers); and a witness.
This substitution does not cover transport-level interruption (see LIVE_TRIAL.md),
and running it does not by itself close gate 3.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE), str(ROOT / 'buyer_demo')]

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import run_demo as demo  # noqa: E402  (buyer_demo/run_demo: approval helpers)
from enforcing_dispatcher import Dispatcher, Journal, GitHubAPI  # noqa: E402
from execution_binding import ExecutionLedger  # noqa: E402
from app_fault import ResponseLostAfterCall, UNKNOWN  # noqa: E402


class CallLog:
    """Wrap any provider client, forward every call, record method and path only."""
    WRITES = ('POST', 'PATCH', 'PUT', 'DELETE')

    def __init__(self, client):
        self._client = client
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        return self._client.request(method, path, body)

    def write_count(self):
        return sum(1 for m, _ in self.calls if m in self.WRITES)

    def paths(self):
        return [m + ' ' + p for m, p in self.calls]


def head_and_tree(client, repository, branch):
    prefix = '/repos/' + repository
    head = client.request('GET', prefix + '/git/ref/heads/' + branch)['object']['sha']
    tree = client.request('GET', prefix + '/git/commits/' + head)['tree']['sha']
    return head, tree


def build(keys, repository, branch, path, parent_sha, base_tree, task_id, artifact):
    """Mint a trial approval bound to the repo's current head, reusing demo.approve's shape."""
    demo.REPOSITORY, demo.BRANCH, demo.PATH = repository, branch, path
    return demo.approve(keys, artifact=artifact, parent_sha=parent_sha,
                        base_tree=base_tree, task_id=task_id)


def make_dispatcher(workdir, name, keys, trust, client, repository, branch, path):
    root = workdir / name
    (root / 'retained').mkdir(parents=True)
    ledger = ExecutionLedger(root / 'registry.db', keys['consumer'], 'consumer-key')
    journal = Journal.initialize(root / 'retained' / 'journal.db')
    return Dispatcher(ledger, journal, client, repository=repository, branch=branch,
                      path=path, trust=trust), ledger, journal


def run(workdir, evidence, repository, branch, path, make_client, source_commit, mode):
    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    artifact = ('# Gate-3 trial artifact\n\nApproved exact bytes for one dispatcher '
                'execution against ' + repository + '.\n')
    scenarios = []

    def record(name, **fields):
        scenarios.append({'scenario': name, **fields})
        print('[%s] %s' % (name, fields.get('outcome')))

    # Scenario A: real write and read-back.
    client_a = CallLog(make_client())
    head, tree = head_and_tree(client_a, repository, branch)
    handoff, contract, trust = build(keys, repository, branch, path, head, tree, 'gate3-write', artifact)
    disp_a, _, _ = make_dispatcher(workdir, 'a', keys, trust, client_a, repository, branch, path)
    result_a = disp_a.dispatch(handoff, contract)
    record('A real write and readback', outcome=result_a['outcome'], parent_sha=head,
           commit_sha=result_a['commit_sha'], file_sha256=result_a['file_sha256'],
           write_calls=client_a.write_count())

    # Scenario B: application-level response loss, then read-only recovery.
    base_client_b = make_client()
    fault = ResponseLostAfterCall(base_client_b)
    client_b = CallLog(fault)
    head_b, tree_b = head_and_tree(client_b, repository, branch)
    handoff_b, contract_b, trust_b = build(keys, repository, branch, path, head_b, tree_b,
                                           'gate3-lost', artifact)
    disp_b, ledger_b, journal_b = make_dispatcher(workdir, 'b', keys, trust_b, client_b,
                                                  repository, branch, path)
    lost_error = None
    try:
        disp_b.dispatch(handoff_b, contract_b)
    except RuntimeError as exc:
        lost_error = str(exc)
    writes_during_loss = client_b.write_count()
    # Operator restart: reopen the journal, swap in a clean counting client (no fault).
    disp_b.journal = Journal(journal_b.path)
    recovery_client = CallLog(make_client())
    disp_b.api = recovery_client
    result_b = disp_b.recover(handoff_b, contract_b)
    reuse_refused = None
    try:
        disp_b.dispatch(handoff_b, contract_b)
    except Exception as exc:  # noqa: BLE001 - the refusal reason is the evidence
        reuse_refused = type(exc).__name__ + ': ' + str(exc)
    record('B lost response then read-only recovery',
           dispatch_error=lost_error, lost_response_was_unknown=(lost_error == UNKNOWN),
           write_calls_including_lost_write=writes_during_loss,
           recovery_outcome=result_b['outcome'], recovery_commit_sha=result_b['commit_sha'],
           recovery_write_calls=recovery_client.write_count(),
           recovery_calls=recovery_client.paths(), reuse_refused=reuse_refused,
           outcome='MATCH' if result_b['outcome'] == 'MATCH' and recovery_client.write_count() == 0
                   and reuse_refused else 'UNEXPECTED')

    # Scenario C: registry rollback with retained journal blocks admission.
    client_c = CallLog(make_client())
    head_c, tree_c = head_and_tree(client_c, repository, branch)
    handoff_c, contract_c, trust_c = build(keys, repository, branch, path, head_c, tree_c,
                                           'gate3-rollback', artifact)
    disp_c, ledger_c, journal_c = make_dispatcher(workdir, 'c', keys, trust_c, client_c,
                                                  repository, branch, path)
    backup = workdir / 'c' / 'registry-before.db'
    import sqlite3
    with sqlite3.connect(ledger_c.path) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)  # registry state that predates the execution below
    result_c = disp_c.dispatch(handoff_c, contract_c)
    writes_before_rollback = client_c.write_count()
    with sqlite3.connect(backup) as src, sqlite3.connect(ledger_c.path) as dst:
        src.backup(dst)  # restore older registry; retained journal untouched
    # A fresh dispatcher reopens the restored (older) registry and the retained
    # journal, as a restarted service would. The journal still records the
    # execution just completed; the older registry has no such record, so the
    # recovery-state check blocks before any provider write. The same approval is
    # re-submitted, so this also shows an already-used permit cannot be revived.
    rollback_client = CallLog(make_client())
    disp_c2 = Dispatcher(ExecutionLedger(ledger_c.path, keys['consumer'], 'consumer-key'),
                         Journal(journal_c.path), rollback_client,
                         repository=repository, branch=branch, path=path, trust=trust_c)
    blocked = None
    try:
        disp_c2.dispatch(handoff_c, contract_c)
    except Exception as exc:  # noqa: BLE001
        blocked = type(exc).__name__ + ': ' + str(exc)
    record('C registry rollback blocks admission',
           first_dispatch_outcome=result_c['outcome'], first_commit_sha=result_c['commit_sha'],
           write_calls_before_rollback=writes_before_rollback,
           admission_blocked=blocked, provider_write_calls_after_rollback=rollback_client.write_count(),
           outcome='BLOCKED' if blocked and rollback_client.write_count() == 0 else 'UNEXPECTED')

    export(evidence, repository, branch, path, source_commit, mode, scenarios)
    return scenarios


def export(evidence, repository, branch, path, source_commit, mode, scenarios):
    evidence.mkdir(parents=True, exist_ok=False)
    summary = {
        'kind': 'proofrail.gate3-live-trial-evidence.v1',
        'mode': mode,
        'claim': ('Against ' + repository + ', the unchanged dispatcher wrote approved bytes once, '
                  'reported a lost response as unknown and recovered with reads only, and blocked '
                  'admission after a registry rollback with the journal retained.'),
        'source_commit': source_commit,
        'repository': repository, 'branch': branch, 'path': path,
        'fault_model': 'application-level response loss after a completed GitHub call',
        'not_covered': ['transport-level interruption during a call (reset, timeout, truncated body)',
                        'independent review', 'key custody / approver identity (keys generated per run)',
                        'branch-control enforcement (must be configured and confirmed out of band)'],
        'environment': {'python': platform.python_version(), 'platform': platform.platform()},
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'scenarios': scenarios,
    }
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    sums = {str(p.relative_to(evidence)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(evidence.rglob('*')) if p.is_file()}
    (evidence / 'SHA256SUMS').write_text(''.join(f'{d}  {n}\n' for n, d in sums.items()))
    print('evidence:', evidence)


def source_commit_of(repo_dir):
    try:
        out = subprocess.run(['git', '-C', str(repo_dir), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(repo_dir), 'status', '--porcelain'],
                              capture_output=True, text=True).stdout.strip()
        return out + ('-dirty' if dirty else '')
    except Exception:  # noqa: BLE001
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--evidence', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--local', action='store_true', help='disposable local git repo, no network')
    group.add_argument('--config', type=Path, help='service config (0600) for a live dedicated repo')
    parser.add_argument('--workdir', type=Path, help='defaults to a temp dir; holds keys and databases')
    args = parser.parse_args()

    import tempfile
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix='gate3-'))
    workdir.mkdir(parents=True, exist_ok=True)
    source_commit = source_commit_of(ROOT)

    if args.local:
        from local_git_provider import LocalGitProvider, create_repository
        repository, branch, path = 'demo-team/gate3-local', 'trial/emergence-gate3', 'evidence/report.json'
        git_dir = workdir / 'repo.git'
        create_repository(git_dir, branch, {'README.md': 'Gate-3 local self-test.\n'})
        make_client = lambda: LocalGitProvider(git_dir, repository)  # noqa: E731
        run(workdir, args.evidence, repository, branch, path, make_client, source_commit, 'local-selftest')
    else:
        from dispatcher_cli import private_file
        config = json.loads(private_file(args.config))
        repository, branch, path = config['repository'], config['branch'], config['path']
        token_file = config['github_token_file']
        make_client = lambda: GitHubAPI(token_file)  # noqa: E731 - reads the 0600 token each call-set
        run(workdir, args.evidence, repository, branch, path, make_client, source_commit, 'live')


if __name__ == '__main__':
    main()

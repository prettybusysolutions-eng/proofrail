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
import base64
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


class Service:
    """One dispatcher installation: a registry and a separately retained journal that
    persist across every scenario, as on a deployed service. The pilot pins one
    authority per configuration, so each approval gets its own Dispatcher over the
    same two stores (the operator re-pinning the config between approvals)."""

    def __init__(self, workdir, keys, repository, branch, path):
        root = workdir / 'service'
        (root / 'retained').mkdir(parents=True)
        self.keys, self.repository, self.branch, self.path = keys, repository, branch, path
        self.registry_path = root / 'registry.db'
        self.journal_path = root / 'retained' / 'journal.db'
        Journal.initialize(self.journal_path)

    def ledger(self):
        return ExecutionLedger(self.registry_path, self.keys['consumer'], 'consumer-key')

    def dispatcher(self, trust, client):
        """Reopen both stores, as a restarted service process would."""
        return Dispatcher(self.ledger(), Journal(self.journal_path), client,
                          repository=self.repository, branch=self.branch, path=self.path, trust=trust)


def run(workdir, evidence, repository, branch, path, make_client, source, mode):
    import sqlite3
    workdir, evidence = Path(workdir).resolve(), Path(evidence).resolve()
    if workdir.is_relative_to(evidence) or evidence.is_relative_to(workdir):
        raise ValueError('work_and_evidence_must_be_separate')
    # Reserve and test the export destination before consuming authority or
    # contacting a provider. Existing evidence must never be overwritten.
    evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    (evidence / 'INCOMPLETE').write_text(
        'Trial incomplete. Preserve work stores and inspect provider history before retrying.\n')
    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    artifact = ('# Gate-3 trial artifact\n\nApproved exact bytes for one dispatcher '
                'execution against ' + repository + '.\n')
    service = Service(workdir, keys, repository, branch, path)
    scenarios = []

    def record(name, **fields):
        scenarios.append({'scenario': name, **fields})
        print('[%s] %s' % (name, fields.get('outcome')))

    # Scenario A: real write and read-back.
    client_a = CallLog(make_client())
    start_head, tree = head_and_tree(client_a, repository, branch)
    handoff, contract, trust = build(keys, repository, branch, path, start_head, tree, 'gate3-write', artifact)
    result_a = service.dispatcher(trust, client_a).dispatch(handoff, contract)
    record('A real write and readback', outcome=result_a['outcome'], parent_sha=start_head,
           commit_sha=result_a['commit_sha'], file_sha256=result_a['file_sha256'],
           execution_id=result_a['execution_id'], write_calls=client_a.write_count())

    # Scenario B: application-level response loss, then read-only recovery.
    fault = ResponseLostAfterCall(make_client())
    client_b = CallLog(fault)
    head_b, tree_b = head_and_tree(client_b, repository, branch)
    handoff_b, contract_b, trust_b = build(keys, repository, branch, path, head_b, tree_b,
                                           'gate3-lost', artifact)
    lost_error = None
    try:
        service.dispatcher(trust_b, client_b).dispatch(handoff_b, contract_b)
    except RuntimeError as exc:
        lost_error = str(exc)
    writes_during_loss = client_b.write_count()
    discarded = sum(event.get('response_discarded') is True
                    for event in getattr(fault, 'events', []))
    # Operator restart: fresh process view of both stores, clean client (no fault).
    recovery_client = CallLog(make_client())
    recovering = service.dispatcher(trust_b, recovery_client)
    result_b = recovering.recover(handoff_b, contract_b)
    reuse_refused = None
    try:
        recovering.dispatch(handoff_b, contract_b)
    except Exception as exc:  # noqa: BLE001 - the refusal reason is the evidence
        reuse_refused = type(exc).__name__ + ': ' + str(exc)
    record('B lost response then read-only recovery',
           dispatch_error=lost_error, lost_response_was_unknown=(lost_error == UNKNOWN),
           discarded_responses=discarded, parent_sha=head_b,
           write_calls_including_lost_write=writes_during_loss,
           recovery_outcome=result_b['outcome'], recovery_commit_sha=result_b['commit_sha'],
           file_sha256=result_b['file_sha256'], execution_id=result_b['execution_id'],
           recovery_write_calls=recovery_client.write_count(),
           recovery_calls=recovery_client.paths(), reuse_refused=reuse_refused,
           outcome='MATCH' if lost_error == UNKNOWN and discarded == 1
                   and writes_during_loss == 3 and result_b['outcome'] == 'MATCH'
                   and recovery_client.write_count() == 0
                   and reuse_refused == 'ValueError: retained_authority_already_reserved'
                   else 'UNEXPECTED')

    # Scenario C: restore an OLDER, non-empty registry (it holds A and B) while the
    # journal is retained; the next admission must be blocked before any provider call.
    client_c = CallLog(make_client())
    head_c, tree_c = head_and_tree(client_c, repository, branch)
    handoff_c, contract_c, trust_c = build(keys, repository, branch, path, head_c, tree_c,
                                           'gate3-rollback', artifact)
    backup = workdir / 'registry-before-c.db'
    with sqlite3.connect(service.registry_path) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    result_c = service.dispatcher(trust_c, client_c).dispatch(handoff_c, contract_c)
    writes_before_rollback = client_c.write_count()
    with sqlite3.connect(backup) as src, sqlite3.connect(service.registry_path) as dst:
        src.backup(dst)  # registry rolled back; retained journal untouched
    restored = service.ledger()
    prior_present = []
    for execution_id in (result_a['execution_id'], result_b['execution_id'], result_c['execution_id']):
        try:
            restored.get(execution_id)
            prior_present.append(True)
        except Exception:  # noqa: BLE001
            prior_present.append(False)
    rollback_client = CallLog(make_client())
    blocked = None
    try:
        service.dispatcher(trust_c, rollback_client).dispatch(handoff_c, contract_c)
    except Exception as exc:  # noqa: BLE001
        blocked = type(exc).__name__ + ': ' + str(exc)
    record('C registry rollback blocks admission',
           first_dispatch_outcome=result_c['outcome'], first_commit_sha=result_c['commit_sha'],
           parent_sha=head_c, file_sha256=result_c['file_sha256'],
           execution_id=result_c['execution_id'],
           write_calls_before_rollback=writes_before_rollback,
           restored_registry_holds=dict(zip(('A', 'B', 'C'), prior_present)),
           admission_blocked=blocked, provider_calls_after_rollback=len(rollback_client.calls),
           outcome='BLOCKED' if blocked == 'BindingError: execution_not_found'
                   and result_c['outcome'] == 'MATCH' and writes_before_rollback == 3
                   and prior_present == [True, True, False]
                   and not rollback_client.calls else 'UNEXPECTED')

    provider = verify_provider_chain(CallLog(make_client()), repository, branch, path,
                                     start_head, scenarios)
    print('[provider end state] %s%s' % (provider['result'],
          ' (' + provider['reason'] + ')' if provider.get('reason') else ''))
    export(evidence, repository, branch, path, source, mode, scenarios, provider)
    return scenarios, provider


def verify_provider_chain(client, repository, branch, path, start_head, scenarios):
    """Read the branch back from the provider (GET only) and require exactly the
    trial's commits: one chain from the starting head, A then B then C, each adding
    only the approved file, with the bytes recorded during the run. This checks the
    run's own observations against the provider instead of trusting them."""
    from github_artifact import verify_tree_change
    prefix = '/repos/' + repository
    expected = [s.get('commit_sha') or s.get('recovery_commit_sha') or s.get('first_commit_sha')
                for s in scenarios]
    digests = [s.get('file_sha256') for s in scenarios]
    chain = []
    try:
        cur = client.request('GET', prefix + '/git/ref/heads/' + branch)['object']['sha']
        while cur != start_head:
            if len(chain) > len(expected):
                raise ValueError('more_commits_than_approved_in_trial_window')
            commit = client.request('GET', prefix + '/git/commits/' + cur)
            parents = [p['sha'] for p in commit['parents']]
            if len(parents) != 1:
                raise ValueError('non_linear_history_in_trial_window')
            chain.append({'commit': cur, 'parent': parents[0], 'tree': commit['tree']['sha']})
            cur = parents[0]
        chain.reverse()
        if [c['commit'] for c in chain] != expected:
            raise ValueError('provider_history_differs_from_trial_record')
        prev_tree = client.request('GET', prefix + '/git/commits/' + start_head)['tree']['sha']
        for link, digest in zip(chain, digests):
            served = client.request('GET', prefix + '/contents/' + path + '?ref=' + link['commit'])
            content = base64.b64decode(''.join(served['content'].split())).decode('utf-8')
            link['file_sha256'] = hashlib.sha256(content.encode()).hexdigest()
            if link['file_sha256'] != digest:
                raise ValueError('provider_bytes_differ_from_trial_record')
            verify_tree_change(client.request('GET', prefix + '/git/trees/' + prev_tree + '?recursive=1'),
                               client.request('GET', prefix + '/git/trees/' + link['tree'] + '?recursive=1'),
                               path, content)
            prev_tree = link['tree']
        result, reason = 'PASS', None
    except Exception as exc:  # noqa: BLE001 - any failure to establish the end state is a FAIL
        result, reason = 'FAIL', type(exc).__name__ + ': ' + str(exc)
    if client.write_count():
        result, reason = 'FAIL', 'end_state_check_issued_writes'
    return {'result': result, 'reason': reason, 'start_head': start_head, 'chain': chain,
            'read_calls': len(client.calls), 'write_calls': client.write_count()}


def export(evidence, repository, branch, path, source, mode, scenarios, provider):
    summary = {
        'kind': 'proofrail.gate3-live-trial-evidence.v1',
        'mode': mode,
        'verdict': 'PASS' if trial_passed(scenarios, provider) else 'FAIL',
        'claim': 'Author-run scenario observations; consult verdict and individual results.',
        'source_commit': source['commit'],
        'source_tree': source,
        'repository': repository, 'branch': branch, 'path': path,
        'fault_model': 'application-level response loss after a completed GitHub call',
        'not_covered': ['transport-level interruption during a call (reset, timeout, truncated body)',
                        'independent review', 'key custody / approver identity (keys generated per run)',
                        'branch-control enforcement (must be configured and confirmed out of band)'],
        'environment': {'python': platform.python_version(), 'platform': platform.platform()},
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'scenarios': scenarios,
        'provider_end_state': provider,
    }
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    sums = {str(p.relative_to(evidence)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(evidence.rglob('*')) if p.is_file() and p.name != 'INCOMPLETE'}
    (evidence / 'SHA256SUMS').write_text(''.join(f'{d}  {n}\n' for n, d in sums.items()))
    (evidence / 'INCOMPLETE').unlink()
    print('evidence:', evidence)


def trial_passed(scenarios, provider):
    return (len(scenarios) == 3
            and [s['outcome'] for s in scenarios] == ['MATCH', 'MATCH', 'BLOCKED']
            and scenarios[0]['write_calls'] == 3
            and scenarios[0]['parent_sha'] != scenarios[0]['commit_sha']
            and provider['result'] == 'PASS' and len(provider['chain']) == 3)


def source_state(repo_dir):
    """The checkout this run executes: commit, tracked changes and untracked paths.

    Recorded separately rather than as a '-dirty' suffix on the SHA. Untracked
    files matter: the runner puts its own directories first on sys.path, so an
    untracked module there could shadow an import. Ignored files (build output,
    caches) are not listed. Keep virtual environments outside the checkout.
    """
    def git(*args):
        return subprocess.run(['git', '-C', str(repo_dir), *args], capture_output=True,
                              text=True, check=True).stdout
    try:
        commit = git('rev-parse', 'HEAD').strip()
        tracked, untracked = [], []
        for entry in filter(None, git('status', '--porcelain=v1', '-z').split('\0')):
            (untracked if entry.startswith('??') else tracked).append(entry[3:])
    except Exception:  # noqa: BLE001
        return {'commit': None, 'tracked_changes': None, 'untracked': None, 'clean': False}
    return {'commit': commit, 'tracked_changes': tracked[:50], 'untracked': untracked[:50],
            'clean': not tracked and not untracked}


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
    source = source_state(ROOT)

    if args.local:
        from local_git_provider import LocalGitProvider, create_repository
        repository, branch, path = 'demo-team/gate3-local', 'trial/emergence-gate3', 'evidence/report.json'
        git_dir = workdir / 'repo.git'
        create_repository(git_dir, branch, {'README.md': 'Gate-3 local self-test.\n'})
        make_client = lambda: LocalGitProvider(git_dir, repository)  # noqa: E731
        scenarios, provider = run(workdir, args.evidence, repository, branch, path, make_client,
                                  source, 'local-selftest')
    else:
        if not source['clean']:
            # Refuse before any GitHub call, so the operator can fix the checkout and
            # rerun within the token's lifetime instead of producing unpinned evidence.
            print('refusing live run: checkout is not a clean pinned commit '
                  '(tracked changes: %s; untracked: %s). Keep the virtual environment '
                  'outside the checkout.' % (source['tracked_changes'],
                                             source['untracked']), file=sys.stderr)
            return 2
        from dispatcher_cli import private_file
        config = json.loads(private_file(args.config))
        repository, branch, path = config['repository'], config['branch'], config['path']
        token_file = config['github_token_file']
        make_client = lambda: GitHubAPI(token_file)  # noqa: E731 - reads the 0600 token each call-set
        scenarios, provider = run(workdir, args.evidence, repository, branch, path, make_client,
                                  source, 'live')
    return 0 if trial_passed(scenarios, provider) else 1


if __name__ == '__main__':
    sys.exit(main())

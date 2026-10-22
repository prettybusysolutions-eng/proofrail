"""Buyer demonstration: approve one exact artifact, allow that write, reject changed
content, and export evidence another person can verify offline.

Runs the unmodified pilot `Dispatcher` against a disposable local git repository
(see local_git_provider.py). No GitHub credentials, network access or model calls.
Keys are generated per run; private keys stay in the work directory and are
never exported.

    python buyer_demo/run_demo.py --workdir /tmp/pr-demo --evidence /tmp/pr-evidence
    python buyer_demo/verify_evidence.py /tmp/pr-evidence
"""
import argparse
import copy
import hashlib
import json
import platform
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from proofrail.envelope import mint_action_authority_envelope  # noqa: E402
from acceptance_bridge import Trust, full_digest  # noqa: E402
from smatp import encode_public, make_envelope  # noqa: E402
from execution_binding import ExecutionLedger  # noqa: E402
from enforcing_dispatcher import Dispatcher, Journal  # noqa: E402
from local_git_provider import (GIT_ENV, LocalGitProvider, ResponseLostAfterRefUpdate,  # noqa: E402
                                commit_file, create_repository, git)

REPOSITORY = 'demo-team/agent-reports'
BRANCH = 'trial/emergence-weekly-report'
PATH = 'evidence/weekly-report.json'
APPROVED_ARTIFACT = (
    '# Weekly service report (week 42)\n\n'
    '- Availability: 99.95% against a 99.9% objective.\n'
    '- Incidents: one, resolved in 38 minutes; follow-up ticket OPS-112.\n'
    '- Next week: rotate the on-call schedule; no planned maintenance.\n')
CHANGED_ARTIFACT = APPROVED_ARTIFACT.replace('one, resolved in 38 minutes', 'none')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def approve(keys, *, artifact, parent_sha, base_tree, task_id):
    """What the human approver signs: these exact bytes, this repository, branch,
    path and parent commit, once, within one hour."""
    params = dict(repository=REPOSITORY, branch=BRANCH, path=PATH,
                  parent_sha=parent_sha, base_tree=base_tree)
    task = {'artifact': artifact}
    roots = {name: full_digest({'demo_root': name, 'repository': REPOSITORY})
             for name in ('identity', 'evidence', 'policy', 'state')}
    approval = full_digest({'operator_authorization': 'Publish the reviewed weekly report', **params})
    contract = dict(kind='emergence.acceptance.v1', tenant='demo-team', task_id=task_id,
                    sender='report-agent', recipient='dispatcher', capability='publish-artifact',
                    task_digest=full_digest(task), action_type='github_artifact_commit',
                    target='github:' + REPOSITORY + ':' + BRANCH + ':' + PATH, parameters=params,
                    expected_sha256=hashlib.sha256(artifact.encode()).hexdigest(),
                    observer='dispatcher-readback', observer_key_id='observer-key',
                    max_observation_age_seconds=3600)
    now = int(time.time())
    authority = mint_action_authority_envelope(
        roots=roots, approval_digest=approval, action_type=contract['action_type'],
        target=contract['target'], parameters=params, subject_principal_id='dispatcher',
        subject_role='executor', issuer_principal_id='report-approver', issuer_role='verifier',
        adapter_contract={'name': 'github-git-data', 'version': 'v1', 'idempotency_required': True},
        observation_contract={'name': 'emergence.acceptance', 'version': 'v1',
                              'minimum_confirmations': 1,
                              'success_predicate_digest': full_digest(contract)},
        nonce=secrets.token_hex(32), expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        private_key=keys['approver'], key_id='approver-key',
        now=datetime.fromtimestamp(now, timezone.utc))
    handoff = make_envelope('report-agent', 'dispatcher', 'publish-artifact',
                            {'task': task, 'contract': contract, 'authority': authority},
                            keys['agent'], now=now, ttl=3600)
    trust = Trust(encode_public(keys['agent'].public_key()), keys['approver'].public_key(),
                  'approver-key', full_digest(authority), authority['issuer'],
                  keys['observer'].public_key(), 'observer-key', roots, approval)
    return handoff, contract, trust


def service(workdir, name, keys, trust, git_dir):
    """One pinned dispatcher installation: own registry, separately retained journal."""
    root = workdir / name
    (root / 'retained').mkdir(parents=True)
    ledger = ExecutionLedger(root / 'registry.db', keys['consumer'], 'consumer-key')
    journal = Journal.initialize(root / 'retained' / 'journal.db')
    provider = LocalGitProvider(git_dir, REPOSITORY)
    dispatcher = Dispatcher(ledger, journal, provider, repository=REPOSITORY, branch=BRANCH,
                            path=PATH, trust=trust)
    return dispatcher, provider


def branch_head(git_dir):
    return git(git_dir, 'rev-parse', 'refs/heads/' + BRANCH).decode().strip()


def attempt(label, dispatcher, provider, git_dir, fn):
    """Run one step; record the outcome, refusal reason and provider write calls."""
    before_calls, before_head = len(provider.calls), branch_head(git_dir)
    started = time.monotonic()
    try:
        result, refusal = fn(), None
    except Exception as exc:  # the reason string is the evidence
        result, refusal = None, (type(exc).__name__ + ': ' + str(exc))
    if refusal is None:
        outcome = result.get('outcome')
    elif refusal.endswith('provider_outcome_unknown'):
        outcome = 'OUTCOME_UNKNOWN'  # the write may have happened; never retried
    else:
        outcome = 'REFUSED'
    step = {
        'step': label,
        'outcome': outcome,
        'refusal': refusal,
        'provider_calls': [m + ' ' + p for m, p in provider.calls[before_calls:]],
        'provider_write_calls': len(provider.writes(before_calls)),
        'branch_updates': sum(m == 'PATCH' for m, _ in provider.calls[before_calls:]),
        'branch_head_before': before_head,
        'branch_head_after': branch_head(git_dir),
        'elapsed_seconds': round(time.monotonic() - started, 3),
    }
    if result:
        step['result'] = result
    status = step['outcome'] + (' (' + refusal + ')' if refusal else '')
    print(f'[{label}] {status}; write calls: {step["provider_write_calls"]}, '
          f'branch updates: {step["branch_updates"]}')
    return step


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workdir', type=Path, required=True, help='new directory; holds private keys')
    parser.add_argument('--evidence', type=Path, required=True, help='new directory; public evidence only')
    args = parser.parse_args()
    run_started = time.monotonic()
    workdir, evidence = args.workdir.resolve(), args.evidence.resolve()
    workdir.mkdir(mode=0o700, parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    if evidence == workdir or workdir in evidence.parents or evidence in workdir.parents:
        raise SystemExit('workdir and evidence must be separate directories')

    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    git_dir = workdir / 'agent-reports.git'
    base_sha, base_tree = create_repository(git_dir, BRANCH, {
        'README.md': 'Reports published by the reporting agent after human approval.\n'})
    steps = []

    # 1. Approve one exact artifact.
    handoff, contract, trust = approve(keys, artifact=APPROVED_ARTIFACT, parent_sha=base_sha,
                                       base_tree=base_tree, task_id='weekly-report-42')
    dispatcher, provider = service(workdir, 'service', keys, trust, git_dir)
    print('[1 approve] artifact sha256', contract['expected_sha256'], '->',
          contract['target'], 'at parent', base_sha[:12])

    # 2. Changed content is refused before any write (two forms).
    tampered = copy.deepcopy(handoff)
    tampered['payload']['task']['artifact'] = CHANGED_ARTIFACT
    steps.append(attempt('2a changed after signing', dispatcher, provider, git_dir,
                         lambda: dispatcher.dispatch(tampered, tampered['payload']['contract'])))
    # The agent re-signs changed content with its own valid key and a matching
    # contract. The approver's signature still names the original bytes.
    resigned_contract = copy.deepcopy(contract)
    resigned_contract['task_digest'] = full_digest({'artifact': CHANGED_ARTIFACT})
    resigned_contract['expected_sha256'] = hashlib.sha256(CHANGED_ARTIFACT.encode()).hexdigest()
    resigned = make_envelope('report-agent', 'dispatcher', 'publish-artifact',
                             {'task': {'artifact': CHANGED_ARTIFACT}, 'contract': resigned_contract,
                              'authority': handoff['payload']['authority']}, keys['agent'], ttl=3600)
    steps.append(attempt('2b agent re-signed changed content', dispatcher, provider, git_dir,
                         lambda: dispatcher.dispatch(resigned, resigned_contract)))

    # 3. The approved bytes are written once and confirmed by reading them back.
    steps.append(attempt('3 approved write', dispatcher, provider, git_dir,
                         lambda: dispatcher.dispatch(handoff, contract)))
    seconds_to_first_write = round(time.monotonic() - run_started, 3)
    confirmed_commit = steps[-1]['result']['commit_sha']
    written = git(git_dir, 'cat-file', 'blob', confirmed_commit + ':' + PATH)
    steps[-1]['independent_git_read_sha256'] = hashlib.sha256(written).hexdigest()

    # 4. The same approval cannot be used again.
    steps.append(attempt('4 replay of the same approval', dispatcher, provider, git_dir,
                         lambda: dispatcher.dispatch(handoff, contract)))

    # 5. Someone edits the published file afterwards; read-only verification no
    #    longer confirms it and makes no write.
    edited = json.loads(written)
    edited['artifact'] = CHANGED_ARTIFACT
    commit_file(git_dir, BRANCH, PATH, json.dumps(edited, indent=2, sort_keys=True) + '\n',
                'Manual edit outside ProofRail')
    steps.append(attempt('5 verify after an out-of-band edit', dispatcher, provider, git_dir,
                         lambda: dispatcher.recover(handoff, contract)))

    # 6. Recovery after a lost response, on a second disposable repository.
    git_dir_2 = workdir / 'agent-reports-recovery.git'
    base_sha_2, base_tree_2 = create_repository(git_dir_2, BRANCH, {
        'README.md': 'Recovery exercise repository.\n'})
    handoff_2, contract_2, trust_2 = approve(keys, artifact=APPROVED_ARTIFACT, parent_sha=base_sha_2,
                                             base_tree=base_tree_2, task_id='weekly-report-42-recovery')
    dispatcher_2, provider_2 = service(workdir, 'service-recovery', keys, trust_2, git_dir_2)
    dispatcher_2.api = ResponseLostAfterRefUpdate(provider_2)
    steps.append(attempt('6a write whose response is lost', dispatcher_2, provider_2, git_dir_2,
                         lambda: dispatcher_2.dispatch(handoff_2, contract_2)))
    dispatcher_2.api = provider_2
    steps.append(attempt('6b read-only recovery', dispatcher_2, provider_2, git_dir_2,
                         lambda: dispatcher_2.recover(handoff_2, contract_2)))
    steps.append(attempt('6c retry of the same approval', dispatcher_2, provider_2, git_dir_2,
                         lambda: dispatcher_2.dispatch(handoff_2, contract_2)))

    # Export: public material only. Private keys and databases stay in workdir.
    consumption, _ = dispatcher.ledger.get(steps[2]['result']['execution_id'])
    consumption_2, _ = dispatcher_2.ledger.get(steps[6]['result']['execution_id'])
    for name, h, c, cons, d, g in (('primary', handoff, contract, consumption, dispatcher, git_dir),
                                   ('recovery', handoff_2, contract_2, consumption_2, dispatcher_2, git_dir_2)):
        authority = h['payload']['authority']
        write_json(evidence / name / 'approval' / 'handoff.json', h)
        write_json(evidence / name / 'approval' / 'contract.json', c)
        write_json(evidence / name / 'execution' / 'consumption.json', cons)
        write_json(evidence / name / 'execution' / 'journal-row.json', d.journal.get(authority['nonce']))
        bundle = evidence / name / 'repository.bundle'
        git(g, 'bundle', 'create', str(bundle), '--all')
    write_json(evidence / 'approved-artifact.json', {'text': APPROVED_ARTIFACT,
               'sha256': hashlib.sha256(APPROVED_ARTIFACT.encode()).hexdigest()})
    pins = {name: encode_public(k.public_key()) for name, k in keys.items()}
    write_json(evidence / 'public-keys.json', pins)
    revision = subprocess.run(['git', '-C', str(HERE), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, env=GIT_ENV).stdout.strip() or None
    dirty = subprocess.run(['git', '-C', str(HERE), 'status', '--porcelain', '--', '..', '../../../proofrail'],
                           capture_output=True, text=True, env=GIT_ENV).stdout.strip() if revision else None
    write_json(evidence / 'summary.json', {
        'kind': 'proofrail.buyer-demo-evidence.v1',
        'claim': ('The pilot dispatcher wrote only the approved bytes, once, and refused changed '
                  'content and reuse; recovery after a lost response made no additional writes.'),
        'limits': ['Local disposable git repository, not GitHub; GitHub transport, token scope '
                   'and branch protection are not exercised.',
                   'Keys are generated by this run; the verifier checks internal consistency, '
                   'not who controls the keys.',
                   'Timings are from this machine and say nothing about production performance.',
                   'Not an independent review.'],
        'source_revision': revision, 'source_tree_modified': bool(dirty) if revision else None,
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                        'git': git(git_dir, 'version').decode().strip()},
        'repository': REPOSITORY, 'branch': BRANCH, 'path': PATH,
        'primary_base_commit': base_sha, 'recovery_base_commit': base_sha_2,
        'seconds_to_first_confirmed_write': seconds_to_first_write,
        'steps': steps,
    })
    sums = {str(p.relative_to(evidence)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(evidence.rglob('*')) if p.is_file()}
    (evidence / 'SHA256SUMS').write_text(''.join(f'{d}  {n}\n' for n, d in sums.items()))
    print('evidence:', evidence, '| seconds to first confirmed write:', seconds_to_first_write)


if __name__ == '__main__':
    main()

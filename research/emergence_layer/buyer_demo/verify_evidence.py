"""Verify an exported buyer-demo evidence directory offline, without the run's databases.

    python buyer_demo/verify_evidence.py /path/to/evidence

Checks checksums, signatures, the approval-to-consumption-to-journal chain, and
the actual git objects in the exported repository bundles. Exits 1 on any failure.

What PASS means: the evidence is internally consistent and the repository holds
exactly the approved bytes from one dispatcher commit. It does not establish who
controlled the keys (the run generated them), and it says nothing about GitHub.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import base64  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402
from proofrail.crypto import verify_signature  # noqa: E402
from acceptance_bridge import Trust, full_digest, verify_handoff  # noqa: E402
from local_git_provider import GIT_ENV  # noqa: E402

CHECKS = []


def check(name, condition, detail=''):
    CHECKS.append({'check': name, 'result': 'PASS' if condition else 'FAIL',
                   'detail': '' if condition else detail})
    return condition


def load(path):
    return json.loads(path.read_text())


def git(git_dir, *args):
    return subprocess.run(['git', '--git-dir', str(git_dir), *args], capture_output=True,
                          env=GIT_ENV, check=True).stdout


def verify_checksums(root):
    listed = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        listed[name] = digest
    present = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'SHA256SUMS'}
    check('no unlisted or missing files', present == set(listed),
          'unlisted=%s missing=%s' % (sorted(present - set(listed)), sorted(set(listed) - present)))
    bad = [n for n, d in listed.items() if (root / n).is_file() and
           hashlib.sha256((root / n).read_bytes()).hexdigest() != d]
    check('every file matches SHA256SUMS', not bad, ', '.join(bad))


def verify_run(root, name, keys, summary, steps, scratch):
    folder = root / name
    handoff = load(folder / 'approval' / 'handoff.json')
    contract = load(folder / 'approval' / 'contract.json')
    consumption = load(folder / 'execution' / 'consumption.json')
    journal = load(folder / 'execution' / 'journal-row.json')
    authority = handoff['payload']['authority']
    approved = load(root / 'approved-artifact.json')
    check(f'{name}: contract is the one inside the signed handoff', handoff['payload']['contract'] == contract)
    trust = Trust(keys['agent_b64'], keys['approver'], 'approver-key', full_digest(authority),
                  authority['issuer'], keys['observer'], 'observer-key', authority['roots'],
                  authority['approval_digest'])
    try:
        verify_signature(consumption, keys['consumer'])
        check(f'{name}: consumption record signed by the dispatcher key', True)
    except Exception as exc:
        check(f'{name}: consumption record signed by the dispatcher key', False, str(exc))
        return
    try:
        binding = verify_handoff(handoff, contract, trust, now=consumption['consumed_at'])
    except Exception as exc:
        check(f'{name}: approval and agent signatures valid at consumption time', False, str(exc))
        return
    check(f'{name}: approval and agent signatures valid at consumption time', True)
    check(f'{name}: consumption names this approval, handoff and contract',
          all(consumption[f] == binding[f] for f in ('handoff_digest', 'authority_digest', 'contract_digest')))
    request = json.loads(journal['request'])
    check(f'{name}: retained journal row matches the consumption',
          journal['authority'] == full_digest(authority) and journal['binding'] == full_digest(binding)
          and journal['nonce'] == authority['nonce'] == consumption['permit_nonce']
          and journal['execution_id'] == consumption['execution_id']
          and request['consumption_digest'] == full_digest(consumption))
    check(f'{name}: approved text is the text the approval names',
          hashlib.sha256(approved['text'].encode()).hexdigest() == approved['sha256'] == contract['expected_sha256']
          and handoff['payload']['task'] == {'artifact': approved['text']})

    git_dir = scratch / (name + '.git')
    subprocess.run(['git', 'clone', '--quiet', '--bare', str(folder / 'repository.bundle'), str(git_dir)],
                   check=True, env=GIT_ENV, capture_output=True)
    p = contract['parameters']
    head = git(git_dir, 'rev-parse', 'refs/heads/' + p['branch']).decode().strip()
    new = git(git_dir, 'rev-list', '--reverse', p['parent_sha'] + '..' + head).decode().split()
    ours = [c for c in new if git(git_dir, 'log', '-1', '--format=%s', c).decode().strip()
            == 'ProofRail execution ' + consumption['execution_id']]
    check(f'{name}: exactly one dispatcher commit after the approved parent', len(ours) == 1,
          'dispatcher commits: %d' % len(ours))
    if len(ours) != 1:
        return
    commit = ours[0]
    check(f'{name}: dispatcher commit is the first commit on the approved parent',
          new[0] == commit and git(git_dir, 'rev-parse', commit + '^').decode().strip() == p['parent_sha']
          and git(git_dir, 'rev-parse', p['parent_sha'] + '^{tree}').decode().strip() == p['base_tree'])
    changed = git(git_dir, 'diff-tree', '--no-commit-id', '--name-only', '-r', p['parent_sha'], commit).decode().split()
    check(f'{name}: dispatcher commit changes only the approved path', changed == [p['path']], str(changed))
    entry = git(git_dir, 'ls-tree', '-z', commit, '--', p['path'])
    entries = entry.rstrip(b'\0').split(b'\0') if entry else []
    regular_file = False
    if len(entries) == 1:
        metadata, entry_path = entries[0].split(b'\t', 1)
        mode, kind, _ = metadata.split()
        regular_file = (mode == b'100644' and kind == b'blob'
                        and entry_path == p['path'].encode())
    check(f'{name}: approved artifact is a non-executable regular file', regular_file)
    expected = json.dumps({'kind': 'emergence.github-artifact.v1', 'execution_id': consumption['execution_id'],
                           'consumption_digest': full_digest(consumption), 'tenant': contract['tenant'],
                           'task_id': contract['task_id'], 'artifact': approved['text']},
                          sort_keys=True, indent=2) + '\n'
    actual = git(git_dir, 'cat-file', 'blob', commit + ':' + p['path'])
    check(f'{name}: committed file is exactly the approved text plus its execution record',
          actual == expected.encode())
    confirmed = [s for s in steps if s.get('result', {}).get('execution_id') == consumption['execution_id']]
    check(f'{name}: summary confirmation names this commit and these bytes',
          bool(confirmed) and all(s['result']['commit_sha'] == commit and
          s['result']['file_sha256'] == hashlib.sha256(actual).hexdigest() for s in confirmed))
    later = new[1:]
    if later:
        content = git(git_dir, 'cat-file', 'blob', head + ':' + p['path'])
        CHECKS.append({'check': f'{name}: later commits by others', 'result': 'NOTE',
                       'detail': '%d later commit(s); file at branch head %s the approved bytes' %
                       (len(later), 'matches' if content == expected.encode() else 'DIFFERS FROM')})


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--json', action='store_true', help='print the full report as JSON')
    args = parser.parse_args()
    root = args.evidence.resolve()
    try:
        verify_all(root)
    except Exception as exc:  # malformed evidence is a failure, never a crash
        check('evidence could be parsed', False, type(exc).__name__ + ': ' + str(exc)[:200])
    failed = [c for c in CHECKS if c['result'] == 'FAIL']
    if args.json:
        print(json.dumps({'verdict': 'FAIL' if failed else 'PASS', 'checks': CHECKS}, indent=2))
    else:
        for c in CHECKS:
            print(f"{c['result']:4}  {c['check']}" + (f"  [{c['detail']}]" if c['detail'] else ''))
        print('VERDICT:', 'FAIL' if failed else 'PASS', f'({len(CHECKS)} checks, {len(failed)} failed)')
    return 1 if failed else 0


def verify_all(root):
    verify_checksums(root)
    summary = load(root / 'summary.json')
    steps = summary['steps']
    raw = load(root / 'public-keys.json')
    keys = {n: Ed25519PublicKey.from_public_bytes(base64.b64decode(v)) for n, v in raw.items()}
    keys['agent_b64'] = raw['agent']
    by = {s['step'].split(' ', 1)[0]: s for s in steps}
    for label in ('2a', '2b'):
        check(f'step {label}: changed content refused with no write and no branch change',
              by[label]['outcome'] == 'REFUSED' and by[label]['provider_calls'] == []
              and by[label]['branch_head_after'] == by[label]['branch_head_before'])
    check('step 3: approved write confirmed with one branch update',
          by['3']['outcome'] == 'MATCH' and by['3']['branch_updates'] == 1
          and by['3']['independent_git_read_sha256'] == by['3']['result']['file_sha256'])
    for label in ('4', '6c'):
        check(f'step {label}: reuse of a used approval refused with no provider call',
              by[label]['outcome'] == 'REFUSED' and by[label]['provider_calls'] == [])
    check('step 5: edited destination not confirmed, and no write',
          by['5']['outcome'] == 'REFUSED' and by['5']['provider_write_calls'] == 0)
    check('step 6a: lost response reported as unknown, not success',
          by['6a']['outcome'] == 'OUTCOME_UNKNOWN' and by['6a']['branch_updates'] == 1)
    check('step 6b: recovery confirmed using reads only',
          by['6b']['outcome'] == 'MATCH' and by['6b']['provider_write_calls'] == 0
          and all(c.startswith('GET ') for c in by['6b']['provider_calls']))
    with tempfile.TemporaryDirectory() as scratch:
        for name in ('primary', 'recovery'):
            try:
                verify_run(root, name, keys, summary, steps, Path(scratch))
            except Exception as exc:  # malformed evidence is a failure, never a crash
                check(f'{name}: evidence could be checked', False, type(exc).__name__)


if __name__ == '__main__':
    sys.exit(main())

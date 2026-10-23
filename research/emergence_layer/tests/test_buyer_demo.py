"""The buyer demonstration reproduces from a clean run and its verifier rejects altered evidence.

Uses a real local git repository through buyer_demo/local_git_provider.py; this
is not a GitHub transport test.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / 'buyer_demo'


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          cwd=DEMO.parent)


def resum(root):
    lines = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
             for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS']
    (root / 'SHA256SUMS').write_text(''.join(lines))


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    base = tmp_path_factory.mktemp('demo')
    result = run(DEMO / 'run_demo.py', '--workdir', base / 'work', '--evidence', base / 'evidence')
    assert result.returncode == 0, result.stderr
    return base / 'evidence'


def test_demo_evidence_verifies(evidence):
    result = run(DEMO / 'verify_evidence.py', evidence, '--json')
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['verdict'] == 'PASS'
    assert not [c for c in report['checks'] if c['result'] == 'FAIL']


def test_demo_outcomes(evidence):
    steps = {s['step'].split(' ', 1)[0]: s for s in json.loads((evidence / 'summary.json').read_text())['steps']}
    assert steps['2a']['refusal'].endswith('Signature verification failed')
    assert steps['2b']['refusal'].endswith('predicate_not_authorized')
    assert steps['3']['outcome'] == 'MATCH' and steps['3']['branch_updates'] == 1
    assert steps['4']['refusal'].endswith('retained_authority_already_reserved')
    assert steps['5']['refusal'].endswith('commit_parent_changed')
    assert steps['6a']['outcome'] == 'OUTCOME_UNKNOWN'
    assert steps['6b']['outcome'] == 'MATCH' and steps['6b']['provider_write_calls'] == 0
    assert steps['6c']['refusal'].endswith('retained_authority_already_reserved')
    assert steps['7a']['outcome'] == 'MATCH'
    assert steps['7b']['refusal'].endswith('commit_tree_not_exact_approved_change')
    total_updates = sum(s['branch_updates'] for s in steps.values())
    assert total_updates == 3  # one per approval: primary, lost-response and look-alike runs


def test_export_holds_no_private_material(evidence):
    names = {str(p.relative_to(evidence)) for p in evidence.rglob('*') if p.is_file()}
    assert not [n for n in names if n.endswith(('.db', '.hex', '.key')) or 'private' in n]
    assert set(json.loads((evidence / 'public-keys.json').read_text())) == {
        'agent', 'approver', 'consumer', 'observer'}


def alter_text(root):
    path = root / 'approved-artifact.json'
    data = json.loads(path.read_text())
    data['text'] = data['text'].replace('38 minutes', '8 minutes')
    data['sha256'] = hashlib.sha256(data['text'].encode()).hexdigest()
    path.write_text(json.dumps(data))


def alter_consumption(root):
    path = root / 'primary' / 'execution' / 'consumption.json'
    data = json.loads(path.read_text())
    data['consumed_at'] -= 1
    path.write_text(json.dumps(data))


def swap_bundles(root):
    a, b = root / 'primary' / 'repository.bundle', root / 'recovery' / 'repository.bundle'
    tmp = a.with_suffix('.tmp')
    a.rename(tmp)
    b.rename(a)
    tmp.rename(b)


def drop_step(root):
    path = root / 'summary.json'
    data = json.loads(path.read_text())
    for step in data['steps']:
        if step['step'].startswith('6b'):
            step['provider_write_calls'] = 1
    path.write_text(json.dumps(data))


@pytest.mark.parametrize('alter', [alter_text, alter_consumption, swap_bundles, drop_step])
def test_altered_evidence_fails_even_with_regenerated_checksums(evidence, tmp_path, alter):
    copy = tmp_path / 'evidence'
    shutil.copytree(evidence, copy)
    alter(copy)
    resum(copy)
    result = run(DEMO / 'verify_evidence.py', copy, '--json')
    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)['verdict'] == 'FAIL'


def test_unlisted_file_fails(evidence, tmp_path):
    copy = tmp_path / 'evidence'
    shutil.copytree(evidence, copy)
    (copy / 'extra.txt').write_text('x')
    assert run(DEMO / 'verify_evidence.py', copy).returncode == 1


@pytest.mark.parametrize('mode', ['100755', '120000'])
def test_rewritten_file_mode_fails(evidence, tmp_path, mode):
    """Unsigned narrative/checksums cannot authorize a different Git entry type."""
    from buyer_demo.local_git_provider import GIT_ENV
    copy = tmp_path / 'evidence'
    shutil.copytree(evidence, copy)
    folder = copy / 'recovery'
    repo = tmp_path / 'rewrite.git'
    def git(*args, input=None):
        return subprocess.run(['git', '--git-dir', str(repo), *args], input=input,
                              capture_output=True, check=True, env=GIT_ENV).stdout.decode().strip()
    subprocess.run(['git', 'clone', '--bare', str(folder / 'repository.bundle'), str(repo)],
                   capture_output=True, check=True, env=GIT_ENV)
    contract = json.loads((folder / 'approval' / 'contract.json').read_text())
    p = contract['parameters']
    ref = 'refs/heads/' + p['branch']
    old = git('rev-parse', ref)
    blob = git('rev-parse', old + ':' + p['path'])
    git('read-tree', old)
    git('update-index', '--cacheinfo', mode + ',' + blob + ',' + p['path'])
    tree = git('write-tree')
    new = git('commit-tree', tree, '-p', p['parent_sha'], '-m', git('log', '-1', '--format=%s', old))
    git('update-ref', ref, new)
    (folder / 'repository.bundle').unlink()
    git('bundle', 'create', str(folder / 'repository.bundle'), ref)
    summary_path = copy / 'summary.json'
    summary = json.loads(summary_path.read_text())
    # The summary is explicitly unsigned: keep it consistent with the forged history.
    summary_path.write_text(json.dumps(summary).replace(old, new))
    resum(copy)
    result = run(DEMO / 'verify_evidence.py', copy, '--json')
    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)['verdict'] == 'FAIL'

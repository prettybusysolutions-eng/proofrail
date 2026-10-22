"""Gate-3 trial self-test: the three scenarios behave correctly against a real local
git repository, and the in-process fault leaves the branch updated on the provider.

This exercises the trial runner and app_fault with the unchanged Dispatcher. It is
NOT the live GitHub trial and does not cover transport-level interruption.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / 'live_trial'
sys.path[:0] = [str(LIVE), str(ROOT / 'buyer_demo'), str(ROOT)]

from app_fault import ResponseLostAfterCall, UNKNOWN  # noqa: E402

SOURCE = {'commit': 'test', 'tracked_changes': [], 'untracked': [], 'clean': True}


def test_runner_local_selftest(tmp_path):
    evidence = tmp_path / 'evidence'
    result = subprocess.run([sys.executable, str(LIVE / 'run_trial.py'), '--local',
                             '--evidence', str(evidence), '--workdir', str(tmp_path / 'work')],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (evidence / 'INCOMPLETE').exists()
    summary = json.loads((evidence / 'summary.json').read_text())
    a, b, c = summary['scenarios']

    assert a['outcome'] == 'MATCH' and a['write_calls'] == 3
    assert a['parent_sha'] != a['commit_sha']

    assert b['outcome'] == 'MATCH'
    assert b['lost_response_was_unknown'] is True
    assert b['dispatch_error'] == UNKNOWN
    assert b['recovery_outcome'] == 'MATCH'
    assert b['recovery_write_calls'] == 0
    assert all(call.startswith('GET ') for call in b['recovery_calls'])
    assert b['reuse_refused'].endswith('retained_authority_already_reserved')

    assert c['outcome'] == 'BLOCKED'
    assert c['first_dispatch_outcome'] == 'MATCH'
    assert c['admission_blocked'].endswith('execution_not_found')
    assert c['provider_calls_after_rollback'] == 0
    # The restored registry is older but not empty: it still holds A and B.
    assert c['restored_registry_holds'] == {'A': True, 'B': True, 'C': False}

    end = summary['provider_end_state']
    assert summary['verdict'] == 'PASS'
    assert end['result'] == 'PASS' and end['write_calls'] == 0
    assert [link['commit'] for link in end['chain']] == [
        a['commit_sha'], b['recovery_commit_sha'], c['first_commit_sha']]
    assert end['chain'][0]['parent'] == a['parent_sha'] == end['start_head']


def test_summary_has_no_secret_material(tmp_path):
    evidence = tmp_path / 'evidence'
    subprocess.run([sys.executable, str(LIVE / 'run_trial.py'), '--local',
                    '--evidence', str(evidence), '--workdir', str(tmp_path / 'work')],
                   capture_output=True, text=True, check=True)
    blob = (evidence / 'summary.json').read_text()
    assert 'PRIVATE KEY' not in blob and 'Authorization' not in blob and 'Bearer' not in blob
    summary = json.loads(blob)
    assert summary['mode'] == 'local-selftest'
    assert 'transport-level interruption during a call (reset, timeout, truncated body)' \
        in summary['not_covered'][0]
    # Only method+path strings are exported for calls, never bodies.
    for call in summary['scenarios'][1]['recovery_calls']:
        assert call.count(' ') == 1


class _Recorder:
    def __init__(self):
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        return {'ok': True, 'object': {'sha': 'a' * 40}}


def test_app_fault_forwards_then_drops_first_match_only():
    real = _Recorder()
    fault = ResponseLostAfterCall(real)
    assert fault.request('GET', '/x')['ok'] is True        # forwarded
    with pytest.raises(RuntimeError, match=UNKNOWN):
        fault.request('PATCH', '/git/refs/heads/b')        # real call made, response dropped
    assert fault.request('PATCH', '/git/refs/heads/b')['ok'] is True  # only the first is dropped
    # The provider saw every call, including the one whose response was dropped.
    assert real.calls == [('GET', '/x'), ('PATCH', '/git/refs/heads/b'), ('PATCH', '/git/refs/heads/b')]
    assert fault.events[1] == {'method': 'PATCH', 'path': '/git/refs/heads/b', 'response_discarded': True}


def test_app_fault_real_failure_is_not_recorded_as_loss():
    class Failing:
        def request(self, method, path, body=None):
            raise RuntimeError('provider_outcome_unknown')
    fault = ResponseLostAfterCall(Failing())
    with pytest.raises(RuntimeError):
        fault.request('PATCH', '/git/refs/heads/b')
    assert fault.events == []        # nothing marked discarded; the call itself failed
    assert fault._armed is True      # still armed: no response was actually dropped


def test_runner_rejects_fault_that_never_fires(tmp_path, monkeypatch):
    import run_trial
    from local_git_provider import LocalGitProvider, create_repository
    repository = 'demo-team/gate3-local'
    branch = 'trial/emergence-gate3'
    repo = tmp_path / 'repo.git'
    create_repository(repo, branch, {'README.md': 'fixture\n'})
    monkeypatch.setattr(run_trial, 'ResponseLostAfterCall', lambda client: client)
    scenarios, provider = run_trial.run(tmp_path / 'work', tmp_path / 'evidence', repository,
                                        branch, 'evidence/report.json',
                                        lambda: LocalGitProvider(repo, repository), SOURCE, 'local-selftest')
    assert scenarios[1]['outcome'] == 'UNEXPECTED'
    summary = json.loads((tmp_path / 'evidence' / 'summary.json').read_text())
    assert summary['verdict'] == 'FAIL'
    monkeypatch.setattr(run_trial, 'run', lambda *args: (scenarios, provider))
    monkeypatch.setattr(sys, 'argv', ['run_trial.py', '--local', '--evidence',
                                    str(tmp_path / 'cli-evidence'), '--workdir',
                                    str(tmp_path / 'cli-work')])
    assert run_trial.main() == 1


def _run_with(tmp_path, monkeypatch, before_scenario_b=None, after_run=None):
    """Run the trial locally; optionally act on the repository mid-run or afterwards."""
    import run_trial
    from local_git_provider import LocalGitProvider, create_repository
    repository, branch, path = 'demo-team/gate3-local', 'trial/emergence-gate3', 'evidence/report.json'
    repo = tmp_path / 'repo.git'
    create_repository(repo, branch, {'README.md': 'fixture\n'})
    real = run_trial.head_and_tree
    seen = {'n': 0}

    def head_and_tree(client, repo_name, branch_name):
        seen['n'] += 1
        if seen['n'] == 2 and before_scenario_b:
            before_scenario_b(repo, branch, path)
        return real(client, repo_name, branch_name)
    monkeypatch.setattr(run_trial, 'head_and_tree', head_and_tree)
    if after_run:
        real_verify = run_trial.verify_provider_chain

        def verify(client, *args):
            after_run(repo, branch, path)
            return real_verify(client, *args)
        monkeypatch.setattr(run_trial, 'verify_provider_chain', verify)
    scenarios, provider = run_trial.run(tmp_path / 'work', tmp_path / 'evidence', repository, branch, path,
                                        lambda: LocalGitProvider(repo, repository), SOURCE, 'local-selftest')
    summary = json.loads((tmp_path / 'evidence' / 'summary.json').read_text())
    return scenarios, provider, summary


def test_unapproved_commit_in_trial_window_fails(tmp_path, monkeypatch):
    """Every scenario can look right while someone else commits to the branch mid-run.
    Before the provider end-state check this exported verdict PASS."""
    from local_git_provider import commit_file
    scenarios, provider, summary = _run_with(
        tmp_path, monkeypatch,
        before_scenario_b=lambda repo, branch, path: commit_file(
            repo, branch, 'deploy/run.sh', '#!/bin/sh\necho unapproved\n', 'Unapproved change'))
    assert [s['outcome'] for s in scenarios] == ['MATCH', 'MATCH', 'BLOCKED']
    assert provider['result'] == 'FAIL'
    assert 'provider_history_differs_from_trial_record' in provider['reason']
    assert summary['verdict'] == 'FAIL'


def test_lookalike_replacing_a_trial_commit_fails(tmp_path, monkeypatch):
    """After the run, the head is replaced by a commit with the same parent and the
    same file bytes plus an extra file; the end-state check must not accept it."""
    from local_git_provider import git, replace_with_lookalike

    def swap(repo, branch, path):
        head = git(repo, 'rev-parse', 'refs/heads/' + branch).decode().strip()
        parent = git(repo, 'rev-parse', head + '^').decode().strip()
        data = git(repo, 'cat-file', 'blob', head + ':' + path)
        replace_with_lookalike(repo, branch, parent, path, data, 'deploy/run.sh', 'echo x\n')
    scenarios, provider, summary = _run_with(tmp_path, monkeypatch, after_run=swap)
    assert provider['result'] == 'FAIL'
    assert summary['verdict'] == 'FAIL'


def test_extra_commit_after_run_fails(tmp_path, monkeypatch):
    from local_git_provider import commit_file
    _, provider, summary = _run_with(
        tmp_path, monkeypatch,
        after_run=lambda repo, branch, path: commit_file(repo, branch, path, 'edited\n', 'Late edit'))
    assert provider['result'] == 'FAIL' and summary['verdict'] == 'FAIL'


def test_source_state_separates_commit_from_untracked_and_tracked_changes(tmp_path):
    """A venv inside the checkout used to turn the recorded SHA into '<sha>-dirty'."""
    import run_trial
    repo = tmp_path / 'checkout'
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / 'a.py').write_text('x = 1\n')
    subprocess.run(['git', '-C', str(repo), 'add', 'a.py'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t',
                    'commit', '-qm', 'init'], check=True)
    sha = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True,
                         text=True, check=True).stdout.strip()
    clean = run_trial.source_state(repo)
    assert clean == {'commit': sha, 'tracked_changes': [], 'untracked': [], 'clean': True}
    (repo / '.venv').mkdir()
    (repo / '.venv' / 'pyvenv.cfg').write_text('home = /usr\n')
    state = run_trial.source_state(repo)
    assert state['commit'] == sha and state['untracked'] == ['.venv/'] and not state['clean']
    (repo / 'a.py').write_text('x = 2\n')
    assert run_trial.source_state(repo)['tracked_changes'] == ['a.py']


def test_live_mode_refuses_unclean_checkout_before_any_provider_call(tmp_path, monkeypatch):
    import run_trial
    monkeypatch.setattr(run_trial, 'source_state', lambda root: {
        'commit': 'a' * 40, 'tracked_changes': [], 'untracked': ['.venv/'], 'clean': False})

    def no_provider(*args, **kwargs):
        raise AssertionError('provider client constructed for an unclean checkout')
    monkeypatch.setattr(run_trial, 'GitHubAPI', no_provider)
    monkeypatch.setattr(run_trial, 'run', no_provider)
    monkeypatch.setattr(sys, 'argv', ['run_trial.py', '--config', str(tmp_path / 'absent.json'),
                                      '--evidence', str(tmp_path / 'e'), '--workdir', str(tmp_path / 'w')])
    assert run_trial.main() == 2
    assert not (tmp_path / 'e').exists()


@pytest.mark.parametrize('failure', ['existing', 'parent_is_file'])
def test_invalid_evidence_destination_refuses_before_provider_calls(tmp_path, failure):
    import run_trial
    from local_git_provider import LocalGitProvider, create_repository, git
    repo = tmp_path / 'repo.git'
    repository, branch = 'demo-team/gate3-local', 'trial/emergence-gate3'
    initial, _ = create_repository(repo, branch, {'README.md': 'fixture\n'})
    client = LocalGitProvider(repo, repository)
    destination = tmp_path / 'evidence'
    if failure == 'existing':
        destination.mkdir()
        (destination / 'keep.txt').write_text('previous evidence')
    else:
        destination.write_text('not a directory')
        destination = destination / 'child'
    with pytest.raises(OSError):
        run_trial.run(tmp_path / 'work', destination, repository, branch,
                      'evidence/report.json', lambda: client, SOURCE, 'local-selftest')
    assert client.calls == [], 'invalid evidence destination was detected after provider activity'
    assert git(repo, 'rev-parse', 'refs/heads/' + branch).decode().strip() == initial


def test_provider_failure_leaves_incomplete_marker(tmp_path):
    import run_trial
    def unavailable():
        raise RuntimeError('provider unavailable')
    with pytest.raises(RuntimeError, match='provider unavailable'):
        run_trial.run(tmp_path / 'work', tmp_path / 'evidence', 'demo/repo',
                      'trial/emergence-test', 'evidence/report.json', unavailable,
                      SOURCE, 'local-selftest')
    assert (tmp_path / 'evidence' / 'INCOMPLETE').is_file()
    assert not (tmp_path / 'evidence' / 'summary.json').exists()


@pytest.mark.parametrize('nested', ['work', 'evidence', 'same'])
def test_work_and_evidence_cannot_overlap(tmp_path, nested):
    import run_trial
    work = tmp_path / 'work'
    evidence = work if nested == 'same' else work / 'evidence'
    if nested == 'work':
        work, evidence = evidence, work
    with pytest.raises(ValueError, match='work_and_evidence_must_be_separate'):
        run_trial.run(work, evidence, 'demo/repo', 'trial/emergence-test',
                      'evidence/report.json', lambda: pytest.fail('provider constructed'),
                      SOURCE, 'local-selftest')

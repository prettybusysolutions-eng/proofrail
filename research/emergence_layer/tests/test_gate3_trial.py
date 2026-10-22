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


def test_runner_local_selftest(tmp_path):
    evidence = tmp_path / 'evidence'
    result = subprocess.run([sys.executable, str(LIVE / 'run_trial.py'), '--local',
                             '--evidence', str(evidence), '--workdir', str(tmp_path / 'work')],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
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
    assert c['provider_write_calls_after_rollback'] == 0


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
    scenarios = run_trial.run(tmp_path / 'work', tmp_path / 'evidence', repository,
                              branch, 'evidence/report.json',
                              lambda: LocalGitProvider(repo, repository), 'test', 'local-selftest')
    assert scenarios[1]['outcome'] == 'UNEXPECTED'
    summary = json.loads((tmp_path / 'evidence' / 'summary.json').read_text())
    assert summary['verdict'] == 'FAIL'
    monkeypatch.setattr(run_trial, 'run', lambda *args: scenarios)
    monkeypatch.setattr(sys, 'argv', ['run_trial.py', '--local', '--evidence',
                                    str(tmp_path / 'cli-evidence'), '--workdir',
                                    str(tmp_path / 'cli-work')])
    assert run_trial.main() == 1

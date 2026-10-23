"""Reason-pinned tests for checks in the research verifiers off the pilot dispatcher path.

verify_observation, verify_execution, dispatch_local and LocalArtifactDestination
are used by the counterfactual lab and the HTTP server, not by enforcing_dispatcher.
Each test re-signs with the legitimate key where a signature would otherwise stop
the input first, so the named check is the one that must refuse it.
"""
import copy
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_acceptance_bridge import make_fixture, NOW
from acceptance_bridge import verify_observation
from execution_binding import ExecutionLedger, LocalArtifactDestination, verify_execution
from proofrail.crypto import canonical_json, sign_record

EXPECTED = hashlib.sha256(b'approved-specification-v1').hexdigest()


def reason(exc_info):
    return str(exc_info.value)


def resigned(record, key, key_id='observer-key', **changes):
    fields = {k: v for k, v in copy.deepcopy(record).items() if k not in ('signature', 'record_hash')}
    fields.update(changes)
    return sign_record(fields, key, key_id=key_id)


# ------------------------------------------------------------------ verify_observation

@pytest.fixture
def f():
    return make_fixture(EXPECTED)


def observe(f, observation):
    return verify_observation(f[0], f[1], observation, f[2], now=NOW)


@pytest.mark.parametrize('changes,expected', [
    ({'extra': 1}, 'invalid_observation_fields'),
    ({'kind': 'emergence.observation.v2'}, 'observation_version'),
    ({'observed_at': NOW + 1}, 'observation_time_invalid'),
    ({'observed_at': str(NOW)}, 'observation_time_invalid'),
    ({'status': 'maybe'}, 'observation_status'),
    ({'status': 'absent'}, 'unconfirmed_observation_has_content'),
    ({'content_sha256': 'A' * 64}, 'invalid_content_digest'),
])
def test_observation_checks(f, changes, expected):
    with pytest.raises(Exception) as exc:
        observe(f, resigned(f[3], f[6], **changes))
    assert reason(exc) == expected


def test_observation_signed_under_another_key_id(f):
    with pytest.raises(Exception) as exc:
        observe(f, resigned(f[3], f[6], key_id='other-observer'))
    assert reason(exc) == 'observer_key_changed'


# ------------------------------------------------------------------ verify_execution

@pytest.fixture
def s(tmp_path):
    fx = make_fixture(EXPECTED)
    ledger = ExecutionLedger(tmp_path / 'execution.db', Ed25519PrivateKey.generate(), 'consumer-key')
    destination = LocalArtifactDestination(tmp_path / 'destination.db')
    claim = ledger.consume(fx[0], fx[1], fx[2], clock=lambda: NOW)
    ledger.dispatch_local(claim['execution_id'], fx[0], fx[1], fx[2], destination, clock=lambda: NOW)
    observation = destination.observe(fx[1]['target'], tenant=fx[1]['tenant'], observer=fx[1]['observer'],
                                      key_id='observer-key', private_key=fx[6], now=NOW)
    return fx, ledger, destination, claim['execution_id'], observation


def execution(s, observation=None, now=NOW, fixture=None):
    fx = fixture or s[0]
    return verify_execution(s[1], s[3], fx[0], fx[1], fx[2], s[4] if observation is None else observation,
                            now=now)


def test_execution_integer_clock(s):
    with pytest.raises(Exception) as exc:
        execution(s, now=float(NOW))
    assert reason(exc) == 'integer_clock_required'


def test_execution_consumed_after_audit_time(s):
    with pytest.raises(Exception) as exc:
        execution(s, now=NOW - 1)
    assert reason(exc) == 'consumption_time_invalid'


def test_execution_audited_against_another_approval(s):
    with pytest.raises(Exception) as exc:
        execution(s, fixture=make_fixture(EXPECTED))
    assert reason(exc) == 'consumption_handoff_digest_changed'


@pytest.mark.parametrize('field,value,expected', [
    ('tenant', 'tenant-b', 'consumption_tenant_changed'),
    ('executor', 'someone-else', 'consumption_executor_changed'),
])
def test_execution_record_forged_with_the_consumer_key(s, field, value, expected):
    """Only reachable by someone holding the consumer signing key; defence in depth."""
    fx, ledger, _, execution_id, _ = s
    import sqlite3
    record, _ = ledger.get(execution_id)
    forged = sign_record({**{k: v for k, v in record.items() if k not in ('signature', 'record_hash')},
                          field: value}, ledger.private_key, key_id=ledger.key_id)
    with sqlite3.connect(ledger.path) as db:
        db.execute('UPDATE emergence_executions SET body=? WHERE execution_id=?',
                   (canonical_json(forged).decode(), execution_id))
        if field == 'executor':  # the shared permit claim cross-checks the executor first
            db.execute('UPDATE permit_claims SET executor_id=?', (value,))
    with pytest.raises(Exception) as exc:
        execution(s)
    assert reason(exc) == expected


@pytest.mark.parametrize('changes,expected', [
    ({'kind': 'emergence.execution-observation.v2'}, 'execution_observation_kind'),
    ({'observed_at': NOW + 5}, 'observation_time_invalid'),
    ({'status': 'maybe'}, 'observation_status'),
    ({'status': 'absent'}, 'inconsistent_absence'),
    ({'content_sha256': 'A' * 64}, 'invalid_content_digest'),
])
def test_execution_observation_checks(s, changes, expected):
    with pytest.raises(Exception) as exc:
        execution(s, observation=resigned(s[4], s[0][6], **changes))
    assert reason(exc) == expected


def test_execution_observation_too_old(s):
    late = NOW + s[0][1]['max_observation_age_seconds'] + 1
    with pytest.raises(Exception) as exc:
        execution(s, now=late)
    assert reason(exc) == 'observation_stale'


def test_execution_observation_under_another_key_id(s):
    with pytest.raises(Exception) as exc:
        execution(s, observation=resigned(s[4], s[0][6], key_id='other-observer'))
    assert reason(exc) == 'observer_key_changed'


# ------------------------------------------------------------------ dispatch_local / destination

def test_dispatch_local_rejects_unknown_fault(tmp_path):
    fx = make_fixture(EXPECTED)
    ledger = ExecutionLedger(tmp_path / 'e.db', Ed25519PrivateKey.generate(), 'consumer-key')
    claim = ledger.consume(fx[0], fx[1], fx[2], clock=lambda: NOW)
    with pytest.raises(Exception) as exc:
        ledger.dispatch_local(claim['execution_id'], fx[0], fx[1], fx[2],
                              LocalArtifactDestination(tmp_path / 'd.db'), clock=lambda: NOW, fault='sometimes')
    assert reason(exc) == 'invalid_fault'


def test_dispatch_local_only_for_fixture_effects(tmp_path):
    fx = make_fixture(EXPECTED)
    ledger = ExecutionLedger(tmp_path / 'e.db', Ed25519PrivateKey.generate(), 'consumer-key')
    contract = {**fx[1], 'target': 'github:owner/repo:main:README.md'}
    with pytest.raises(Exception) as exc:
        ledger.dispatch_local('unused', fx[0], contract, fx[2], LocalArtifactDestination(tmp_path / 'd.db'),
                              clock=lambda: NOW)
    assert reason(exc) == 'unsupported_local_effect'


def test_dispatch_local_only_for_artifact_tasks(tmp_path):
    fx = make_fixture(EXPECTED)
    handoff = copy.deepcopy(fx[0])
    handoff['payload']['task']['command'] = 'rm -rf /'
    ledger = ExecutionLedger(tmp_path / 'e.db', Ed25519PrivateKey.generate(), 'consumer-key')
    with pytest.raises(Exception) as exc:
        ledger.dispatch_local('unused', handoff, fx[1], fx[2], LocalArtifactDestination(tmp_path / 'd.db'),
                              clock=lambda: NOW)
    assert reason(exc) == 'unsupported_local_task'


def test_destination_accepts_only_text(tmp_path):
    destination = LocalArtifactDestination(tmp_path / 'd.db')
    with pytest.raises(Exception) as exc:
        destination.apply({'execution_id': 'e', 'tenant': 't', 'target': 'x'}, b'bytes')
    assert reason(exc) == 'artifact_must_be_text'

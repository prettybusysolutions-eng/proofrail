"""The first test preserves the observed pre-execution attribution gap."""
from test_acceptance_bridge import make_fixture, NOW
from acceptance_bridge import verify_observation
from acceptance_bridge import BindingError, full_digest
from execution_binding import ExecutionLedger, LocalArtifactDestination, verify_execution
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from proofrail.crypto import sign_record
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import copy
import hashlib
import multiprocessing
import sqlite3
import pytest


@pytest.fixture
def setup(tmp_path):
    f = make_fixture(hashlib.sha256(b'approved-specification-v1').hexdigest())
    ledger = ExecutionLedger(tmp_path / 'execution.db', Ed25519PrivateKey.generate(), 'consumer-key')
    destination = LocalArtifactDestination(tmp_path / 'destination.db')
    return f, ledger, destination


def consume(setup):
    f, ledger, _ = setup
    return ledger.consume(f[0], f[1], f[2], clock=lambda: NOW)


def dispatch(setup, execution_id, fault=None):
    f, ledger, destination = setup
    ledger.dispatch_local(execution_id, f[0], f[1], f[2], destination,
                          clock=lambda: NOW, fault=fault)


def observe(setup, now=NOW):
    f, _, destination = setup
    return destination.observe(f[1]['target'], tenant=f[1]['tenant'], observer=f[1]['observer'],
                               key_id=f[1]['observer_key_id'], private_key=f[6], now=now)


def verify(setup, execution_id, observation=None, now=NOW):
    f, ledger, _ = setup
    return verify_execution(ledger, execution_id, f[0], f[1], f[2], observation, now=now)


def test_legacy_state_match_does_not_establish_execution():
    handoff, contract, trust, observation, *_ = make_fixture()
    # No worker, destination, consumption ledger, or execution exists here.
    # A signed state observation still matches. This was documented read-only
    # behavior, not proof of a production authorization bypass.
    result = verify_observation(handoff, contract, observation, trust, now=NOW)
    assert result['outcome'] == 'MATCH'
    assert result['execution_authorized'] is False


def test_execution_verification_requires_real_consumption(setup):
    with pytest.raises(BindingError, match='execution_not_found'):
        verify(setup, 'nonexistent', setup[0][3])


def test_actual_effect_and_destination_provenance_match(setup):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    result = verify(setup, claim['execution_id'], observe(setup))
    assert result['outcome'] == 'MATCH'
    assert result['consumption_digest'] == full_digest(claim)
    assert not result['execution_authorized']


def test_old_state_receipt_cannot_be_execution_evidence(setup):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    with pytest.raises(BindingError, match='invalid_execution_observation'):
        verify(setup, claim['execution_id'], setup[0][3])


def test_consumed_but_not_dispatched_is_unconfirmed(setup):
    claim = consume(setup)
    assert verify(setup, claim['execution_id'], observe(setup))['outcome'] == 'UNCONFIRMED'


def test_same_authority_cannot_be_consumed_twice(setup):
    consume(setup)
    with pytest.raises(BindingError, match='already_consumed'):
        consume(setup)


def test_concurrent_consumption_has_one_winner(setup):
    def attempt(_):
        try:
            return consume(setup)['execution_id']
        except BindingError as exc:
            assert str(exc) == 'authority_already_consumed'
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(r is not None for r in results) == 1


def test_concurrent_dispatch_has_one_effect(setup):
    claim = consume(setup)
    def attempt(_):
        try:
            dispatch(setup, claim['execution_id'])
            return True
        except BindingError as exc:
            assert str(exc) == 'dispatch_already_started_no_retry'
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 1
    assert verify(setup, claim['execution_id'], observe(setup))['outcome'] == 'MATCH'
    with sqlite3.connect(setup[2].path) as db:
        assert db.execute('SELECT COUNT(*) FROM operations').fetchone()[0] == 1


@pytest.mark.parametrize('field,value', [
    ('execution_id', 'another-execution'), ('consumption_digest', 'b' * 64),
    ('target', 'fixture:other'), ('tenant', 'tenant-b'), ('observer', 'other'),
])
def test_valid_observer_signature_cannot_change_provenance(setup, field, value):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    observation = observe(setup)
    observation[field] = value
    observation = sign_record(observation, setup[0][6], key_id='observer-key')
    with pytest.raises(BindingError):
        verify(setup, claim['execution_id'], observation)


@pytest.mark.parametrize('fault,expected', [('after_mark', 'UNCONFIRMED'), ('after_effect', 'MATCH')])
def test_real_crash_restart_reconciles_without_redispatch(setup, fault, expected):
    claim = consume(setup)
    child = multiprocessing.get_context('fork').Process(target=dispatch,
                                                        args=(setup, claim['execution_id'], fault))
    child.start()
    child.join(15)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail('worker hung')
    assert child.exitcode == 73
    f, old, destination = setup
    restarted = ExecutionLedger(old.path, old.private_key, old.key_id)
    restarted_setup = f, restarted, destination
    assert verify(restarted_setup, claim['execution_id'], observe(setup))['outcome'] == expected
    with pytest.raises(BindingError, match='no_retry'):
        dispatch(restarted_setup, claim['execution_id'])


def test_renewed_authority_same_target_cannot_claim_prior_run(setup, monkeypatch):
    from smatp import sign, unsigned
    claim_a = consume(setup)
    dispatch(setup, claim_a['execution_id'])
    f, ledger, dest = setup
    env = copy.deepcopy(f[0])
    authority = env['payload']['authority']
    authority['nonce'] = 'fresh-authority-nonce-0002'
    authority['envelope_id'] = 'renewed-authority'
    authority = sign_record(authority, f[5], key_id='authority-key')
    env['payload']['authority'] = authority
    env = sign(unsigned(env), f[4])
    trust = replace(f[2], authority_digest=full_digest(authority))
    claim_b = ledger.consume(env, f[1], trust, clock=lambda: NOW)
    # B crosses the dispatch boundary but dies before its effect. Destination
    # still contains A's identical expected bytes; state equality is insufficient.
    other = ((env, f[1], trust, *f[3:]), ledger, dest)
    child = multiprocessing.get_context('fork').Process(target=dispatch,
                                                        args=(other, claim_b['execution_id'], 'after_mark'))
    child.start()
    child.join(15)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail('worker hung')
    assert child.exitcode == 73
    observation = observe(setup)
    assert observation['content_sha256'] == f[1]['expected_sha256']
    legacy = copy.deepcopy(f[3])
    legacy.update(handoff_digest=full_digest(env), authority_digest=full_digest(authority),
                  content_sha256=observation['content_sha256'])
    legacy = sign_record(legacy, f[6], key_id='observer-key')
    assert verify_observation(env, f[1], legacy, trust, now=NOW)['outcome'] == 'MATCH'
    with pytest.raises(BindingError, match='observation_execution_changed'):
        verify(other, claim_b['execution_id'], observation)
    # Counterfactual mutation: remove only the execution/provenance binding
    # checks, keeping signatures, content, timestamps and authority checks.
    import execution_binding
    original = execution_binding.require
    def without_provenance(condition, reason):
        if reason not in ('observation_execution_changed', 'observation_consumption_changed'):
            original(condition, reason)
    with monkeypatch.context() as context:
        context.setattr(execution_binding, 'require', without_provenance)
        assert verify(other, claim_b['execution_id'], observation)['outcome'] == 'MATCH'


def test_reconciliation_after_authority_expiry_uses_consumption_time(setup):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    assert verify(setup, claim['execution_id'], observe(setup, NOW + 400), NOW + 400)['outcome'] == 'MATCH'


def test_expiry_before_dispatch_blocks_effect(setup):
    claim = consume(setup)
    f, ledger, dest = setup
    with pytest.raises(BindingError, match='handoff_expired'):
        ledger.dispatch_local(claim['execution_id'], f[0], f[1], f[2], dest, clock=lambda: NOW + 300)
    assert observe(setup)['status'] == 'absent'


def test_consumption_database_tampering_is_detected(setup):
    import json
    claim = consume(setup)
    with sqlite3.connect(setup[1].path) as db:
        claim['target'] = 'fixture:other'
        db.execute('UPDATE executions SET body=?', (json.dumps(claim),))
    with pytest.raises(ValueError):
        verify(setup, claim['execution_id'])


def test_cross_tenant_readback_does_not_find_artifact(setup):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    f, _, dest = setup
    observation = dest.observe(f[1]['target'], tenant='tenant-b', observer=f[1]['observer'],
                               key_id='observer-key', private_key=f[6], now=NOW)
    assert observation['status'] == 'absent'


def test_actual_content_tamper_is_diverged(setup):
    claim = consume(setup)
    dispatch(setup, claim['execution_id'])
    with sqlite3.connect(setup[2].path) as db:
        db.execute("UPDATE artifacts SET content='wrong'")
    assert verify(setup, claim['execution_id'], observe(setup))['outcome'] == 'DIVERGED'

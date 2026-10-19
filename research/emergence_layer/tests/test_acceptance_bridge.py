import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from acceptance_bridge import Trust, full_digest, verify_handoff, verify_observation
from proofrail.crypto import sign_record
from proofrail.envelope import mint_action_authority_envelope
from smatp import make_envelope, new_identity, sign, unsigned

NOW = 1792406400


@pytest.fixture
def fixture():
    sender, sender_pub = new_identity()
    authority_key = Ed25519PrivateKey.generate()
    observer_key = Ed25519PrivateKey.generate()
    task = {'artifact': 'approved-specification-v1'}
    contract = {
        'kind': 'emergence.acceptance.v1', 'tenant': 'tenant-a', 'task_id': 'task-1',
        'sender': 'requester', 'recipient': 'executor', 'capability': 'publish-artifact',
        'task_digest': full_digest(task), 'action_type': 'artifact_write',
        'target': 'fixture:artifact-1', 'parameters': {'version': 1},
        'expected_sha256': 'a' * 64, 'observer': 'provider-observer',
        'observer_key_id': 'observer-key', 'max_observation_age_seconds': 60,
    }
    roots = {name: str(i) * 64 for i, name in enumerate(('identity', 'evidence', 'policy', 'state'), 1)}
    now = datetime.fromtimestamp(NOW, timezone.utc)
    authority = mint_action_authority_envelope(
        roots=roots, approval_digest='5' * 64, action_type=contract['action_type'],
        target=contract['target'], parameters=contract['parameters'],
        subject_principal_id='executor', subject_role='executor',
        issuer_principal_id='governor', issuer_role='verifier',
        adapter_contract={'name': 'fixture', 'version': 'v1', 'idempotency_required': True},
        observation_contract={'name': 'emergence.acceptance', 'version': 'v1',
                              'minimum_confirmations': 1,
                              'success_predicate_digest': full_digest(contract)},
        nonce='authority-nonce-0000001', expires_at=now + timedelta(minutes=5),
        private_key=authority_key, key_id='authority-key', now=now)
    handoff = make_envelope('requester', 'executor', 'publish-artifact',
                           {'task': task, 'contract': contract, 'authority': authority},
                           sender, now=NOW)
    trust = Trust(sender_pub, authority_key.public_key(), 'authority-key', full_digest(authority),
                  {'principal_id': 'governor', 'role': 'verifier'},
                  observer_key.public_key(), 'observer-key', roots, '5' * 64)
    observation = sign_record({
        'kind': 'emergence.observation.v1', 'tenant': 'tenant-a', 'task_id': 'task-1',
        'target': contract['target'], 'observer': contract['observer'],
        'contract_digest': full_digest(contract), 'handoff_digest': full_digest(handoff),
        'authority_digest': full_digest(authority), 'observed_at': NOW,
        'status': 'present', 'content_sha256': 'a' * 64}, observer_key, key_id='observer-key')
    return handoff, contract, trust, observation, sender, authority_key, observer_key


def check(f, observation=None, now=NOW):
    return verify_observation(f[0], f[1], f[3] if observation is None else observation, f[2], now=now)


def test_valid_binding_is_not_execution_authorization(fixture):
    result = check(fixture)
    assert result['outcome'] == 'MATCH'
    assert result['execution_authorized'] is False


@pytest.mark.parametrize('field,value', [
    ('tenant', 'tenant-b'), ('task_id', 'task-2'), ('target', 'fixture:other'),
    ('expected_sha256', 'b' * 64), ('observer', 'attacker'), ('recipient', 'attacker'),
])
def test_sender_cannot_rewrite_contract_even_with_valid_signature(fixture, field, value):
    env = copy.deepcopy(fixture[0])
    env['payload']['contract'][field] = value
    env = sign(unsigned(env), fixture[4])
    with pytest.raises(ValueError):
        verify_handoff(env, fixture[1], fixture[2], now=NOW)


def test_sender_cannot_replace_task(fixture):
    env = copy.deepcopy(fixture[0])
    env['payload']['task']['artifact'] = 'other'
    env = sign(unsigned(env), fixture[4])
    with pytest.raises(ValueError, match='task_changed'):
        verify_handoff(env, fixture[1], fixture[2], now=NOW)


def test_different_valid_authority_is_not_the_enrolled_authority(fixture):
    env = copy.deepcopy(fixture[0])
    authority = env['payload']['authority']
    authority['nonce'] = 'replacement-authority-nonce'
    env['payload']['authority'] = sign_record(authority, fixture[5], key_id='authority-key')
    env = sign(unsigned(env), fixture[4])
    with pytest.raises(ValueError, match='authority_substituted'):
        verify_handoff(env, fixture[1], fixture[2], now=NOW)


def test_contract_must_be_bound_by_authority_not_just_sender(fixture):
    env = copy.deepcopy(fixture[0])
    contract = copy.deepcopy(fixture[1])
    contract['expected_sha256'] = 'b' * 64
    env['payload']['contract'] = contract
    env = sign(unsigned(env), fixture[4])
    with pytest.raises(ValueError, match='predicate_not_authorized'):
        verify_handoff(env, contract, fixture[2], now=NOW)


@pytest.mark.parametrize('field,value', [
    ('tenant', 'tenant-b'), ('task_id', 'task-2'), ('target', 'fixture:other'),
    ('observer', 'other'), ('handoff_digest', 'b' * 64),
    ('authority_digest', 'b' * 64), ('contract_digest', 'b' * 64),
])
def test_signed_observation_cannot_be_transplanted(fixture, field, value):
    observation = copy.deepcopy(fixture[3])
    observation[field] = value
    observation = sign_record(observation, fixture[6], key_id='observer-key')
    with pytest.raises(ValueError):
        check(fixture, observation)


def test_attacker_using_observer_key_label_is_rejected(fixture):
    observation = sign_record(fixture[3], Ed25519PrivateKey.generate(), key_id='observer-key')
    with pytest.raises(ValueError):
        check(fixture, observation)


def test_stale_observation_rejected(fixture):
    with pytest.raises(ValueError, match='observation_stale'):
        check(fixture, now=NOW + 61)


def test_expired_handoff_rejected(fixture):
    with pytest.raises(ValueError, match='handoff_expired'):
        check(fixture, now=NOW + 300)


@pytest.mark.parametrize('status', ['absent', 'unknown'])
def test_absence_and_uncertainty_never_match(fixture, status):
    observation = copy.deepcopy(fixture[3])
    observation.update(status=status, content_sha256=None)
    observation = sign_record(observation, fixture[6], key_id='observer-key')
    assert check(fixture, observation)['outcome'] == 'UNCONFIRMED'


def test_missing_evidence_stays_unconfirmed(fixture):
    assert verify_observation(fixture[0], fixture[1], None, fixture[2], now=NOW)['outcome'] == 'UNCONFIRMED'


def test_wrong_content_is_diverged_not_success(fixture):
    observation = copy.deepcopy(fixture[3])
    observation['content_sha256'] = 'b' * 64
    observation = sign_record(observation, fixture[6], key_id='observer-key')
    assert check(fixture, observation)['outcome'] == 'DIVERGED'


def test_changed_policy_roots_rejected(fixture):
    trust = replace(fixture[2], roots={**fixture[2].roots, 'policy': 'f' * 64})
    with pytest.raises(ValueError, match='policy_root_changed'):
        verify_handoff(fixture[0], fixture[1], trust, now=NOW)


def test_digest_does_not_drop_task_fields_named_signature():
    assert full_digest({'signature': 'one'}) != full_digest({'signature': 'two'})

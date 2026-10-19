"""Read-only research bridge to ProofRail's existing authority verifier.

MATCH means signed evidence meets the pinned predicate. It does not authorize
execution, consume authority, prove provider honesty, or permit a retry.
All expected values and keys come from a trusted caller, never the handoff.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re

from proofrail.core import ProofRailError, parse_time
from proofrail.crypto import canonical_json, verify_signature
from proofrail.envelope import verify_action_authority_envelope
from smatp import check_signature, key_id


class BindingError(ProofRailError):
    pass


def full_digest(value):
    """Include every field, including any nested or top-level signatures."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def require(condition, reason):
    if not condition:
        raise BindingError(reason)


@dataclass(frozen=True)
class Trust:
    sender_public_b64: str
    authority_public: object
    authority_key_id: str
    authority_digest: str
    issuer: dict
    observer_public: object
    observer_key_id: str
    roots: dict
    approval_digest: str


CONTRACT_FIELDS = {
    'kind', 'tenant', 'task_id', 'sender', 'recipient', 'capability',
    'task_digest', 'action_type', 'target', 'parameters', 'expected_sha256',
    'observer', 'observer_key_id', 'max_observation_age_seconds',
}


def verify_handoff(handoff, contract, trust, *, now):
    """Verify exact binding; returns no execution grant and performs no writes."""
    require(type(now) is int, 'integer_clock_required')
    require(isinstance(contract, dict) and set(contract) == CONTRACT_FIELDS,
            'invalid_contract_fields')
    require(contract['kind'] == 'emergence.acceptance.v1', 'contract_version')
    for field in ('tenant', 'task_id', 'sender', 'recipient', 'capability',
                  'action_type', 'target', 'observer', 'observer_key_id'):
        require(isinstance(contract[field], str) and bool(contract[field]), 'invalid_' + field)
    for field in ('task_digest', 'expected_sha256'):
        require(isinstance(contract[field], str) and
                re.fullmatch('[0-9a-f]{64}', contract[field]), 'invalid_' + field)
    require(type(contract['max_observation_age_seconds']) is int and
            0 < contract['max_observation_age_seconds'] <= 3600, 'invalid_observation_age')
    require(contract['observer_key_id'] == trust.observer_key_id, 'observer_key_changed')
    require(isinstance(contract['parameters'], dict), 'invalid_parameters')
    fields = {'version', 'message_id', 'sender', 'recipient', 'sender_key_id',
              'capability', 'payload', 'created_at', 'expires_at', 'nonce',
              'idempotency_key', 'signature'}
    require(isinstance(handoff, dict) and set(handoff) == fields, 'invalid_handoff_fields')
    require(handoff['version'] == 'smatp/0.1', 'handoff_version')
    for field in ('message_id', 'nonce', 'idempotency_key'):
        require(isinstance(handoff[field], str) and 0 < len(handoff[field]) <= 128,
                'invalid_' + field)
    require(type(handoff['created_at']) is int and type(handoff['expires_at']) is int,
            'invalid_handoff_time')
    require(handoff['created_at'] <= now < handoff['expires_at'] and
            handoff['expires_at'] - handoff['created_at'] <= 86400, 'handoff_expired_or_future')
    for field in ('sender', 'recipient', 'capability'):
        require(handoff[field] == contract[field], field + '_changed')
    require(handoff['sender_key_id'] == key_id(trust.sender_public_b64), 'sender_key_changed')
    check_signature(handoff, trust.sender_public_b64)
    payload = handoff['payload']
    require(isinstance(payload, dict) and set(payload) == {'task', 'authority', 'contract'},
            'invalid_payload')
    require(canonical_json(payload['contract']) == canonical_json(contract), 'contract_changed')
    require(full_digest(payload['task']) == contract['task_digest'], 'task_changed')
    authority = payload['authority']
    require(full_digest(authority) == trust.authority_digest, 'authority_substituted')
    require(authority['signature']['key_id'] == trust.authority_key_id, 'authority_key_changed')
    require(authority['issuer'] == trust.issuer, 'issuer_changed')
    require(authority['subject'] == {'principal_id': contract['recipient'], 'role': 'executor'},
            'subject_changed')
    require(parse_time(authority['issued_at']).timestamp() <= now, 'authority_not_yet_valid')
    verify_action_authority_envelope(
        authority, public_key=trust.authority_public, expected_roots=trust.roots,
        expected_approval_digest=trust.approval_digest,
        action_type=contract['action_type'], target=contract['target'],
        parameters=contract['parameters'], now=datetime.fromtimestamp(now, timezone.utc))
    require(authority['observation_contract'] == {
        'name': 'emergence.acceptance', 'version': 'v1', 'minimum_confirmations': 1,
        'success_predicate_digest': full_digest(contract)}, 'predicate_not_authorized')
    return {'binding': 'VERIFIED', 'handoff_digest': full_digest(handoff),
            'authority_digest': full_digest(authority), 'contract_digest': full_digest(contract),
            'execution_authorized': False}


def verify_observation(handoff, contract, observation, trust, *, now):
    binding = verify_handoff(handoff, contract, trust, now=now)
    if observation is None:
        return {**binding, 'outcome': 'UNCONFIRMED', 'reason': 'no_observation'}
    required = {'kind', 'tenant', 'task_id', 'target', 'observer', 'contract_digest',
                'handoff_digest', 'authority_digest', 'observed_at', 'status',
                'content_sha256', 'signature', 'record_hash'}
    require(isinstance(observation, dict) and set(observation) == required,
            'invalid_observation_fields')
    require(observation['kind'] == 'emergence.observation.v1', 'observation_version')
    require(isinstance(observation['signature'], dict) and
            observation['signature'].get('key_id') == trust.observer_key_id,
            'observer_key_changed')
    verify_signature(observation, trust.observer_public)
    for field in ('tenant', 'task_id', 'target', 'observer'):
        require(observation[field] == contract[field], 'observation_' + field + '_changed')
    for field in ('handoff_digest', 'authority_digest', 'contract_digest'):
        require(observation[field] == binding[field], 'observation_' + field + '_changed')
    observed_at = observation['observed_at']
    require(type(observed_at) is int and handoff['created_at'] <= observed_at <= now,
            'observation_time_invalid')
    require(now - observed_at <= contract['max_observation_age_seconds'], 'observation_stale')
    require(observation['status'] in ('present', 'absent', 'unknown'), 'observation_status')
    actual = observation['content_sha256']
    if observation['status'] != 'present':
        require(actual is None, 'unconfirmed_observation_has_content')
        return {**binding, 'outcome': 'UNCONFIRMED', 'reason': observation['status']}
    require(isinstance(actual, str) and re.fullmatch('[0-9a-f]{64}', actual), 'invalid_content_digest')
    return {**binding, 'outcome': 'MATCH' if actual == contract['expected_sha256'] else 'DIVERGED',
            'observation_digest': full_digest(observation)}

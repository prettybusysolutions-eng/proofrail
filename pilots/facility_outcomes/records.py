"""Records, digests, signatures and principals for the facility pilot.

Uses ProofRail's own primitives (RFC 8785 canonical JSON, SHA-256 record hashes,
Ed25519 signatures) rather than introducing new ones. Identity is possession of a
registered key: a record is attributed to a principal only if it verifies under
that principal's registered public key. Caller-supplied identity fields are never
trusted on their own.
"""
from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from jsonschema import Draft202012Validator

from proofrail.crypto import hash_record, sign_record, verify_signature

SCHEMAS = Path(__file__).resolve().parent / 'contracts'   # not 'schemas': that would shadow proofrail's package


class PilotError(Exception):
    """A refusal. The message is a stable reason code; it never carries secrets."""

    def __init__(self, reason: str, detail: str = ''):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def require(condition: bool, reason: str, detail: str = '') -> None:
    if not condition:
        raise PilotError(reason, detail)


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / f'{name}.schema.json').read_text()))


def validate(name: str, record: Mapping[str, Any]) -> None:
    errors = sorted(_validator(name).iter_errors(record), key=lambda e: list(e.path))
    require(not errors, f'invalid_{name}', errors[0].message[:200] if errors else '')


def digest(value: Any) -> str:
    """Canonical SHA-256 of a JSON value, ignoring record_hash and signature."""
    if isinstance(value, Mapping):
        return hash_record(value)
    return hash_record({'value': value})


def utc(text: str) -> datetime:
    require(isinstance(text, str) and text.endswith('Z'), 'invalid_timestamp')
    try:
        return datetime.fromisoformat(text[:-1] + '+00:00')
    except ValueError:
        raise PilotError('invalid_timestamp') from None


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Clock:
    """Injected time. Tests and the reproducible runner pin it; nothing reads wall time directly."""

    def __init__(self, start: datetime):
        self._now = start.astimezone(timezone.utc).replace(microsecond=0)

    def now(self) -> datetime:
        return self._now

    def text(self) -> str:
        return stamp(self._now)

    def advance(self, **delta) -> None:
        from datetime import timedelta
        self._now = self._now + timedelta(**delta)


def encode_public(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def decode_public(text: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(text, validate=True))


ROLES = frozenset({
    'reporter', 'problem_reviewer', 'planner', 'approver', 'authority_issuer', 'gateway',
    'provider_observer', 'contractor', 'provider', 'inspector', 'outcome_reviewer', 'buyer',
    'settlement_authorizer', 'tenant_admin',
})


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str            # the tenant this principal acts for (provider staff: the tenant they serve)
    organization: str         # employing organisation, used for independence checks
    roles: frozenset
    key_id: str
    public_key: str           # base64 raw Ed25519

    def describe(self) -> dict[str, Any]:
        return {'principal_id': self.principal_id, 'tenant_id': self.tenant_id,
                'organization': self.organization, 'roles': sorted(self.roles),
                'key_id': self.key_id, 'public_key': self.public_key}


@dataclass
class Identity:
    """A principal plus its private key. Only test fixtures and the runner hold these."""
    principal: Principal
    private_key: Ed25519PrivateKey = field(repr=False)

    def sign(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return sign_record(record, self.private_key, key_id=self.principal.key_id)


class Registry:
    """Registered principals and buyer-designated inspectors. Its digest is the identity root."""

    def __init__(self):
        self._by_id: dict[str, Principal] = {}
        self._by_key: dict[str, Principal] = {}
        self._designations: set[tuple[str, str, str]] = set()   # (tenant, facility, inspector)

    def add(self, principal_id: str, *, tenant_id: str, organization: str, roles: Iterable[str]) -> Identity:
        roles = frozenset(roles)
        require(roles <= ROLES and roles, 'unknown_role')
        require(principal_id not in self._by_id, 'duplicate_principal')
        key = Ed25519PrivateKey.generate()
        principal = Principal(principal_id, tenant_id, organization, roles, 'key-' + principal_id,
                              encode_public(key.public_key()))
        self._by_id[principal_id] = principal
        self._by_key[principal.key_id] = principal
        return Identity(principal, key)

    def adopt(self, principal: Principal, private_key: Ed25519PrivateKey) -> Identity:
        """Re-register a persisted test identity (multi-process tests reload the same world)."""
        require(principal.principal_id not in self._by_id, 'duplicate_principal')
        require(encode_public(private_key.public_key()) == principal.public_key, 'key_does_not_match_principal')
        self._by_id[principal.principal_id] = principal
        self._by_key[principal.key_id] = principal
        return Identity(principal, private_key)

    def restore_designations(self, designations) -> None:
        self._designations = {tuple(d) for d in designations}

    def designations(self) -> list:
        return sorted(map(list, self._designations))

    def designate_inspector(self, *, tenant_id: str, facility_id: str, inspector_id: str,
                            by: Identity) -> None:
        require(by.principal.tenant_id == tenant_id and 'buyer' in by.principal.roles,
                'designation_requires_tenant_buyer')
        inspector = self.get(inspector_id)
        require('inspector' in inspector.roles, 'designee_not_inspector')
        self._designations.add((tenant_id, facility_id, inspector_id))

    def designated(self, tenant_id: str, facility_id: str, inspector_id: str) -> bool:
        return (tenant_id, facility_id, inspector_id) in self._designations

    def get(self, principal_id: str) -> Principal:
        principal = self._by_id.get(principal_id)
        require(principal is not None, 'unknown_principal')
        return principal

    def signer(self, record: Mapping[str, Any], *, role: str, tenant_id: str) -> Principal:
        """Return the principal whose registered key signed `record`, if it holds `role` for `tenant_id`."""
        signature = record.get('signature')
        require(isinstance(signature, Mapping), 'signature_missing')
        principal = self._by_key.get(signature.get('key_id'))
        require(principal is not None, 'unknown_signing_key')
        try:
            verify_signature(record, decode_public(principal.public_key))
        except Exception:
            raise PilotError('signature_invalid') from None
        require(role in principal.roles, 'signer_role_not_permitted', role)
        require(principal.tenant_id == tenant_id, 'signer_tenant_mismatch')
        return principal

    def principals(self) -> list[Principal]:
        return list(self._by_id.values())

    def root(self) -> str:
        return digest({'principals': [p.describe() for p in sorted(self._by_id.values(), key=lambda p: p.principal_id)],
                       'designations': sorted(map(list, self._designations))})

    def public_keys(self) -> dict[str, Any]:
        return {p.principal_id: p.describe() for p in self._by_id.values()}


def without(record: Mapping[str, Any], *fields: str) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in record.items() if k not in fields}

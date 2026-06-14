from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from jsonschema import Draft202012Validator

from .crypto import hash_record, sign_record, verify_signature
from .permit import PERMIT_ISSUER_ROLES, PermitError

ROOT_NAMES = ("identity", "evidence", "policy", "state")


def effect_digest(
    action_type: str,
    target: str,
    parameters: Mapping[str, Any],
) -> str:
    return hash_record(
        {
            "action_type": action_type,
            "target": target,
            "parameters": dict(parameters),
        }
    )


def mint_action_authority_envelope(
    *,
    roots: Mapping[str, str],
    approval_digest: str,
    action_type: str,
    target: str,
    parameters: Mapping[str, Any],
    subject_principal_id: str,
    subject_role: str,
    issuer_principal_id: str,
    issuer_role: str,
    adapter_contract: Mapping[str, Any],
    observation_contract: Mapping[str, Any],
    nonce: str,
    expires_at: datetime | str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    now: datetime | None = None,
    constraints: Mapping[str, Any] | None = None,
    trust: Mapping[str, Any] | None = None,
    envelope_id: str | None = None,
) -> dict[str, Any]:
    issued_at = _utc(now)
    expiry = _parse_time(expires_at)
    if issuer_role not in PERMIT_ISSUER_ROLES:
        raise PermitError("issuer_role_forbidden")
    if expiry <= issued_at:
        raise PermitError("permit_expired")
    if not isinstance(nonce, str) or len(nonce) < 16:
        raise PermitError("invalid_nonce")
    if not action_type or not target:
        raise PermitError("effect_missing")

    normalized_roots = {name: roots.get(name) for name in ROOT_NAMES}
    for name, value in normalized_roots.items():
        _require_digest(value, f"{name}_root")
    _require_digest(approval_digest, "approval_digest")

    record: dict[str, Any] = {
        "kind": "proofrail.action-authority-envelope.v1",
        "envelope_id": envelope_id or str(uuid.uuid4()),
        "state": "PERMITTED",
        "issued_at": _format_time(issued_at),
        "expires_at": _format_time(expiry),
        "nonce": nonce,
        "issuer": {"principal_id": issuer_principal_id, "role": issuer_role},
        "subject": {"principal_id": subject_principal_id, "role": subject_role},
        "roots": normalized_roots,
        "approval_digest": approval_digest,
        "effect": {
            "action_type": action_type,
            "target": target,
            "parameters": dict(parameters),
            "effect_digest": effect_digest(action_type, target, parameters),
        },
        "constraints": dict(constraints or {}),
        "adapter_contract": dict(adapter_contract),
        "observation_contract": dict(observation_contract),
        "failure_semantics": {
            "consume_before_effect": True,
            "ambiguous_outcome": "RECONCILIATION_FAILED",
            "retry": "NEW_AUTHORITY_REQUIRED",
        },
    }
    if trust is not None:
        record["trust"] = dict(trust)
    signed = sign_record(record, private_key, key_id=key_id)
    _validator().validate(signed)
    return signed


def verify_action_authority_envelope(
    envelope: Mapping[str, Any],
    *,
    public_key: Ed25519PublicKey | bytes,
    expected_roots: Mapping[str, str],
    expected_approval_digest: str,
    action_type: str,
    target: str,
    parameters: Mapping[str, Any],
    now: datetime | None = None,
) -> bool:
    try:
        _validator().validate(envelope)
        verify_signature(envelope, public_key)
    except Exception as exc:
        raise PermitError("invalid_envelope", str(exc)) from exc
    if _utc(now) >= _parse_time(str(envelope["expires_at"])):
        raise PermitError("permit_expired")

    roots = envelope["roots"]
    for name in ROOT_NAMES:
        if roots.get(name) != expected_roots.get(name):
            raise PermitError(f"{name}_root_changed")
    if envelope.get("approval_digest") != expected_approval_digest:
        raise PermitError("approval_scope_changed")

    effect = envelope["effect"]
    expected_digest = effect_digest(action_type, target, parameters)
    if effect.get("action_type") != action_type:
        raise PermitError("action_type_changed")
    if effect.get("target") != target:
        raise PermitError("target_changed")
    if effect.get("parameters") != dict(parameters):
        raise PermitError("parameters_changed")
    if effect.get("effect_digest") != expected_digest:
        raise PermitError("effect_digest_changed")
    return True


def _validator() -> Draft202012Validator:
    schema_path = files("schemas").joinpath("action_authority_envelope.schema.json")
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise PermitError("timezone_required")
    return current.astimezone(timezone.utc)


def _parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (AttributeError, ValueError) as exc:
        raise PermitError("invalid_timestamp") from exc


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_digest(value: object, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise PermitError("invalid_digest", field)
    try:
        int(value, 16)
    except ValueError as exc:
        raise PermitError("invalid_digest", field) from exc

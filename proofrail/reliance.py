"""Portable relying-party acceptance check for two signed, normalized records.

This is an OFFLINE evidence verifier, not an authorization engine or a
provider-enforcing gateway. Adapters must bind actual upstream decisions and
provider observations before signing; self-asserted normalization is not proof.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .core import ProofRailError
from .crypto import verify_signature


AUTH_KIND = "proofrail.reliance.authorization.v0"
OBS_KIND = "proofrail.reliance.observation.v0"
OUTCOMES = frozenset(("applied", "failed", "unknown"))


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an explicit UTC ISO8601 string ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def _public_bytes(key: Ed25519PublicKey | bytes) -> bytes:
    if isinstance(key, Ed25519PublicKey):
        return key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("a separately pinned 32-byte Ed25519 public key is required")
    return key


def _bound_signer(record: Mapping[str, Any], principal: str, key_id: str) -> bool:
    signer = record.get("signer")
    signature = record.get("signature")
    return (
        isinstance(signer, Mapping)
        and signer.get("principal_id") == principal
        and isinstance(signature, Mapping)
        and signature.get("key_id") == key_id
    )


def assess_reliance(
    authorization: Mapping[str, Any],
    observation: Mapping[str, Any] | None,
    *,
    authority_key: Ed25519PublicKey | bytes,
    observer_key: Ed25519PublicKey | bytes,
    authority_principal: str,
    authority_key_id: str,
    observer_principal: str,
    observer_key_id: str,
    expected_effect: Mapping[str, Any],
    expected_provider: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assess a *recorded* action outcome with buyer-supplied trust anchors.

    No caller-supplied 'verified' flags are honored. Key identity, signer
    identity, exact effect, source, expiration and the receipt binding are
    tested here. ACCEPT means only that the separately pinned signers
    issued consistent records claiming the specified outcome.
    """
    reasons: list[str] = []

    def refuse(reason: str, verdict: str = "REFUSE") -> dict[str, Any]:
        return {
            "verdict": verdict,
            "accepted": False,
            "reasons": [reason],
            "limits": [
                "Provider truth depends on the trustworthiness of the pinned observer.",
                "No independent log registration, custody, or physical outcome is proven.",
                "No provider-side execution prevention or single-use enforcement occurs here.",
            ],
        }

    if not isinstance(authorization, Mapping) or (
        observation is not None and not isinstance(observation, Mapping)
    ):
        return refuse("invalid_record_type")
    if not all(isinstance(x, str) and x for x in (
        authority_principal, authority_key_id, observer_principal,
        observer_key_id, expected_provider
    )):
        return refuse("missing_relying_party_trust_context")
    if not isinstance(expected_effect, Mapping) or not expected_effect:
        return refuse("missing_expected_effect")
    try:
        a_key = _public_bytes(authority_key)
        o_key = _public_bytes(observer_key)
    except ValueError:
        return refuse("untrusted_key_material")
    if a_key == o_key or authority_principal == observer_principal:
        return refuse("separate_signers_required")
    if authorization.get("kind") != AUTH_KIND:
        return refuse("unrecognized_authorization_kind")
    if not _bound_signer(authorization, authority_principal, authority_key_id):
        return refuse("unexpected_authorization_signer")
    try:
        verify_signature(authorization, a_key)
    except (ProofRailError, TypeError, ValueError):
        return refuse("invalid_authorization_signature")
    if authorization.get("decision") != "allow":
        return refuse("authorization_not_allowed")
    effect = authorization.get("effect")
    if not isinstance(effect, Mapping) or dict(effect) != dict(expected_effect):
        return refuse("authorization_effect_mismatch")
    try:
        issued = _time(authorization.get("issued_at"))
        expiry = _time(authorization.get("expires_at"))
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            return refuse("naive_verifier_clock")
        clock = clock.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return refuse("invalid_authorization_time")
    if expiry <= issued or issued > clock or expiry <= clock:
        return refuse("authorization_not_current")

    if observation is None:
        return refuse("provider_observation_missing", "INSUFFICIENT_EVIDENCE")
    if observation.get("kind") != OBS_KIND:
        return refuse("unrecognized_observation_kind")
    if not _bound_signer(observation, observer_principal, observer_key_id):
        return refuse("unexpected_observer_signer")
    try:
        verify_signature(observation, o_key)
    except (ProofRailError, TypeError, ValueError):
        return refuse("invalid_observation_signature")
    if observation.get("authorization_hash") != authorization.get("record_hash"):
        return refuse("observation_authorization_hash_mismatch")
    if observation.get("effect") != dict(expected_effect):
        return refuse("observation_effect_mismatch")
    if observation.get("provider") != expected_provider:
        return refuse("unexpected_provider")
    event_id = observation.get("provider_event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        return refuse("missing_provider_event_id")
    try:
        observed = _time(observation.get("observed_at"))
    except (ValueError, TypeError, OverflowError):
        return refuse("invalid_observation_time")
    if observed < issued or observed > clock:
        return refuse("observation_outside_observed_interval")
    outcome = observation.get("outcome")
    if outcome not in OUTCOMES:
        return refuse("invalid_observed_outcome")
    if outcome != "applied":
        return refuse("outcome_not_confirmed", "INSUFFICIENT_EVIDENCE")

    return {
        "verdict": "ACCEPT_RECORDED_OUTCOME",
        "accepted": True,
        "reasons": reasons,
        "authorization_hash": authorization["record_hash"],
        "observation_hash": observation["record_hash"],
        "provider_event_id": event_id,
        "effect": dict(expected_effect),
        "limits": [
            "Signatures and bindings were checked against externally supplied public keys.",
            "Only the observer's signed claim of the provider outcome was checked.",
            "Independent operator custody, log non-equivocation, and actual provider state were not established.",
            "Acceptance is not permission to execute, retry, pay, or deploy.",
        ],
    }

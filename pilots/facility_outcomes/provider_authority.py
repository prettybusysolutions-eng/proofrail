"""Provider-owned validation of scoped work-order authority (opt-in simulator mode).

Provider trust comes from an operator-supplied key roster OUTSIDE the request.
Neither header identity nor a gateway's receipt authenticates itself.
"""
from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

from proofrail.crypto import verify_signature
from proofrail.envelope import verify_action_authority_envelope
from records import decode_public

ACTION_TYPE = "facility.create_work_order"


class ProviderAuthorityError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _unpack_header(header):
    if not isinstance(header, str) or len(header) > 32000:
        raise ProviderAuthorityError("authority_header_missing_or_oversized")
    try:
        raw = base64.b64decode(header, validate=True)
        if len(raw) > 20000:
            raise ValueError("oversized")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise ProviderAuthorityError("authority_header_invalid") from None


def authorize_create(tenant: str, key: str, body: dict, headers, trusted: dict, now=None):
    """Validate exact effect, pinned issuer and gateway, committed-row attestation.

    This validates the gateway's cryptographic assertion of consumption, not an
    independently anchored replay registry. Provider DB idempotency remains
    authoritative for duplicate HTTP requests.
    """
    envelope = _unpack_header(headers.get("X-ProofRail-Envelope"))
    receipt = _unpack_header(headers.get("X-ProofRail-Consumption"))
    issuer = envelope.get("issuer")
    subject = envelope.get("subject")
    if not isinstance(issuer, dict) or not isinstance(subject, dict):
        raise ProviderAuthorityError("authority_principal_invalid")

    issuer_id = issuer.get("principal_id")
    gateway_id = subject.get("principal_id")
    trusted_issuer = trusted.get("issuers", {}).get(issuer_id)
    trusted_gateway = trusted.get("gateways", {}).get(gateway_id)
    if not isinstance(trusted_issuer, dict) or not isinstance(trusted_gateway, dict):
        raise ProviderAuthorityError("authority_untrusted_principal")
    if trusted_issuer.get("tenant_id") != tenant or trusted_gateway.get("tenant_id") != tenant:
        raise ProviderAuthorityError("authority_tenant_mismatch")
    if body.get("tenant_id", tenant) != tenant:
        raise ProviderAuthorityError("authority_tenant_mismatch")
    if envelope.get("record_hash") != key:
        raise ProviderAuthorityError("authority_idempotency_mismatch")
    effect = envelope.get("effect", {})
    params = effect.get("parameters")
    if not isinstance(params, dict) or params != {**body, "tenant_id": tenant}:
        raise ProviderAuthorityError("authority_effect_mismatch")
    if effect.get("action_type") != ACTION_TYPE:
        raise ProviderAuthorityError("authority_action_mismatch")
    expected_target = "workorder:%s:%s:%s:%s" % (
        body["provider_id"], tenant, body["facility_id"], body["area_id"])
    if effect.get("target") != expected_target:
        raise ProviderAuthorityError("authority_target_mismatch")

    roots = envelope.get("roots")
    if not isinstance(roots, dict):
        raise ProviderAuthorityError("authority_roots_missing")
    try:
        verify_action_authority_envelope(
            envelope,
            public_key=decode_public(trusted_issuer["public_key"]),
            expected_roots=roots,
            expected_approval_digest=envelope["approval_digest"],
            action_type=ACTION_TYPE,
            target=expected_target,
            parameters=params,
            now=now or datetime.now(timezone.utc),
        )
        if (issuer != {"principal_id": issuer_id, "role": "verifier"}
            or subject != {"principal_id": gateway_id, "role": "executor"}
            or envelope.get("signature", {}).get("key_id") != trusted_issuer["key_id"]):
            raise ValueError("issuer, gateway or key binding mismatched")
        issued = datetime.fromisoformat(envelope["issued_at"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(envelope["expires_at"].replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if (issued.tzinfo is None or expiry.tzinfo is None
            or issued > current or expiry <= issued):
            raise ValueError("authority outside valid time window")
    except Exception:
        raise ProviderAuthorityError("authority_envelope_invalid") from None

    if not isinstance(receipt.get("signature"), dict):
        raise ProviderAuthorityError("consumption_receipt_invalid")
    if receipt["signature"].get("key_id") != trusted_gateway.get("key_id"):
        raise ProviderAuthorityError("consumption_gateway_key_untrusted")
    if (receipt.get("kind") != "wrn.consumption-attestation.v1"
        or receipt.get("tenant_id") != tenant
        or receipt.get("envelope_digest") != key
        or receipt.get("nonce") != envelope.get("nonce")
        or receipt.get("executor_principal") != gateway_id
        or not isinstance(receipt.get("registry_claim_digest"), str)
        or len(receipt["registry_claim_digest"]) != 64
        or not isinstance(receipt.get("consumed_at"), str)):
        raise ProviderAuthorityError("consumption_receipt_scope_mismatch")
    try:
        verify_signature(receipt, decode_public(trusted_gateway["public_key"]))
    except Exception:
        raise ProviderAuthorityError("consumption_receipt_signature_invalid") from None
    return True

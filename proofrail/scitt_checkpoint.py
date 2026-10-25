"""Offline COSE_Sign1 SCITT-shaped ProofRail checkpoint statement prototype.

RFC 9943 signed-statement headers: COSE alg (-8 EdDSA), content type, kid,
and protected CWT iss/sub. This only authenticates issuer assertions. It is
NOT a SCITT transparency receipt, inclusion proof, or registration client.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .checkpoint import verify_checkpoint
from .core import ProofRailError
from .crypto import canonical_json, hash_record

COSE_TAG_SIGN1 = 18
COSE_ALG_EDDSA = -8
CONTENT_TYPE = "application/vnd.proofrail.checkpoint+json"
KIND = "proofrail.scitt-checkpoint-statement.v0"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def checkpoint_claim(
    checkpoint: Mapping[str, Any],
    *,
    authority_digest: str,
    consumption_digest: str,
    reconciliation_digest: str,
    previous_checkpoint_digest: str,
    sequence: int,
    domain: str,
) -> dict[str, Any]:
    """Commit to authority and provider evidence without claiming correctness."""
    for name, value in (
        ("authority_digest", authority_digest),
        ("consumption_digest", consumption_digest),
        ("reconciliation_digest", reconciliation_digest),
    ):
        if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
            raise ProofRailError(f"{name}_invalid")
    if previous_checkpoint_digest != "GENESIS" and (
        not isinstance(previous_checkpoint_digest, str)
        or _HEX64.fullmatch(previous_checkpoint_digest) is None
    ):
        raise ProofRailError("previous_checkpoint_digest_invalid")
    if type(sequence) is not int or sequence < 1:
        raise ProofRailError("checkpoint_sequence_invalid")
    if (sequence == 1) != (previous_checkpoint_digest == "GENESIS"):
        raise ProofRailError("checkpoint_lineage_invalid")
    if not isinstance(domain, str) or not domain.strip():
        raise ProofRailError("execution_domain_invalid")
    if not isinstance(checkpoint, Mapping):
        raise ProofRailError("checkpoint_invalid")
    return {
        "kind": KIND,
        "checkpoint_digest": hash_record(checkpoint),
        "authority_digest": authority_digest,
        "consumption_digest": consumption_digest,
        "reconciliation_digest": reconciliation_digest,
        "previous_checkpoint_digest": previous_checkpoint_digest,
        "sequence": sequence,
        "execution_domain": domain,
    }


def sign_scitt_checkpoint_statement(
    claim: Mapping[str, Any],
    *,
    issuer: str,
    subject: str,
    key_id: bytes,
    private_key: Ed25519PrivateKey,
) -> bytes:
    """Emit tagged COSE_Sign1 with embedded canonical JSON payload."""
    if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
        raise ProofRailError("issuer_or_subject_missing")
    if not isinstance(key_id, bytes) or not key_id or len(key_id) > 128:
        raise ProofRailError("key_id_invalid")
    _validate_claim_shape(claim)
    protected = cbor2.dumps({
        1: COSE_ALG_EDDSA, 3: CONTENT_TYPE, 4: key_id, 15: {1: issuer, 2: subject},
    }, canonical=True)
    payload = canonical_json(dict(claim))
    sig_structure = cbor2.dumps(["Signature1", protected, b"", payload], canonical=True)
    signature = private_key.sign(sig_structure)
    return cbor2.dumps(cbor2.CBORTag(COSE_TAG_SIGN1, [protected, {}, payload, signature]), canonical=True)


def verify_scitt_checkpoint_statement(
    encoded: bytes,
    *,
    issuer_public_key: Ed25519PublicKey,
    expected_issuer: str,
    expected_subject: str,
    expected_key_id: bytes,
    expected_claim: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    checkpoint_public_key: Ed25519PublicKey,
    ledger_path: str,
) -> dict[str, Any]:
    """Validate COSE signature, exact independent context and signed ledger.

    This is an offline Issuer Signed Statement verification only. Caller pins
    issuer key, identifiers, full expected claim, and checkpoint key *outside*
    the statement. A SCITT Receipt requires a separate transparency service.
    """
    reasons = []
    try:
        if not isinstance(encoded, bytes) or len(encoded) > 1_000_000:
            raise ProofRailError("cose_size_invalid")
        sign1 = cbor2.loads(encoded)
        if not isinstance(sign1, cbor2.CBORTag) or sign1.tag != COSE_TAG_SIGN1:
            raise ProofRailError("cose_tag_invalid")
        items = sign1.value
        if not isinstance(items, list) or len(items) != 4:
            raise ProofRailError("cose_shape_invalid")
        protected, unprotected, payload, signature = items
        if (not isinstance(protected, bytes) or not protected
            or not isinstance(unprotected, dict) or unprotected
            or not isinstance(payload, bytes) or not isinstance(signature, bytes)):
            raise ProofRailError("cose_components_invalid")
        headers = cbor2.loads(protected)
        if not isinstance(headers, dict) or set(headers) != {1, 3, 4, 15}:
            raise ProofRailError("protected_headers_invalid")
        if (headers[1] != COSE_ALG_EDDSA or headers[3] != CONTENT_TYPE
            or headers[4] != expected_key_id or headers[15] != {1: expected_issuer, 2: expected_subject}):
            raise ProofRailError("issuer_header_mismatch")
        import json
        decoded = json.loads(payload)
        _validate_claim_shape(decoded)
        if canonical_json(decoded) != payload:
            raise ProofRailError("payload_not_canonical")
        if dict(decoded) != dict(expected_claim):
            raise ProofRailError("claim_context_mismatch")
        sig_structure = cbor2.dumps(["Signature1", protected, b"", payload], canonical=True)
        try:
            issuer_public_key.verify(signature, sig_structure)
        except InvalidSignature as exc:
            raise ProofRailError("issuer_signature_invalid") from exc
        if decoded["checkpoint_digest"] != hash_record(checkpoint):
            raise ProofRailError("checkpoint_digest_mismatch")
        checked = verify_checkpoint(checkpoint, ledger_path, public_key=checkpoint_public_key)
        if not checked["valid"]:
            raise ProofRailError("checkpoint_or_ledger_invalid")
    except (ProofRailError, ValueError, TypeError, KeyError, cbor2.CBORDecodeError, cbor2.CBORDecodeValueError) as exc:
        reasons.append(str(exc) if isinstance(exc, ProofRailError) else "malformed_statement")
    return {
        "valid": not reasons,
        "issuer_signed_statement_verified": not reasons,
        "transparency_receipt_verified": False,
        "externally_retained_history_proven": False,
        "external_effect_proven": False,
        "errors": reasons,
    }


def _validate_claim_shape(claim: Mapping[str, Any]) -> None:
    required = {
        "kind", "checkpoint_digest", "authority_digest", "consumption_digest",
        "reconciliation_digest", "previous_checkpoint_digest", "sequence", "execution_domain",
    }
    if not isinstance(claim, Mapping) or set(claim) != required or claim.get("kind") != KIND:
        raise ProofRailError("claim_shape_invalid")
    for key in ("checkpoint_digest", "authority_digest", "consumption_digest", "reconciliation_digest"):
        value = claim.get(key)
        if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
            raise ProofRailError(f"{key}_invalid")
    previous = claim.get("previous_checkpoint_digest")
    seq = claim.get("sequence")
    if type(seq) is not int or seq < 1:
        raise ProofRailError("checkpoint_sequence_invalid")
    if (seq == 1) != (previous == "GENESIS"):
        raise ProofRailError("checkpoint_lineage_invalid")
    if previous != "GENESIS" and (not isinstance(previous, str) or _HEX64.fullmatch(previous) is None):
        raise ProofRailError("previous_checkpoint_digest_invalid")
    if not isinstance(claim.get("execution_domain"), str) or not claim["execution_domain"].strip():
        raise ProofRailError("execution_domain_invalid")

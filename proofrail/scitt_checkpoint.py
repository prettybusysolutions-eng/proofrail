"""Offline COSE_Sign1 SCITT-shaped ProofRail checkpoint statement prototype.

RFC 9943 signed-statement headers: COSE alg (-19 Ed25519), content type, kid,
and protected CWT iss/sub. This only authenticates issuer assertions. It is
NOT a SCITT transparency receipt, inclusion proof, or registration client.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .checkpoint import verify_checkpoint
from .core import ProofRailError
from .crypto import canonical_json, hash_record

COSE_TAG_SIGN1 = 18
COSE_ALG_ED25519 = -19  # RFC 9864, fully specified and recommended
COSE_ALG_EDDSA_LEGACY = -8  # Deprecated; verify only as a migration option
COSE_RECEIPTS_HEADER = 394  # RFC 9942; not covered by the issuer signature
MAX_RECEIPTS = 16
MAX_RECEIPT_BYTES = 65536
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
    algorithm: int = COSE_ALG_ED25519,
) -> bytes:
    """Emit tagged COSE_Sign1 with embedded canonical JSON payload."""
    if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
        raise ProofRailError("issuer_or_subject_missing")
    if not isinstance(key_id, bytes) or not key_id or len(key_id) > 128:
        raise ProofRailError("key_id_invalid")
    _validate_claim_shape(claim)
    if type(algorithm) is not int or algorithm not in (COSE_ALG_ED25519, COSE_ALG_EDDSA_LEGACY):
        raise ProofRailError("signing_algorithm_unsupported")
    protected = cbor2.dumps({
        1: algorithm, 3: CONTENT_TYPE, 4: key_id, 15: {1: issuer, 2: subject},
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
    allow_legacy_eddsa: bool = True,
    pinned_latest: Mapping[str, Any] | None = None,
    require_transparency_receipt: bool = False,
) -> dict[str, Any]:
    """Verify *issuer* signature, exact claim, checkpoint and optional tip pin.

    RFC 9942 receipts in unprotected header 394 may be parsed but are NOT
    cryptographically verified by this routine. A true transparency verifier
    must validate receipt signatures, VDS/VDP inclusion proofs, and freshness
    against a trusted transparency service or independently authenticated
    monitor. A separately supplied tip only checks equality with a caller's
    expected tip; it cannot authenticate that the tip is actually current.
    """
    reasons: list[str] = []
    receipts: tuple[bytes, ...] = ()
    algorithm: int | None = None
    issuer_verified = False
    tip_matched = False
    try:
        if type(encoded) is not bytes or len(encoded) > 1_000_000:
            raise ProofRailError("cose_size_invalid")
        sign1 = cbor2.loads(encoded)
        if not isinstance(sign1, cbor2.CBORTag) or sign1.tag != COSE_TAG_SIGN1:
            raise ProofRailError("cose_tag_invalid")
        items = sign1.value
        if not isinstance(items, (list, tuple)) or len(items) != 4:
            raise ProofRailError("cose_shape_invalid")
        protected, unprotected, payload, signature = items
        if (type(protected) is not bytes or not protected
            or not isinstance(unprotected, Mapping)
            or type(payload) is not bytes
            or type(signature) is not bytes or len(signature) != 64):
            raise ProofRailError("cose_components_invalid")

        # An unprotected receipt is *not* authenticated by the issuer
        # signature. Accept only its registered header and basic RFC 9942
        # structure, and never promote it into a verified transparency claim.
        receipts = _parse_unverified_receipts(unprotected)

        headers = cbor2.loads(protected)
        if not isinstance(headers, Mapping) or set(headers) != {1, 3, 4, 15}:
            raise ProofRailError("protected_headers_invalid")
        algorithm = headers[1]
        if (type(algorithm) is not int
            or algorithm not in (COSE_ALG_ED25519, COSE_ALG_EDDSA_LEGACY)):
            raise ProofRailError("issuer_algorithm_unsupported")
        if algorithm == COSE_ALG_EDDSA_LEGACY and not allow_legacy_eddsa:
            raise ProofRailError("legacy_algorithm_disallowed")
        if (headers[3] != CONTENT_TYPE
            or headers[4] != expected_key_id
            or headers[15] != {1: expected_issuer, 2: expected_subject}):
            raise ProofRailError("issuer_header_mismatch")
        import json
        decoded = json.loads(payload)
        _validate_claim_shape(decoded)
        _validate_claim_shape(expected_claim)
        if canonical_json(decoded) != payload:
            raise ProofRailError("payload_not_canonical")
        if dict(decoded) != dict(expected_claim):
            raise ProofRailError("claim_context_mismatch")
        sig_structure = cbor2.dumps(
            ["Signature1", protected, b"", payload], canonical=True
        )
        try:
            issuer_public_key.verify(signature, sig_structure)
        except InvalidSignature as exc:
            raise ProofRailError("issuer_signature_invalid") from exc
        issuer_verified = True

        if decoded["checkpoint_digest"] != hash_record(checkpoint):
            raise ProofRailError("checkpoint_digest_mismatch")
        checked = verify_checkpoint(
            checkpoint, ledger_path, public_key=checkpoint_public_key
        )
        if not checked["valid"]:
            raise ProofRailError("checkpoint_or_ledger_invalid")

        if pinned_latest is not None:
            _verify_pinned_tip(
                decoded, pinned_latest, expected_issuer=expected_issuer,
                expected_subject=expected_subject,
            )
            tip_matched = True
        if require_transparency_receipt:
            # Parsing a receipt is not inclusion-proof or log-key verification.
            # Fail closed until an actual RFC 9942 VDS/VDP verifier is wired.
            raise ProofRailError("transparency_receipt_verification_unavailable")
    except (ProofRailError, ValueError, TypeError, KeyError, RecursionError,
            cbor2.CBORDecodeError) as exc:
        reasons.append(
            str(exc) if isinstance(exc, ProofRailError) else "malformed_statement"
        )
    return {
        "valid": not reasons,
        "issuer_signed_statement_verified": issuer_verified,
        "issuer_algorithm": algorithm,
        "legacy_algorithm": algorithm == COSE_ALG_EDDSA_LEGACY,
        "attached_receipts_count": len(receipts),
        "attached_receipts_structurally_accepted": bool(receipts),
        "transparency_receipt_verified": False,
        "pinned_latest_matched": tip_matched,
        "externally_verified_latest_log_state_proven": False,
        "externally_retained_history_proven": False,
        "external_effect_proven": False,
        "errors": reasons,
    }


def _parse_unverified_receipts(unprotected: Mapping[Any, Any]) -> tuple[bytes, ...]:
    """Reject arbitrary unsigned headers; validate but do not trust receipts."""
    if not unprotected:
        return ()
    if set(unprotected) != {COSE_RECEIPTS_HEADER}:
        raise ProofRailError("unprotected_headers_unsupported")
    value = unprotected[COSE_RECEIPTS_HEADER]
    if (not isinstance(value, (list, tuple))
        or not 1 <= len(value) <= MAX_RECEIPTS):
        raise ProofRailError("receipts_array_invalid")
    result = []
    for item in value:
        if (type(item) is not bytes
            or not 1 <= len(item) <= MAX_RECEIPT_BYTES):
            raise ProofRailError("receipt_bytes_invalid")
        try:
            decoded = cbor2.loads(item)
        except (ValueError, TypeError, RecursionError, cbor2.CBORDecodeError) as exc:
            raise ProofRailError("receipt_cbor_invalid") from exc
        if (not isinstance(decoded, cbor2.CBORTag)
            or decoded.tag != COSE_TAG_SIGN1
            or not isinstance(decoded.value, (list, tuple))
            or len(decoded.value) != 4):
            raise ProofRailError("receipt_cose_shape_invalid")
        p, u, body, sig = decoded.value
        if (type(p) is not bytes or not p
            or not isinstance(u, Mapping)
            or body is not None and type(body) is not bytes
            or type(sig) is not bytes or not sig):
            raise ProofRailError("receipt_cose_components_invalid")
        result.append(item)
    return tuple(result)


def _verify_pinned_tip(
    claim: Mapping[str, Any],
    pinned_latest: Mapping[str, Any],
    *,
    expected_issuer: str,
    expected_subject: str,
) -> None:
    """Compare with an externally authenticated tip, not a bundle's own tip.

    This function cannot prove that the caller checked service consistency or
    obtained the true latest entry. That proof is a distinct integration gate.
    """
    required = {"issuer", "subject", "execution_domain", "sequence",
                "checkpoint_digest"}
    if not isinstance(pinned_latest, Mapping) or set(pinned_latest) != required:
        raise ProofRailError("pinned_latest_shape_invalid")
    if (pinned_latest["issuer"] != expected_issuer
        or pinned_latest["subject"] != expected_subject
        or pinned_latest["execution_domain"] != claim["execution_domain"]):
        raise ProofRailError("pinned_latest_scope_mismatch")
    if (type(pinned_latest["sequence"]) is not int
        or pinned_latest["sequence"] < 1):
        raise ProofRailError("pinned_latest_sequence_invalid")
    if (type(pinned_latest["checkpoint_digest"]) is not str
        or _HEX64.fullmatch(pinned_latest["checkpoint_digest"]) is None):
        raise ProofRailError("pinned_latest_digest_invalid")
    if claim["sequence"] != pinned_latest["sequence"]:
        raise ProofRailError("pinned_latest_sequence_mismatch")
    if claim["checkpoint_digest"] != pinned_latest["checkpoint_digest"]:
        raise ProofRailError("pinned_latest_checkpoint_digest_mismatch")


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

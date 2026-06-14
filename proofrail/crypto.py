from __future__ import annotations

import base64
import copy
import hashlib
from collections.abc import Mapping
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import ProofRailError


def canonical_json(record: Any) -> bytes:
    """Return RFC 8785 canonical JSON bytes for a JSON-compatible value."""
    try:
        return rfc8785.dumps(record)
    except (rfc8785.CanonicalizationError, rfc8785.FloatDomainError) as exc:
        raise ProofRailError(f"Record is not canonically serializable: {exc}") from exc


def hash_record(record: Mapping[str, Any]) -> str:
    """Hash record content without its derived hash or signature fields."""
    unsigned = _without_fields(record, {"record_hash", "signature"})
    return hashlib.sha256(canonical_json(unsigned)).hexdigest()


def sign_record(
    record: Mapping[str, Any],
    private_key: Ed25519PrivateKey | bytes,
    *,
    key_id: str,
) -> dict[str, Any]:
    """Return a copy with a content hash and detached Ed25519 signature."""
    if not key_id.strip():
        raise ProofRailError("key_id is required")
    signed = copy.deepcopy(dict(record))
    signed.pop("signature", None)
    signed["record_hash"] = hash_record(signed)
    signature = _private_key(private_key).sign(canonical_json(signed))
    signed["signature"] = {
        "algorithm": "ed25519",
        "key_id": key_id,
        "value": _encode(signature),
    }
    return signed


def verify_signature(
    record: Mapping[str, Any],
    public_key: Ed25519PublicKey | bytes,
) -> bool:
    """Verify both the content hash and Ed25519 signature."""
    signature = record.get("signature")
    if not isinstance(signature, Mapping):
        raise ProofRailError("Record signature is missing")
    if signature.get("algorithm") != "ed25519":
        raise ProofRailError("Unsupported signature algorithm")
    recorded_hash = record.get("record_hash")
    if not isinstance(recorded_hash, str) or recorded_hash != hash_record(record):
        raise ProofRailError("Record hash mismatch")
    value = signature.get("value")
    if not isinstance(value, str):
        raise ProofRailError("Signature value is missing")
    unsigned = _without_fields(record, {"signature"})
    try:
        _public_key(public_key).verify(_decode(value), canonical_json(unsigned))
    except (InvalidSignature, ValueError) as exc:
        raise ProofRailError("Record signature verification failed") from exc
    return True


def _without_fields(record: Mapping[str, Any], fields: set[str]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in record.items()
        if key not in fields
    }


def _private_key(value: Ed25519PrivateKey | bytes) -> Ed25519PrivateKey:
    if isinstance(value, Ed25519PrivateKey):
        return value
    if isinstance(value, bytes):
        try:
            return Ed25519PrivateKey.from_private_bytes(value)
        except ValueError as exc:
            raise ProofRailError("Invalid Ed25519 private key") from exc
    raise ProofRailError("Unsupported Ed25519 private key type")


def _public_key(value: Ed25519PublicKey | bytes) -> Ed25519PublicKey:
    if isinstance(value, Ed25519PublicKey):
        return value
    if isinstance(value, bytes):
        try:
            return Ed25519PublicKey.from_public_bytes(value)
        except ValueError as exc:
            raise ProofRailError("Invalid Ed25519 public key") from exc
    raise ProofRailError("Unsupported Ed25519 public key type")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

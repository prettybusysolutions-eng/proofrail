from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .checkpoint import read_ledger, verify_ledger
from .core import ProofRailError
from .crypto import sign_record, verify_signature


def create_anchor(
    ledger_path: str | Path,
    *,
    trust_checkpoint_hash: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    anchor_provider: str,
    anchor_reference: str,
    trust_checkpoint_present: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Sign an externally retainable commitment to one exact ledger state."""
    verification = verify_ledger(ledger_path)
    if not verification["valid"]:
        raise ProofRailError(
            "Cannot anchor invalid ledger: " + ", ".join(verification["errors"])
        )
    _require_digest(trust_checkpoint_hash, "trust_checkpoint_hash")
    if not anchor_provider.strip() or not anchor_reference.strip():
        raise ProofRailError("Anchor provider and reference are required")
    records = read_ledger(ledger_path)
    sequences = [
        record.get("sequence")
        for record in records
        if isinstance(record.get("sequence"), int)
    ]
    sequence_range = {
        "start": min(sequences) if sequences else (1 if records else 0),
        "end": max(sequences) if sequences else len(records),
        "entry_count": len(records),
    }
    record = {
        "kind": "proofrail.external-anchor.v0.5.2",
        "created_at": _format_time(now),
        "anchor_provider": anchor_provider,
        "anchor_reference": anchor_reference,
        "ledger_merkle_root": verification["merkle_root"],
        "ledger_first_hash": verification["first_hash"],
        "ledger_last_hash": verification["last_hash"],
        "trust_checkpoint_hash": trust_checkpoint_hash,
        "trust_checkpoint_present": trust_checkpoint_present,
        "sequence_range": sequence_range,
    }
    signed = sign_record(record, private_key, key_id=key_id)
    signed["anchor_signature"] = signed.pop("signature")
    return signed


def verify_anchor(
    anchor: Mapping[str, Any],
    ledger_path: str | Path,
    *,
    public_key: Ed25519PublicKey | bytes,
    expected_trust_checkpoint_hash: str | None = None,
) -> dict[str, Any]:
    """Verify anchor authorship and exact ledger continuity."""
    errors: list[str] = []
    signed = dict(anchor)
    signature = signed.pop("anchor_signature", None)
    signed["signature"] = signature
    try:
        verify_signature(signed, public_key)
    except ProofRailError as exc:
        errors.append(f"invalid_anchor_signature:{exc}")
    if anchor.get("kind") != "proofrail.external-anchor.v0.5.2":
        errors.append("invalid_anchor_kind")
    if expected_trust_checkpoint_hash is not None:
        if anchor.get("trust_checkpoint_hash") != expected_trust_checkpoint_hash:
            errors.append("anchor_trust_checkpoint_hash_mismatch")
        if anchor.get("trust_checkpoint_present") is not True:
            errors.append("anchor_trust_checkpoint_missing")

    ledger = verify_ledger(ledger_path)
    if not ledger["valid"]:
        errors.extend(f"ledger:{error}" for error in ledger["errors"])
    comparisons = {
        "ledger_merkle_root": ledger.get("merkle_root"),
        "ledger_first_hash": ledger.get("first_hash"),
        "ledger_last_hash": ledger.get("last_hash"),
    }
    for field, observed in comparisons.items():
        if anchor.get(field) != observed:
            errors.append(f"anchor_{field}_mismatch")
    sequence_range = anchor.get("sequence_range")
    if not isinstance(sequence_range, Mapping):
        errors.append("anchor_sequence_range_missing")
    else:
        if sequence_range.get("entry_count") != ledger["entries"]:
            errors.append("anchor_sequence_entry_count_mismatch")
        records = read_ledger(ledger_path) if ledger["valid"] else []
        sequences = [
            record.get("sequence")
            for record in records
            if isinstance(record.get("sequence"), int)
        ]
        expected_start = min(sequences) if sequences else (1 if records else 0)
        expected_end = max(sequences) if sequences else len(records)
        if sequence_range.get("start") != expected_start:
            errors.append("anchor_sequence_start_mismatch")
        if sequence_range.get("end") != expected_end:
            errors.append("anchor_sequence_end_mismatch")
    return {
        "valid": not errors,
        "entries": ledger["entries"],
        "ledger_merkle_root": ledger.get("merkle_root"),
        "trust_checkpoint_hash": anchor.get("trust_checkpoint_hash"),
        "trust_checkpoint_present": anchor.get("trust_checkpoint_present"),
        "anchor_provider": anchor.get("anchor_provider"),
        "anchor_reference": anchor.get("anchor_reference"),
        "errors": errors,
    }


def encode_public_key(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_public_key(value: str) -> Ed25519PublicKey:
    try:
        raw = base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise ProofRailError("Invalid encoded Ed25519 public key") from exc


def resolve_file_anchor_public_key(
    anchor: Mapping[str, Any],
    *,
    anchor_path: str | Path,
) -> Ed25519PublicKey:
    if anchor.get("anchor_provider") != "local-file":
        raise ProofRailError("Only local-file anchors are supported in v0.5.2")
    reference = anchor.get("anchor_reference")
    if not isinstance(reference, str) or not reference.startswith("file:"):
        raise ProofRailError("Local-file anchor reference must start with file:")
    relative = reference.removeprefix("file:")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ProofRailError("Local-file anchor reference must be a safe relative path")
    key_path = Path(anchor_path).resolve().parent / relative
    if key_path.is_symlink() or not key_path.is_file():
        raise ProofRailError("Anchor public key reference must be a regular file")
    return decode_public_key(key_path.read_text(encoding="utf-8"))


def _format_time(value: datetime | None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ProofRailError("Anchor timestamp must include a timezone")
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_digest(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ProofRailError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProofRailError(f"{name} must be hexadecimal") from exc

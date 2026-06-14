from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import ProofRailError, digest_ledger_entry
from .crypto import canonical_json, hash_record, sign_record, verify_signature


def merkle_root(records: Sequence[Mapping[str, Any]]) -> str:
    """Return a domain-separated SHA-256 Merkle root over canonical records."""
    if not records:
        return hashlib.sha256(b"").hexdigest()
    level = [
        hashlib.sha256(b"\x00" + canonical_json(record)).digest()
        for record in records
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"\x01" + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()


def read_ledger(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProofRailError(f"line_{line_number}:invalid_json") from exc
            if not isinstance(record, dict):
                raise ProofRailError(f"line_{line_number}:not_an_object")
            records.append(record)
    return records


def verify_ledger(path: str | Path) -> dict[str, Any]:
    """Verify portable v1 ledger entries and v0.2 signed-record hash links."""
    try:
        records = read_ledger(path)
    except (OSError, ProofRailError) as exc:
        return {
            "valid": False,
            "entries": 0,
            "merkle_root": None,
            "errors": [str(exc)],
        }

    errors: list[str] = []
    previous_hash: str | None = None
    for index, record in enumerate(records, start=1):
        claimed_hash = _claimed_hash(record)
        if "entry_hash" in record:
            if claimed_hash != digest_ledger_entry(record):
                errors.append(f"line_{index}:invalid_entry_hash")
            expected_previous = "GENESIS" if previous_hash is None else previous_hash
            if record.get("previous_hash") != expected_previous:
                errors.append(f"line_{index}:broken_previous_hash")
        elif "record_hash" in record:
            if claimed_hash != hash_record(record):
                errors.append(f"line_{index}:invalid_record_hash")
            if "previous_hash" in record:
                expected_previous = None if previous_hash is None else previous_hash
                if record.get("previous_hash") != expected_previous:
                    errors.append(f"line_{index}:broken_previous_hash")
        else:
            errors.append(f"line_{index}:missing_content_hash")
        previous_hash = claimed_hash or previous_hash

    return {
        "valid": not errors,
        "entries": len(records),
        "first_hash": _claimed_hash(records[0]) if records else None,
        "last_hash": _claimed_hash(records[-1]) if records else None,
        "merkle_root": merkle_root(records),
        "errors": errors,
    }


def export_ledger(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Export valid ledgers exactly and wrap unhashed legacy records safely."""
    result = verify_ledger(source)
    records = read_ledger(source)
    legacy = bool(records) and all(_claimed_hash(record) is None for record in records)
    if not result["valid"] and not legacy:
        raise ProofRailError(
            "Refusing to export invalid ledger: " + ", ".join(result["errors"])
        )
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        dir=destination_path.parent,
    )
    os.close(fd)
    try:
        if legacy:
            _write_legacy_envelopes(records, Path(temporary))
        else:
            shutil.copyfile(source_path, temporary)
        os.replace(temporary, destination_path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    exported = verify_ledger(destination_path)
    if not exported["valid"]:
        raise ProofRailError(
            "Export verification failed: " + ", ".join(exported["errors"])
        )
    return {
        **exported,
        "source": str(source_path),
        "output": str(destination_path),
        "legacy_records_wrapped": legacy,
    }


def create_checkpoint(
    ledger_path: str | Path,
    *,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a signed checkpoint over a currently valid ledger."""
    verification = verify_ledger(ledger_path)
    if not verification["valid"]:
        raise ProofRailError(
            "Cannot checkpoint invalid ledger: " + ", ".join(verification["errors"])
        )
    timestamp = _utc(now)
    checkpoint = {
        "kind": "proofrail.merkle-checkpoint.v0.3",
        "checkpoint_id": str(uuid.uuid4()),
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "ledger": {
            "format": "jsonl",
            "entry_count": verification["entries"],
            "first_hash": verification["first_hash"],
            "last_hash": verification["last_hash"],
            "merkle_root": verification["merkle_root"],
            "hash_algorithm": "sha256",
            "tree_algorithm": "proofrail-merkle-v1",
        },
    }
    return sign_record(checkpoint, private_key, key_id=key_id)


def verify_checkpoint(
    checkpoint: Mapping[str, Any],
    ledger_path: str | Path,
    *,
    public_key: Ed25519PublicKey | bytes,
) -> dict[str, Any]:
    """Verify checkpoint authorship and recompute its ledger commitment."""
    errors: list[str] = []
    try:
        verify_signature(checkpoint, public_key)
    except ProofRailError as exc:
        errors.append(f"invalid_checkpoint_signature:{exc}")
    if checkpoint.get("kind") != "proofrail.merkle-checkpoint.v0.3":
        errors.append("invalid_checkpoint_kind")

    ledger_result = verify_ledger(ledger_path)
    if not ledger_result["valid"]:
        errors.extend(f"ledger:{error}" for error in ledger_result["errors"])
    commitment = checkpoint.get("ledger")
    if not isinstance(commitment, Mapping):
        errors.append("checkpoint_commitment_missing")
    else:
        comparisons = {
            "entry_count": ledger_result["entries"],
            "first_hash": ledger_result.get("first_hash"),
            "last_hash": ledger_result.get("last_hash"),
            "merkle_root": ledger_result.get("merkle_root"),
        }
        for field, observed in comparisons.items():
            if commitment.get(field) != observed:
                errors.append(f"checkpoint_{field}_mismatch")

    return {
        "valid": not errors,
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "entries": ledger_result["entries"],
        "merkle_root": ledger_result.get("merkle_root"),
        "errors": errors,
    }


def _claimed_hash(record: Mapping[str, Any]) -> str | None:
    value = record.get("entry_hash", record.get("record_hash"))
    return value if isinstance(value, str) else None


def _write_legacy_envelopes(
    records: Sequence[Mapping[str, Any]],
    destination: Path,
) -> None:
    previous_hash = "GENESIS"
    envelopes = []
    for sequence, record in enumerate(records, start=1):
        envelope = {
            "kind": "proofrail.legacy-ledger-envelope.v0.3",
            "sequence": sequence,
            "source_record_hash": hashlib.sha256(canonical_json(record)).hexdigest(),
            "payload": record,
            "previous_hash": previous_hash,
        }
        envelope["entry_hash"] = digest_ledger_entry(envelope)
        previous_hash = envelope["entry_hash"]
        envelopes.append(envelope)
    destination.write_text(
        "\n".join(
            json.dumps(envelope, sort_keys=True, separators=(",", ":"))
            for envelope in envelopes
        )
        + "\n",
        encoding="utf-8",
    )


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ProofRailError("Checkpoint timestamp must include a timezone")
    return value.astimezone(timezone.utc)

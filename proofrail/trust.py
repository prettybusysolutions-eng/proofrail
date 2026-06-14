from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import ProofRailError
from .crypto import hash_record, sign_record, verify_signature

EMPTY_ROOT = hash_record({"kind": "proofrail.empty-root.v0.5.1"})


def replay_claim_exists(registry_path: str | Path, permit_hash: str) -> bool:
    path = Path(registry_path)
    if not path.exists():
        return False
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT 1 FROM permit_claims WHERE permit_hash = ?",
                (permit_hash,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise ProofRailError("Replay registry is unreadable or corrupt") from exc
    return row is not None


def replay_registry_root(registry_path: str | Path) -> str:
    """Commit to the complete replay-claim state, failing on corrupt storage."""
    path = Path(registry_path)
    if not path.exists():
        claims: list[dict[str, Any]] = []
    else:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                rows = connection.execute(
                    """
                    SELECT permit_hash, nonce, executor_id, executing_at, consumed_at
                    FROM permit_claims ORDER BY permit_hash
                    """
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise ProofRailError("Replay registry is unreadable or corrupt") from exc
        claims = [
            {
                "permit_hash": row[0],
                "nonce": row[1],
                "executor_id": row[2],
                "executing_at": row[3],
                "consumed_at": row[4],
            }
            for row in rows
        ]
    return hash_record(
        {"kind": "proofrail.replay-registry-root.v0.5.1", "claims": claims}
    )


def create_trust_checkpoint(
    *,
    replay_root: str,
    ledger_checkpoint_root: str = EMPTY_ROOT,
    observation_root: str = EMPTY_ROOT,
    epoch: int,
    monotonic_counter: int,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    previous_checkpoint_hash: str | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("replay_root", replay_root),
        ("ledger_checkpoint_root", ledger_checkpoint_root),
        ("observation_root", observation_root),
    ):
        _require_digest(value, name)
    if not isinstance(epoch, int) or epoch < 0:
        raise ProofRailError("checkpoint epoch must be a non-negative integer")
    if not isinstance(monotonic_counter, int) or monotonic_counter < 0:
        raise ProofRailError("monotonic counter must be a non-negative integer")
    if previous_checkpoint_hash is not None:
        _require_digest(previous_checkpoint_hash, "previous_checkpoint_hash")
    roots = {
        "replay": replay_root,
        "ledger_checkpoint": ledger_checkpoint_root,
        "observation": observation_root,
    }
    record = {
        "kind": "proofrail.trust-checkpoint.v0.5.1",
        "epoch": epoch,
        "monotonic_counter": monotonic_counter,
        "roots": roots,
        "trust_root": hash_record(
            {"kind": "proofrail.trust-root.v0.5.1", "roots": roots}
        ),
        "previous_checkpoint_hash": previous_checkpoint_hash,
    }
    return sign_record(record, private_key, key_id=key_id)


def verify_trust_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    registry_path: str | Path,
    public_key: Ed25519PublicKey | bytes,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_signature(checkpoint, public_key)
    except ProofRailError as exc:
        errors.append(f"invalid_checkpoint_signature:{exc}")
    if checkpoint.get("kind") != "proofrail.trust-checkpoint.v0.5.1":
        errors.append("invalid_checkpoint_kind")
    roots = checkpoint.get("roots")
    observed_replay_root = replay_registry_root(registry_path)
    if not isinstance(roots, Mapping):
        errors.append("checkpoint_roots_missing")
    else:
        expected_trust_root = hash_record(
            {"kind": "proofrail.trust-root.v0.5.1", "roots": dict(roots)}
        )
        if checkpoint.get("trust_root") != expected_trust_root:
            errors.append("trust_root_mismatch")
        if roots.get("replay") != observed_replay_root:
            errors.append("replay_root_mismatch")
    return {
        "valid": not errors,
        "epoch": checkpoint.get("epoch"),
        "monotonic_counter": checkpoint.get("monotonic_counter"),
        "replay_root": observed_replay_root,
        "errors": errors,
    }


def next_trust_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    registry_path: str | Path,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    observation_root: str | None = None,
    ledger_checkpoint_root: str | None = None,
) -> dict[str, Any]:
    roots = checkpoint.get("roots")
    if not isinstance(roots, Mapping):
        raise ProofRailError("Trust checkpoint roots are missing")
    return create_trust_checkpoint(
        replay_root=replay_registry_root(registry_path),
        ledger_checkpoint_root=ledger_checkpoint_root or str(roots["ledger_checkpoint"]),
        observation_root=observation_root or str(roots["observation"]),
        epoch=int(checkpoint["epoch"]) + 1,
        monotonic_counter=int(checkpoint["monotonic_counter"]) + 1,
        private_key=private_key,
        key_id=key_id,
        previous_checkpoint_hash=str(checkpoint["record_hash"]),
    )


def write_trust_checkpoint(path: str | Path, checkpoint: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(checkpoint, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_trust_checkpoint(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofRailError("Trust checkpoint is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise ProofRailError("Trust checkpoint must be an object")
    return value


def _require_digest(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ProofRailError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProofRailError(f"{name} must be hexadecimal") from exc

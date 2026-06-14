from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .crypto import hash_record, sign_record, verify_signature
from .permit import PERMIT_ISSUER_ROLES, PermitError
from .trust import replay_claim_exists, replay_registry_root, verify_trust_checkpoint


class DatabaseMigrationAdapterProtocol(Protocol):
    def observe(self, action: dict[str, Any]) -> dict[str, Any]:
        ...

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        ...


def migration_digest(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise PermitError("migration_sql_missing")
    return hash_record(
        {"kind": "proofrail.database-migration-source.v0.6", "sql": sql}
    )


def mint_database_migration_permit(
    *,
    identity_root: str,
    evidence_root: str,
    policy_root: str,
    state_root: str,
    approval_digest: str,
    database_id: str,
    database_instance_fingerprint: str,
    expected_schema_root: str,
    expected_result_schema_root: str,
    migration_sql: str,
    target_version: int,
    nonce: str,
    expires_at: datetime | str,
    issuer_principal_id: str,
    issuer_role: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    now: datetime | None = None,
    constraints: Mapping[str, Any] | None = None,
    trust: Mapping[str, Any] | None = None,
    permit_id: str | None = None,
) -> dict[str, Any]:
    issued_at = _utc(now)
    expiry = _parse_time(expires_at)
    if issuer_role not in PERMIT_ISSUER_ROLES:
        raise PermitError("issuer_role_forbidden")
    if expiry <= issued_at:
        raise PermitError("permit_expired")
    if not isinstance(database_id, str) or not database_id.strip():
        raise PermitError("invalid_database_id")
    if not isinstance(target_version, int) or target_version <= 0:
        raise PermitError("invalid_target_version")
    if not isinstance(nonce, str) or len(nonce) < 16:
        raise PermitError("invalid_nonce")
    for field, value in (
        ("identity_root", identity_root),
        ("evidence_root", evidence_root),
        ("policy_root", policy_root),
        ("state_root", state_root),
        ("approval_digest", approval_digest),
        ("database_instance_fingerprint", database_instance_fingerprint),
        ("expected_schema_root", expected_schema_root),
        ("expected_result_schema_root", expected_result_schema_root),
    ):
        _require_digest(value, field)

    record: dict[str, Any] = {
        "kind": "proofrail.database-migration-permit.v0.6",
        "permit_id": permit_id or str(uuid.uuid4()),
        "state": "PERMITTED",
        "issued_at": _format_time(issued_at),
        "expires_at": _format_time(expiry),
        "nonce": nonce,
        "issuer": {
            "principal_id": issuer_principal_id,
            "role": issuer_role,
        },
        "roots": {
            "identity": identity_root,
            "evidence": evidence_root,
            "policy": policy_root,
            "state": state_root,
        },
        "approval_digest": approval_digest,
        "effect": {
            "action_type": "database_migration",
            "database_id": database_id,
            "database_instance_fingerprint": database_instance_fingerprint,
            "expected_schema_root": expected_schema_root,
            "expected_result_schema_root": expected_result_schema_root,
            "migration_digest": migration_digest(migration_sql),
            "target_version": target_version,
        },
        "constraints": dict(constraints or {}),
    }
    if trust is not None:
        record["trust"] = _validated_trust_constraints(trust)
    return sign_record(record, private_key, key_id=key_id)


def verify_database_migration_permit(
    permit: Mapping[str, Any],
    *,
    public_key: Ed25519PublicKey | bytes,
    expected_identity_root: str,
    expected_evidence_root: str,
    expected_policy_root: str,
    expected_state_root: str,
    expected_approval_digest: str,
    database_id: str,
    database_instance_fingerprint: str,
    current_schema_root: str,
    expected_result_schema_root: str,
    migration_sql: str,
    target_version: int,
    now: datetime | None = None,
    current_checkpoint_epoch: int | None = None,
    current_monotonic_counter: int | None = None,
    expected_replay_root: str | None = None,
    expected_checkpoint_root: str | None = None,
    expected_observation_root: str | None = None,
) -> bool:
    try:
        verify_signature(permit, public_key)
    except Exception as exc:
        raise PermitError("invalid_signature", str(exc)) from exc
    if permit.get("kind") != "proofrail.database-migration-permit.v0.6":
        raise PermitError("invalid_permit_kind")
    if permit.get("state") != "PERMITTED":
        raise PermitError("invalid_permit_state")
    issuer = permit.get("issuer")
    if not isinstance(issuer, Mapping) or issuer.get("role") not in PERMIT_ISSUER_ROLES:
        raise PermitError("issuer_role_forbidden")
    if _utc(now) >= _parse_time(_required_text(permit, "expires_at")):
        raise PermitError("permit_expired")

    roots = permit.get("roots")
    if not isinstance(roots, Mapping):
        raise PermitError("roots_missing")
    for name, expected in (
        ("identity", expected_identity_root),
        ("evidence", expected_evidence_root),
        ("policy", expected_policy_root),
        ("state", expected_state_root),
    ):
        if roots.get(name) != expected:
            raise PermitError(f"{name}_root_changed")
    if permit.get("approval_digest") != expected_approval_digest:
        raise PermitError("approval_scope_changed")

    effect = permit.get("effect")
    if not isinstance(effect, Mapping):
        raise PermitError("effect_missing")
    comparisons = (
        ("action_type", "database_migration", "action_type_changed"),
        ("database_id", database_id, "database_changed"),
        (
            "database_instance_fingerprint",
            database_instance_fingerprint,
            "database_instance_changed",
        ),
        ("expected_schema_root", current_schema_root, "schema_root_changed"),
        (
            "expected_result_schema_root",
            expected_result_schema_root,
            "result_schema_root_changed",
        ),
        ("migration_digest", migration_digest(migration_sql), "migration_changed"),
        ("target_version", target_version, "target_version_changed"),
    )
    for field, expected, code in comparisons:
        if effect.get(field) != expected:
            raise PermitError(code)

    trust = permit.get("trust")
    if trust is not None:
        if not isinstance(trust, Mapping):
            raise PermitError("trust_constraints_missing")
        if current_checkpoint_epoch is None or current_monotonic_counter is None:
            raise PermitError("trust_checkpoint_missing")
        if current_checkpoint_epoch < trust.get("minimum_checkpoint_epoch", -1):
            raise PermitError("checkpoint_epoch_too_old")
        if current_monotonic_counter != trust.get("monotonic_counter"):
            raise PermitError("monotonic_counter_changed")
        for field, observed, code in (
            ("replay_root", expected_replay_root, "replay_root_changed"),
            ("checkpoint_root", expected_checkpoint_root, "checkpoint_root_changed"),
            ("observation_root", expected_observation_root, "observation_root_changed"),
        ):
            if observed is None or trust.get(field) != observed:
                raise PermitError(code)
    return True


def execute_database_migration(
    permit: Mapping[str, Any] | None,
    *,
    adapter: DatabaseMigrationAdapterProtocol,
    migration_sql: str,
    registry_path: str | Path,
    public_key: Ed25519PublicKey | bytes,
    expected_identity_root: str,
    expected_evidence_root: str,
    expected_policy_root: str,
    expected_state_root: str,
    expected_approval_digest: str,
    executor_id: str,
    now: datetime | None = None,
    trust_checkpoint: Mapping[str, Any] | None = None,
    checkpoint_public_key: Ed25519PublicKey | bytes | None = None,
) -> dict[str, Any]:
    if permit is None:
        raise PermitError("permit_missing")
    effect = permit.get("effect")
    if not isinstance(effect, Mapping):
        raise PermitError("effect_missing")
    database_id = effect.get("database_id")
    expected_result = effect.get("expected_result_schema_root")
    expected_instance = effect.get("database_instance_fingerprint")
    target_version = effect.get("target_version")
    if not isinstance(database_id, str) or not database_id:
        raise PermitError("invalid_database_id")
    if not isinstance(expected_result, str):
        raise PermitError("invalid_expected_result_schema_root")
    if not isinstance(expected_instance, str):
        raise PermitError("invalid_database_instance_fingerprint")
    if not isinstance(target_version, int):
        raise PermitError("invalid_target_version")

    action = {
        "action_id": permit.get("permit_id"),
        "action_type": "database_migration",
        "target": database_id,
        "risk": "high",
        "reversible": False,
        "claim_ids": [expected_evidence_root],
        "execution": {
            "database_id": database_id,
            "database_instance_fingerprint": expected_instance,
            "migration_sql": migration_sql,
            "migration_digest": migration_digest(migration_sql),
            "target_version": target_version,
        },
    }
    before = adapter.observe(action)
    current_schema_root = _observation_root(before)
    current_instance = _observation_instance(before)
    trust_values = _trust_values(
        permit,
        registry_path=registry_path,
        trust_checkpoint=trust_checkpoint,
        checkpoint_public_key=checkpoint_public_key,
    )
    verify_database_migration_permit(
        permit,
        public_key=public_key,
        expected_identity_root=expected_identity_root,
        expected_evidence_root=expected_evidence_root,
        expected_policy_root=expected_policy_root,
        expected_state_root=expected_state_root,
        expected_approval_digest=expected_approval_digest,
        database_id=database_id,
        database_instance_fingerprint=current_instance,
        current_schema_root=current_schema_root,
        expected_result_schema_root=expected_result,
        migration_sql=migration_sql,
        target_version=target_version,
        now=now,
        **trust_values,
    )
    claim = _claim_permit(
        permit,
        registry_path=registry_path,
        executor_id=executor_id,
        consumed_at=_utc(now),
    )
    try:
        executor_receipt = adapter.execute(
            action,
            idempotency_key=claim["permit_hash"],
        )
    except Exception as exc:
        return _ambiguous_result(
            claim=claim,
            before=before,
            phase="execution",
            exc=exc,
        )
    try:
        after = adapter.observe(action)
    except Exception as exc:
        return _ambiguous_result(
            claim=claim,
            before=before,
            phase="reconciliation",
            exc=exc,
            executor_receipt=executor_receipt,
        )
    observed_root = _observation_root(after)
    observed_version = after.get("user_version")
    reconciled = observed_root == expected_result and observed_version == target_version
    if reconciled:
        authority_state = "RECONCILED"
    elif executor_receipt.get("status") == "failed":
        authority_state = "EXECUTION_FAILED"
    else:
        authority_state = "RECONCILIATION_FAILED"
    return {
        "permit_claim": claim,
        "authority_state": authority_state,
        "adapter_receipt": executor_receipt,
        "observations": {"before": before, "after": after},
    }


def _trust_values(
    permit: Mapping[str, Any],
    *,
    registry_path: str | Path,
    trust_checkpoint: Mapping[str, Any] | None,
    checkpoint_public_key: Ed25519PublicKey | bytes | None,
) -> dict[str, Any]:
    if permit.get("trust") is None:
        return {}
    if trust_checkpoint is None or checkpoint_public_key is None:
        raise PermitError("trust_checkpoint_missing")
    result = verify_trust_checkpoint(
        trust_checkpoint,
        registry_path=registry_path,
        public_key=checkpoint_public_key,
    )
    if not result["valid"]:
        if "replay_root_mismatch" in result["errors"]:
            raise PermitError("replay_root_changed")
        raise PermitError("trust_checkpoint_invalid", ",".join(result["errors"]))
    permit_hash = _required_text(permit, "record_hash")
    if replay_claim_exists(registry_path, permit_hash):
        raise PermitError("permit_replayed")
    roots = trust_checkpoint.get("roots")
    if not isinstance(roots, Mapping):
        raise PermitError("trust_checkpoint_invalid")
    return {
        "current_checkpoint_epoch": result["epoch"],
        "current_monotonic_counter": result["monotonic_counter"],
        "expected_replay_root": result["replay_root"],
        "expected_checkpoint_root": trust_checkpoint.get("record_hash"),
        "expected_observation_root": roots.get("observation"),
    }


def _claim_permit(
    permit: Mapping[str, Any],
    *,
    registry_path: str | Path,
    executor_id: str,
    consumed_at: datetime,
) -> dict[str, Any]:
    permit_hash = _required_text(permit, "record_hash")
    nonce = _required_text(permit, "nonce")
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, isolation_level=None)
    try:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS permit_claims (
                permit_hash TEXT PRIMARY KEY,
                nonce TEXT NOT NULL UNIQUE,
                executor_id TEXT NOT NULL,
                executing_at TEXT NOT NULL,
                consumed_at TEXT NOT NULL
            )
            """
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS permit_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                permit_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                executor_id TEXT NOT NULL
            )
            """
        )
        database.execute("BEGIN IMMEDIATE")
        timestamp = _format_time(consumed_at)
        try:
            database.execute(
                """
                INSERT INTO permit_claims
                    (permit_hash, nonce, executor_id, executing_at, consumed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (permit_hash, nonce, executor_id, timestamp, timestamp),
            )
            database.execute(
                """
                INSERT INTO permit_events
                    (permit_hash, state, observed_at, executor_id)
                VALUES (?, 'EXECUTING', ?, ?), (?, 'CONSUMED', ?, ?)
                """,
                (permit_hash, timestamp, executor_id, permit_hash, timestamp, executor_id),
            )
            database.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            database.execute("ROLLBACK")
            raise PermitError("permit_replayed") from exc
        except Exception:
            database.execute("ROLLBACK")
            raise
    finally:
        database.close()
    return {
        "permit_hash": permit_hash,
        "state": "CONSUMED",
        "executor_id": executor_id,
        "consumed_at": _format_time(consumed_at),
        "next_replay_root": replay_registry_root(path),
    }


def _observation_root(observation: Mapping[str, Any]) -> str:
    root = observation.get("schema_root")
    _require_digest(root, "schema_root")
    return root


def _observation_instance(observation: Mapping[str, Any]) -> str:
    fingerprint = observation.get("database_instance_fingerprint")
    _require_digest(fingerprint, "database_instance_fingerprint")
    return fingerprint


def _ambiguous_result(
    *,
    claim: dict[str, Any],
    before: Mapping[str, Any],
    phase: str,
    exc: Exception,
    executor_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = dict(executor_receipt or {})
    receipt.update(
        {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": claim["permit_hash"],
            "remote_operation_id": receipt.get("remote_operation_id"),
            "status": "unknown",
            "side_effect_confirmed": False,
            "retry_safe": False,
            "receipt_evidence": {
                "phase": phase,
                "error_type": type(exc).__name__,
                "prior_receipt": receipt.get("receipt_evidence"),
            },
        }
    )
    return {
        "permit_claim": claim,
        "authority_state": "RECONCILIATION_FAILED",
        "adapter_receipt": receipt,
        "observations": {"before": dict(before), "after": None},
    }


def _required_text(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise PermitError(f"{field}_missing")
    return value


def _require_digest(value: Any, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise PermitError(f"invalid_{field}")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PermitError(f"invalid_{field}") from exc


def _validated_trust_constraints(trust: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(trust)
    for field in ("replay_root", "checkpoint_root", "observation_root"):
        _require_digest(result.get(field), field)
    for field in ("minimum_checkpoint_epoch", "monotonic_counter"):
        value = result.get(field)
        if not isinstance(value, int) or value < 0:
            raise PermitError(f"invalid_{field}")
    return result


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise PermitError("naive_datetime")
    return value.astimezone(timezone.utc)


def _parse_time(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str):
        raise PermitError("invalid_timestamp")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise PermitError("invalid_timestamp") from exc


def _format_time(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")

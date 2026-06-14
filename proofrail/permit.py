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

from .core import ProofRailError
from .crypto import sign_record, verify_signature
from .trust import replay_claim_exists, replay_registry_root, verify_trust_checkpoint

ROOT_NAMES = ("identity", "evidence", "policy", "state")
MERGE_METHODS = {"merge", "squash", "rebase"}
PERMIT_ISSUER_ROLES = {"verifier", "governor"}


class GitHubMergeAdapterProtocol(Protocol):
    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        ...


class PermitError(ProofRailError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def mint_permit(
    *,
    identity_root: str,
    evidence_root: str,
    policy_root: str,
    state_root: str,
    approval_digest: str,
    repository: str,
    pull_number: int,
    expected_head_sha: str,
    merge_method: str,
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
    """Mint a signed permit for one exact GitHub merge effect."""
    issued_at = _utc(now)
    expiry = _parse_time(expires_at)
    if issuer_role not in PERMIT_ISSUER_ROLES:
        raise PermitError(
            "issuer_role_forbidden",
            f"Role {issuer_role!r} cannot mint execution permits",
        )
    if expiry <= issued_at:
        raise PermitError("permit_expired", "Permit expiry must be in the future")
    if len(nonce) < 16:
        raise PermitError("invalid_nonce", "Permit nonce must be at least 16 characters")
    if permit_id is not None and not permit_id.strip():
        raise PermitError("invalid_permit_id")
    if merge_method not in MERGE_METHODS:
        raise PermitError("unsupported_merge_method")
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise PermitError("invalid_pull_number")
    if repository.count("/") != 1:
        raise PermitError("invalid_repository")

    roots = {
        "identity": identity_root,
        "evidence": evidence_root,
        "policy": policy_root,
        "state": state_root,
    }
    for name, value in roots.items():
        _require_digest(value, f"{name}_root")
    _require_digest(approval_digest, "approval_digest")
    _require_sha(expected_head_sha, "expected_head_sha")

    record = {
        "kind": "proofrail.execution-permit.v0.2",
        "permit_id": permit_id or str(uuid.uuid4()),
        "state": "PERMITTED",
        "issued_at": _format_time(issued_at),
        "expires_at": _format_time(expiry),
        "nonce": nonce,
        "issuer": {
            "principal_id": issuer_principal_id,
            "role": issuer_role,
        },
        "roots": roots,
        "approval_digest": approval_digest,
        "effect": {
            "action_type": "github_merge",
            "repository": repository,
            "pull_number": pull_number,
            "expected_head_sha": expected_head_sha,
            "merge_method": merge_method,
        },
        "constraints": dict(constraints or {}),
    }
    if trust is not None:
        record["trust"] = _validated_trust_constraints(trust)
    return sign_record(record, private_key, key_id=key_id)


def verify_permit(
    permit: Mapping[str, Any],
    *,
    public_key: Ed25519PublicKey | bytes,
    expected_identity_root: str,
    expected_evidence_root: str,
    expected_policy_root: str,
    expected_state_root: str,
    expected_approval_digest: str,
    repository: str,
    pull_number: int,
    expected_head_sha: str,
    merge_method: str,
    now: datetime | None = None,
    current_checkpoint_epoch: int | None = None,
    current_monotonic_counter: int | None = None,
    expected_replay_root: str | None = None,
    expected_checkpoint_root: str | None = None,
    expected_observation_root: str | None = None,
) -> bool:
    """Verify signature, expiry, roots, approval, and exact GitHub effect."""
    try:
        verify_signature(permit, public_key)
    except ProofRailError as exc:
        raise PermitError("invalid_signature", str(exc)) from exc
    if permit.get("kind") != "proofrail.execution-permit.v0.2":
        raise PermitError("invalid_permit_kind")
    if permit.get("state") != "PERMITTED":
        raise PermitError("invalid_permit_state")
    issuer = permit.get("issuer")
    if not isinstance(issuer, Mapping) or issuer.get("role") not in PERMIT_ISSUER_ROLES:
        raise PermitError("issuer_role_forbidden")

    expiry = _parse_time(_required_text(permit, "expires_at"))
    if _utc(now) >= expiry:
        raise PermitError("permit_expired")

    expected_roots = {
        "identity": expected_identity_root,
        "evidence": expected_evidence_root,
        "policy": expected_policy_root,
        "state": expected_state_root,
    }
    roots = permit.get("roots")
    if not isinstance(roots, Mapping):
        raise PermitError("roots_missing")
    for name in ROOT_NAMES:
        if roots.get(name) != expected_roots[name]:
            raise PermitError(f"{name}_root_changed")

    if permit.get("approval_digest") != expected_approval_digest:
        raise PermitError("approval_scope_changed")

    effect = permit.get("effect")
    if not isinstance(effect, Mapping):
        raise PermitError("effect_missing")
    comparisons = (
        ("repository", repository, "repository_changed"),
        ("pull_number", pull_number, "pull_number_changed"),
        ("expected_head_sha", expected_head_sha, "pr_head_changed"),
        ("merge_method", merge_method, "merge_method_changed"),
    )
    for field, expected, code in comparisons:
        if effect.get(field) != expected:
            raise PermitError(code)
    if effect.get("action_type") != "github_merge":
        raise PermitError("action_type_changed")
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
        comparisons = (
            ("replay_root", expected_replay_root, "replay_root_changed"),
            ("checkpoint_root", expected_checkpoint_root, "checkpoint_root_changed"),
            ("observation_root", expected_observation_root, "observation_root_changed"),
        )
        for field, observed, code in comparisons:
            if observed is None or trust.get(field) != observed:
                raise PermitError(code)
    return True


def consume_permit(
    permit: Mapping[str, Any],
    *,
    registry_path: str | Path,
    public_key: Ed25519PublicKey | bytes,
    expected_identity_root: str,
    expected_evidence_root: str,
    expected_policy_root: str,
    expected_state_root: str,
    expected_approval_digest: str,
    repository: str,
    pull_number: int,
    expected_head_sha: str,
    merge_method: str,
    executor_id: str,
    now: datetime | None = None,
    trust_checkpoint: Mapping[str, Any] | None = None,
    checkpoint_public_key: Ed25519PublicKey | bytes | None = None,
) -> dict[str, Any]:
    """Atomically spend a valid permit and nonce before provider execution."""
    consumed_at = _utc(now)
    trust_values: dict[str, Any] = {}
    if permit.get("trust") is not None:
        if trust_checkpoint is None or checkpoint_public_key is None:
            raise PermitError("trust_checkpoint_missing")
        checkpoint_result = verify_trust_checkpoint(
            trust_checkpoint,
            registry_path=registry_path,
            public_key=checkpoint_public_key,
        )
        if not checkpoint_result["valid"]:
            if "replay_root_mismatch" in checkpoint_result["errors"]:
                raise PermitError("replay_root_changed")
            raise PermitError(
                "trust_checkpoint_invalid",
                ",".join(checkpoint_result["errors"]),
            )
        permit_hash = _required_text(permit, "record_hash")
        if replay_claim_exists(registry_path, permit_hash):
            raise PermitError("permit_replayed")
        roots = trust_checkpoint.get("roots")
        if not isinstance(roots, Mapping):
            raise PermitError("trust_checkpoint_invalid")
        trust_values = {
            "current_checkpoint_epoch": checkpoint_result["epoch"],
            "current_monotonic_counter": checkpoint_result["monotonic_counter"],
            "expected_replay_root": checkpoint_result["replay_root"],
            "expected_checkpoint_root": trust_checkpoint.get("record_hash"),
            "expected_observation_root": roots.get("observation"),
        }
    verify_permit(
        permit,
        public_key=public_key,
        expected_identity_root=expected_identity_root,
        expected_evidence_root=expected_evidence_root,
        expected_policy_root=expected_policy_root,
        expected_state_root=expected_state_root,
        expected_approval_digest=expected_approval_digest,
        repository=repository,
        pull_number=pull_number,
        expected_head_sha=expected_head_sha,
        merge_method=merge_method,
        now=consumed_at,
        **trust_values,
    )
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
        try:
            timestamp = _format_time(consumed_at)
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
        "next_checkpoint_epoch": (
            int(trust_values["current_checkpoint_epoch"]) + 1
            if trust_values
            else None
        ),
        "next_monotonic_counter": (
            int(trust_values["current_monotonic_counter"]) + 1
            if trust_values
            else None
        ),
    }


def execute_github_merge(
    permit: Mapping[str, Any] | None,
    *,
    adapter: GitHubMergeAdapterProtocol,
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
    """Spend an exact permit before exposing a GitHub merge to the adapter."""
    if permit is None:
        raise PermitError("permit_missing")
    effect = permit.get("effect")
    if not isinstance(effect, Mapping):
        raise PermitError("effect_missing")
    repository = effect.get("repository")
    pull_number = effect.get("pull_number")
    expected_head_sha = effect.get("expected_head_sha")
    merge_method = effect.get("merge_method")
    if not isinstance(repository, str) or "/" not in repository:
        raise PermitError("invalid_repository")
    owner, repo = repository.split("/", 1)

    claim = consume_permit(
        permit,
        registry_path=registry_path,
        public_key=public_key,
        expected_identity_root=expected_identity_root,
        expected_evidence_root=expected_evidence_root,
        expected_policy_root=expected_policy_root,
        expected_state_root=expected_state_root,
        expected_approval_digest=expected_approval_digest,
        repository=repository,
        pull_number=pull_number,
        expected_head_sha=expected_head_sha,
        merge_method=merge_method,
        executor_id=executor_id,
        now=now,
        trust_checkpoint=trust_checkpoint,
        checkpoint_public_key=checkpoint_public_key,
    )
    action = {
        "action_id": permit.get("permit_id"),
        "action_type": "github_merge",
        "target": f"{repository}#{pull_number}",
        "risk": "high",
        "reversible": False,
        "claim_ids": [expected_evidence_root],
        "execution": {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "expected_head_sha": expected_head_sha,
            "merge_method": merge_method,
        },
    }
    receipt = adapter.execute(action, idempotency_key=claim["permit_hash"])
    if receipt.get("status") == "success" and receipt.get("side_effect_confirmed") is True:
        authority_state = "RECONCILED"
    elif receipt.get("status") == "failed":
        authority_state = "EXECUTION_FAILED"
    else:
        authority_state = "RECONCILIATION_FAILED"
    return {
        "permit_claim": claim,
        "authority_state": authority_state,
        "adapter_receipt": receipt,
    }


def _required_text(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise PermitError(f"{field}_missing")
    return value


def _require_digest(value: str, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise PermitError(f"invalid_{field}")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PermitError(f"invalid_{field}") from exc


def _require_sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not 7 <= len(value) <= 64:
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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PermitError("invalid_timestamp") from exc
    return _utc(parsed)


def _format_time(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")

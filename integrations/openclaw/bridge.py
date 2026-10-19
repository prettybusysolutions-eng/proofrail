from __future__ import annotations

import json
import hashlib
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from proofrail.core import (
    GateDecision,
    Ledger,
    ProofRailError,
    evaluate_action,
    sign_document,
)


class ActionAdapter(Protocol):
    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ActionAdapter] = {}

    def register(self, action_type: str, adapter: ActionAdapter) -> None:
        if not action_type or action_type in self._adapters:
            raise ProofRailError(f"Adapter already registered or invalid: {action_type!r}")
        self._adapters[action_type] = adapter

    def resolve(self, action_type: str) -> ActionAdapter:
        try:
            return self._adapters[action_type]
        except KeyError as exc:
            raise ProofRailError(f"No execution adapter for action type: {action_type}") from exc


@dataclass(frozen=True)
class BridgeResult:
    status: str
    decision: dict[str, Any]
    receipt: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    prior: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision,
            "receipt": self.receipt,
            "execution": self.execution,
            "prior": self.prior,
        }


class OpenClawProofRailBridge:
    def __init__(
        self,
        *,
        state_db: str | Path,
        ledger_path: str | Path,
        registry: AdapterRegistry,
        evidence_secret: bytes,
        approval_secret: bytes,
        decision_secret: bytes,
        decision_key_id: str = "proofrail-openclaw",
    ) -> None:
        self.state_db = Path(state_db)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(ledger_path)
        self.registry = registry
        self.evidence_secret = evidence_secret
        self.approval_secret = approval_secret
        self.decision_secret = decision_secret
        self.decision_key_id = decision_key_id
        self._initialize_state()

    def run(
        self,
        *,
        action: dict[str, Any],
        evidence: list[dict[str, Any]],
        policy: dict[str, Any],
        approval: dict[str, Any] | None,
        actor: str,
    ) -> BridgeResult:
        decision = evaluate_action(
            action,
            evidence,
            policy,
            evidence_secret=self.evidence_secret,
            approval=approval,
            approval_secret=self.approval_secret if approval else None,
        )
        signed_decision = sign_document(
            {"kind": "proofrail.decision.v1", **decision.as_dict()},
            self.decision_secret,
            self.decision_key_id,
        )
        if not decision.allowed:
            return BridgeResult(status="denied", decision=signed_decision)

        prior = self._claim_execution(decision.action_digest, action["action_id"])
        if prior is not None:
            return BridgeResult(status="replay_blocked", decision=signed_decision, prior=prior)

        adapter = self.registry.resolve(action["action_type"])
        try:
            execution = validate_adapter_receipt(
                adapter.execute(action, idempotency_key=decision.action_digest),
                expected_idempotency_key=decision.action_digest,
            )
            outcome = execution["status"]
            receipt = self.ledger.append(
                action=action,
                decision=decision,
                outcome=outcome,
                actor=actor,
                details={"execution": execution},
            )
            self._complete_execution(decision.action_digest, outcome, receipt)
            return BridgeResult(
                status=outcome,
                decision=signed_decision,
                receipt=receipt,
                execution=execution,
            )
        except Exception as exc:
            # The adapter was invoked, so the side effect may already have
            # happened (e.g. the process ran, then output decoding or receipt
            # validation failed). Record the outcome as unknown, never failed,
            # and keep it in the tamper-evident ledger.
            error = {"error_type": type(exc).__name__, "error": str(exc)}
            try:
                receipt = self.ledger.append(
                    action=action,
                    decision=decision,
                    outcome="unknown",
                    actor=actor,
                    details={"adapter_error": error},
                )
            except Exception:
                receipt = None
            self._complete_execution(
                decision.action_digest,
                "unknown",
                {**error, "ledger_receipt": receipt},
            )
            raise

    def export_audit(self, action_digest: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT action_id, status, result_json FROM executions WHERE action_digest = ?",
                (action_digest,),
            ).fetchone()
        if row is None:
            raise ProofRailError("Unknown action digest")
        return {
            "kind": "proofrail.audit-export.v1",
            "action_digest": action_digest,
            "action_id": row[0],
            "status": row[1],
            "result": json.loads(row[2]) if row[2] else None,
            "ledger": self.ledger.verify(),
        }

    def _initialize_state(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    action_digest TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT
                )
                """
            )

    def _claim_execution(self, action_digest: str, action_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT action_id, status, result_json FROM executions WHERE action_digest = ?",
                (action_digest,),
            ).fetchone()
            if row is not None:
                connection.commit()
                return {
                    "action_id": row[0],
                    "status": row[1],
                    "result": json.loads(row[2]) if row[2] else None,
                }
            connection.execute(
                "INSERT INTO executions(action_digest, action_id, status) VALUES (?, ?, 'started')",
                (action_digest, action_id),
            )
            connection.commit()
            return None

    def _complete_execution(
        self,
        action_digest: str,
        status: str,
        result: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE executions SET status = ?, result_json = ? WHERE action_digest = ?",
                (status, json.dumps(result, sort_keys=True), action_digest),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.state_db, timeout=30)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class SubprocessAdapter:
    """Executes an exact argv without a shell and with a program allowlist."""

    def __init__(
        self,
        *,
        allowed_programs: set[str],
        timeout_seconds: int = 60,
        cwd: str | Path | None = None,
    ) -> None:
        self.allowed_programs = allowed_programs
        self.timeout_seconds = timeout_seconds
        self.cwd = str(cwd) if cwd else None

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        execution = action.get("execution")
        if not isinstance(execution, dict):
            raise ProofRailError("Action is missing an execution object")
        program = execution.get("program")
        arguments = execution.get("args", [])
        if program not in self.allowed_programs:
            raise ProofRailError(f"Program is not allowlisted: {program!r}")
        if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
            raise ProofRailError("Execution args must be a list of strings")
        try:
            completed = subprocess.run(
                [program, *arguments],
                cwd=self.cwd,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                env={"PATH": "/usr/bin:/bin", "PROOFRAIL_IDEMPOTENCY_KEY": idempotency_key},
            )
        except subprocess.TimeoutExpired as exc:
            # The program ran and may have produced its side effect before
            # being killed: outcome is unknown and must not be retried blindly.
            return {
                "contract": "proofrail.adapter-receipt.v1",
                "idempotency_key": idempotency_key,
                "remote_operation_id": f"local:{program}:{idempotency_key[:16]}",
                "status": "unknown",
                "side_effect_confirmed": False,
                "retry_safe": False,
                "receipt_evidence": {
                    "program": program,
                    "args": arguments,
                    "timeout_seconds": self.timeout_seconds,
                    **_output_evidence(exc.stdout or b"", exc.stderr or b""),
                },
            }
        result = {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": f"local:{program}:{idempotency_key[:16]}",
            "status": "success" if completed.returncode == 0 else "failed",
            "side_effect_confirmed": completed.returncode == 0,
            "retry_safe": bool(execution.get("retry_safe", False)),
            "receipt_evidence": {
                "program": program,
                "args": arguments,
                "returncode": completed.returncode,
                **_output_evidence(completed.stdout, completed.stderr),
            },
        }
        return result


def _output_evidence(stdout: bytes, stderr: bytes) -> dict[str, str]:
    """Hash the exact output bytes; decode only the display tails, lossily.

    Programs may emit bytes that are not valid UTF-8. Decoding strictly would
    raise after the program's side effect already happened.
    """
    return {
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_tail": stdout[-8192:].decode("utf-8", errors="replace"),
        "stderr_tail": stderr[-8192:].decode("utf-8", errors="replace"),
    }


def validate_adapter_receipt(
    receipt: dict[str, Any],
    *,
    expected_idempotency_key: str,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ProofRailError("Adapter did not return an object")
    required = {
        "contract",
        "idempotency_key",
        "remote_operation_id",
        "status",
        "side_effect_confirmed",
        "retry_safe",
        "receipt_evidence",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        raise ProofRailError(f"Adapter receipt missing fields: {', '.join(missing)}")
    if receipt["contract"] != "proofrail.adapter-receipt.v1":
        raise ProofRailError("Unsupported adapter receipt contract")
    if receipt["idempotency_key"] != expected_idempotency_key:
        raise ProofRailError("Adapter receipt idempotency key mismatch")
    if receipt["status"] not in {"success", "failed", "unknown"}:
        raise ProofRailError("Adapter receipt status is invalid")
    if not isinstance(receipt["side_effect_confirmed"], bool):
        raise ProofRailError("side_effect_confirmed must be boolean")
    if not isinstance(receipt["retry_safe"], bool):
        raise ProofRailError("retry_safe must be boolean")
    if not isinstance(receipt["receipt_evidence"], dict):
        raise ProofRailError("receipt_evidence must be an object")
    if receipt["status"] == "success":
        if not receipt["side_effect_confirmed"]:
            raise ProofRailError("Successful adapter receipt must confirm the side effect")
        if not isinstance(receipt["remote_operation_id"], str) or not receipt["remote_operation_id"]:
            raise ProofRailError("Successful adapter receipt requires a remote operation id")
        if not receipt["receipt_evidence"]:
            raise ProofRailError("Successful adapter receipt requires evidence")
    if receipt["status"] == "unknown" and receipt["retry_safe"]:
        raise ProofRailError("Unknown side-effect state cannot be declared retry-safe")
    return receipt

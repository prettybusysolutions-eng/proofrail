from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from integrations.openclaw.bridge import validate_adapter_receipt
from proofrail.core import ProofRailError
from proofrail.envelope import effect_digest, verify_action_authority_envelope
from proofrail.permit import PermitError

MCP_ACTION_TYPE = "mcp.tool_call"


class MCPToolAdapter(Protocol):
    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        ...


class MCPObservationAdapter(Protocol):
    def observe(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        adapter_receipt: Mapping[str, Any],
        effect_digest: str,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class MCPAuthorityResult:
    status: str
    reason: str
    envelope_digest: str
    adapter_receipt: dict[str, Any] | None = None
    observation_receipt: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "envelope_digest": self.envelope_digest,
            "adapter_receipt": self.adapter_receipt,
            "observation_receipt": self.observation_receipt,
        }


class MCPAuthorityMiddleware:
    """Verify and spend exact authority before a consequential MCP tool call."""

    def __init__(
        self,
        *,
        state_db: str | Path,
        adapter: MCPToolAdapter,
        observer: MCPObservationAdapter,
        issuer_public_key: Ed25519PublicKey | bytes,
    ) -> None:
        self.state_db = Path(state_db)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.observer = observer
        self.issuer_public_key = issuer_public_key
        self._initialize_state()

    def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        envelope: Mapping[str, Any],
        expected_roots: Mapping[str, str],
        expected_approval_digest: str,
    ) -> MCPAuthorityResult:
        envelope_digest = str(envelope.get("record_hash", ""))
        try:
            verify_action_authority_envelope(
                envelope,
                public_key=self.issuer_public_key,
                expected_roots=expected_roots,
                expected_approval_digest=expected_approval_digest,
                action_type=MCP_ACTION_TYPE,
                target=tool_name,
                parameters=arguments,
            )
        except PermitError as exc:
            return MCPAuthorityResult("denied", exc.code, envelope_digest)

        replay = self._consume(envelope)
        if replay is not None:
            return MCPAuthorityResult("denied", "authority_already_consumed", envelope_digest)

        try:
            adapter_receipt = validate_adapter_receipt(
                self.adapter.execute(
                    tool_name,
                    arguments,
                    idempotency_key=envelope_digest,
                ),
                expected_idempotency_key=envelope_digest,
            )
        except TimeoutError:
            return self._finish(
                envelope_digest,
                status="reconciliation_failed",
                reason="ambiguous_tool_timeout",
            )
        except Exception as exc:
            return self._finish(
                envelope_digest,
                status="reconciliation_failed",
                reason=f"adapter_error_ambiguous:{type(exc).__name__}",
            )

        try:
            observation = validate_observation_receipt(
                self.observer.observe(
                    tool_name,
                    arguments,
                    adapter_receipt=adapter_receipt,
                    effect_digest=envelope["effect"]["effect_digest"],
                ),
                envelope=envelope,
            )
        except Exception as exc:
            return self._finish(
                envelope_digest,
                status="reconciliation_failed",
                reason=f"observation_error:{type(exc).__name__}",
                adapter_receipt=adapter_receipt,
            )

        adapter_status = adapter_receipt["status"]
        observation_status = observation["status"]
        if adapter_status == "unknown" or observation_status == "unknown":
            return self._finish(
                envelope_digest,
                status="reconciliation_failed",
                reason="ambiguous_observed_outcome",
                adapter_receipt=adapter_receipt,
                observation_receipt=observation,
            )
        if adapter_status != observation_status:
            return self._finish(
                envelope_digest,
                status="reconciliation_failed",
                reason="false_success_denied"
                if adapter_status == "success"
                else "outcome_contradiction",
                adapter_receipt=adapter_receipt,
                observation_receipt=observation,
            )
        status = adapter_status
        return self._finish(
            envelope_digest,
            status=status,
            reason="observed_success" if status == "success" else "observed_failure",
            adapter_receipt=adapter_receipt,
            observation_receipt=observation,
        )

    def _initialize_state(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consumed_authority (
                    envelope_digest TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    result_json TEXT
                )
                """
            )

    def _consume(self, envelope: Mapping[str, Any]) -> dict[str, Any] | None:
        envelope_digest = str(envelope["record_hash"])
        nonce = str(envelope["nonce"])
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, result_json FROM consumed_authority "
                "WHERE envelope_digest = ? OR nonce = ?",
                (envelope_digest, nonce),
            ).fetchone()
            if row is not None:
                return {
                    "status": row[0],
                    "result": json.loads(row[1]) if row[1] else None,
                }
            connection.execute(
                "INSERT INTO consumed_authority(envelope_digest, nonce, status) "
                "VALUES (?, ?, 'consumed')",
                (envelope_digest, nonce),
            )
            return None

    def _finish(
        self,
        envelope_digest: str,
        *,
        status: str,
        reason: str,
        adapter_receipt: dict[str, Any] | None = None,
        observation_receipt: dict[str, Any] | None = None,
    ) -> MCPAuthorityResult:
        result = MCPAuthorityResult(
            status=status,
            reason=reason,
            envelope_digest=envelope_digest,
            adapter_receipt=adapter_receipt,
            observation_receipt=observation_receipt,
        )
        with self._connect() as connection:
            connection.execute(
                "UPDATE consumed_authority SET status = ?, result_json = ? "
                "WHERE envelope_digest = ?",
                (status, json.dumps(result.as_dict(), sort_keys=True), envelope_digest),
            )
        return result

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


def validate_observation_receipt(
    receipt: Mapping[str, Any],
    *,
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise ProofRailError("Observation receipt must be an object")
    required = {
        "contract",
        "effect_digest",
        "status",
        "confirmations",
        "evidence",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        raise ProofRailError(
            "Observation receipt missing fields: " + ", ".join(missing)
        )
    if receipt["contract"] != "proofrail.observation-receipt.v1":
        raise ProofRailError("Unsupported observation receipt contract")
    if receipt["effect_digest"] != envelope["effect"]["effect_digest"]:
        raise ProofRailError("Observation effect digest mismatch")
    if receipt["status"] not in {"success", "failed", "unknown"}:
        raise ProofRailError("Observation status is invalid")
    minimum = envelope["observation_contract"]["minimum_confirmations"]
    if not isinstance(receipt["confirmations"], int) or receipt["confirmations"] < minimum:
        raise ProofRailError("Observation confirmations below required minimum")
    if not isinstance(receipt["evidence"], Mapping) or not receipt["evidence"]:
        raise ProofRailError("Observation evidence is required")
    return dict(receipt)

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from integrations.openclaw.bridge import validate_adapter_receipt
from proofrail.core import ProofRailError
from proofrail.crypto import canonical_json
from proofrail.envelope import effect_digest, verify_action_authority_envelope
from proofrail.permit import PermitError

MCP_ACTION_TYPE = "mcp.tool_call"

# Trusted, server-side view of current authority state for one effect:
# {"roots": {identity, evidence, policy, state}, "approval_digest": str}.
TrustedStateProvider = Callable[[str], Mapping[str, Any]]


def mcp_target(server_id: str, tool_name: str) -> str:
    """The signed target for a tool on one MCP server: mcp://<server_id>/<tool>.

    Binding the server means an envelope minted for one server's tool is not
    valid on another server that exposes a tool with the same name.
    """
    return f"mcp://{server_id}/{tool_name}"


class ConsumptionStore(Protocol):
    """Single-use authority ledger. Replicas of one server must share it."""

    def claim(
        self,
        envelope_digest: str,
        nonce: str,
        *,
        recheck: Callable[[], str | None],
    ) -> str | None:
        """Atomically spend authority. Return None when spent now, otherwise a
        denial reason: "authority_already_consumed", or whatever `recheck`
        (called inside the atomic section) returned."""
        ...

    def finish(self, envelope_digest: str, status: str, result_json: str) -> None:
        ...


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
        server_id: str,
        trusted_state: TrustedStateProvider,
        adapter: MCPToolAdapter,
        observer: MCPObservationAdapter,
        issuer_public_key: Ed25519PublicKey | bytes,
        state_db: str | Path | None = None,
        consumption_store: ConsumptionStore | None = None,
    ) -> None:
        """
        server_id: this server's identity, bound into every effect target.
        trusted_state: server-side source of current roots and approval for an
            effect. Callers of invoke() cannot supply these.
        consumption_store / state_db: where authority is spent. Every replica
            of one server must use the same store, or authority is single-use
            per replica rather than per server.
        """
        if not isinstance(server_id, str) or not server_id.strip() or "/" in server_id:
            raise ProofRailError("server_id must be a non-empty identifier without '/'")
        if (consumption_store is None) == (state_db is None):
            raise ProofRailError("Provide exactly one of consumption_store or state_db")
        if not callable(trusted_state):
            raise ProofRailError("trusted_state must be callable")
        self.server_id = server_id
        self.trusted_state = trusted_state
        self.store = consumption_store or SQLiteConsumptionStore(state_db)
        self.adapter = adapter
        self.observer = observer
        self.issuer_public_key = issuer_public_key

    def invoke(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        envelope: Mapping[str, Any],
    ) -> MCPAuthorityResult:
        # Snapshot caller-supplied inputs exactly once, as canonical JSON bytes.
        # Everything below (verification, consumption, execution, observation)
        # works from fresh copies decoded from these bytes, so a caller-held
        # Mapping that changes between reads, or a nested object mutated after
        # verification, cannot alter the effect that was authorized.
        if not isinstance(envelope, Mapping):
            return MCPAuthorityResult("denied", "invalid_envelope", "")
        if not isinstance(arguments, Mapping) or not isinstance(tool_name, str):
            return MCPAuthorityResult("denied", "invalid_arguments", "")
        try:
            frozen_envelope = canonical_json(dict(envelope))
            frozen_arguments = canonical_json(dict(arguments))
        except (ProofRailError, TypeError, ValueError, RecursionError):
            # RecursionError: cyclic or extremely deep input.
            return MCPAuthorityResult("denied", "non_canonical_input", "")
        envelope = _thaw(frozen_envelope)
        envelope_digest = str(envelope.get("record_hash", ""))
        target = mcp_target(self.server_id, tool_name)
        # Key trusted state on the effect this server computes, never on the
        # envelope's own claim about itself.
        computed_effect = effect_digest(MCP_ACTION_TYPE, target, _thaw(frozen_arguments))
        state = self._trusted(computed_effect)
        if state is None:
            return MCPAuthorityResult("denied", "trusted_state_unavailable", envelope_digest)
        try:
            verify_action_authority_envelope(
                envelope,
                public_key=self.issuer_public_key,
                expected_roots=state["roots"],
                expected_approval_digest=state["approval_digest"],
                action_type=MCP_ACTION_TYPE,
                target=target,
                parameters=_thaw(frozen_arguments),
            )
        except PermitError as exc:
            return MCPAuthorityResult("denied", exc.code, envelope_digest)

        def recheck() -> str | None:
            # Inside the store's atomic section: a revocation or policy change
            # committed after verification must still stop this execution.
            current = self._trusted(computed_effect)
            if current is None:
                return "trusted_state_unavailable"
            if dict(current["roots"]) != dict(envelope.get("roots", {})):
                return "state_changed_before_consumption"
            if current["approval_digest"] != envelope.get("approval_digest"):
                return "approval_changed_before_consumption"
            return None

        denial = self.store.claim(envelope_digest, str(envelope["nonce"]), recheck=recheck)
        if denial is not None:
            return MCPAuthorityResult("denied", denial, envelope_digest)

        try:
            adapter_receipt = validate_adapter_receipt(
                self.adapter.execute(
                    tool_name,
                    _thaw(frozen_arguments),
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
                    _thaw(frozen_arguments),
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

    def _trusted(self, computed_effect: str) -> Mapping[str, Any] | None:
        try:
            state = self.trusted_state(computed_effect)
        except Exception:
            return None
        if not isinstance(state, Mapping) or not isinstance(state.get("roots"), Mapping) \
                or not isinstance(state.get("approval_digest"), str):
            return None
        return state

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
        self.store.finish(envelope_digest, status, json.dumps(result.as_dict(), sort_keys=True))
        return result


class SQLiteConsumptionStore:
    """Default ConsumptionStore. Share one database file across a server's replicas."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
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

    def claim(self, envelope_digest: str, nonce: str, *, recheck: Callable[[], str | None]) -> str | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT 1 FROM consumed_authority WHERE envelope_digest = ? OR nonce = ?",
                (envelope_digest, nonce),
            ).fetchone()
            if row is not None:
                return "authority_already_consumed"
            reason = recheck()
            if reason is not None:
                return reason
            connection.execute(
                "INSERT INTO consumed_authority(envelope_digest, nonce, status) VALUES (?, ?, 'consumed')",
                (envelope_digest, nonce),
            )
            return None

    def finish(self, envelope_digest: str, status: str, result_json: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE consumed_authority SET status = ?, result_json = ? WHERE envelope_digest = ?",
                (status, result_json, envelope_digest),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_MAX_SAFE_INTEGER = 2**53


def _thaw(frozen: bytes) -> dict[str, Any]:
    """Decode an independent copy of a canonical JSON snapshot.

    RFC 8785 writes a large float such as 1.2345678901234568e20 as
    123456789012345680000. Decoding that as an int would exceed the canonical
    integer range and could not be re-canonicalised, so integers beyond
    2**53 decode as floats, which reproduce the identical canonical bytes.
    """
    def parse_int(text: str) -> int | float:
        value = int(text)
        return float(value) if abs(value) > _MAX_SAFE_INTEGER else value

    return json.loads(frozen, parse_int=parse_int)


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

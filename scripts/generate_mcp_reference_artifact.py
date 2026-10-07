from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.mcp.middleware import MCPAuthorityMiddleware
from proofrail.core import ProofRailError
from proofrail.crypto import canonical_json, sign_record, verify_signature
from proofrail.envelope import mint_action_authority_envelope

ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL = "5" * 64
PRIVATE_KEY_BYTES = bytes.fromhex("42" * 32)
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


class Adapter:
    def __init__(self, *, timeout: bool = False):
        self.calls = 0
        self.timeout = timeout

    def execute(self, tool_name, arguments, *, idempotency_key):
        self.calls += 1
        if self.timeout:
            raise TimeoutError("simulated provider timeout")
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "provider:operation-1",
            "status": "success",
            "side_effect_confirmed": True,
            "retry_safe": False,
            "receipt_evidence": {"provider_request_id": "request-1"},
        }


class Observer:
    def __init__(self, status="success"):
        self.status = status

    def observe(self, tool_name, arguments, *, adapter_receipt, effect_digest):
        return {
            "contract": "proofrail.observation-receipt.v1",
            "effect_digest": effect_digest,
            "status": self.status,
            "confirmations": 1,
            "evidence": {"provider_state_digest": "6" * 64},
        }


def build_report() -> dict[str, Any]:
    private_key = Ed25519PrivateKey.from_private_bytes(PRIVATE_KEY_BYTES)
    public_key = private_key.public_key()
    arguments = {"ticket_id": "INC-42", "state": "closed"}

    def envelope(nonce: str):
        return mint_action_authority_envelope(
            roots=ROOTS,
            approval_digest=APPROVAL,
            action_type="mcp.tool_call",
            target="support.close_ticket",
            parameters=arguments,
            subject_principal_id="agent:operator",
            subject_role="executor",
            issuer_principal_id="verifier:primary",
            issuer_role="verifier",
            adapter_contract={
                "name": "proofrail.adapter-receipt",
                "version": "v1",
                "idempotency_required": True,
            },
            observation_contract={
                "name": "proofrail.provider-observation",
                "version": "v1",
                "minimum_confirmations": 1,
                "success_predicate_digest": "7" * 64,
            },
            nonce=nonce,
            expires_at="2099-01-01T00:00:00Z",
            private_key=private_key,
            key_id="mcp-artifact-verifier",
            now=NOW,
            envelope_id=f"artifact-{nonce[-4:]}",
        )

    scenarios: list[dict[str, Any]] = []

    def run(
        name: str,
        *,
        suffix: str,
        adapter: Adapter | None = None,
        observer: Observer | None = None,
        call_arguments: dict[str, Any] | None = None,
        roots: dict[str, str] | None = None,
        replay: bool = False,
    ) -> None:
        tool_adapter = adapter or Adapter()
        authority = envelope(f"mcp-artifact-nonce-{suffix}")
        with tempfile.TemporaryDirectory() as directory:
            middleware = MCPAuthorityMiddleware(
                state_db=Path(directory) / "state.sqlite3",
                adapter=tool_adapter,
                observer=observer or Observer(),
                issuer_public_key=public_key,
            )
            result = middleware.invoke(
                tool_name="support.close_ticket",
                arguments=call_arguments or arguments,
                envelope=authority,
                expected_roots=roots or ROOTS,
                expected_approval_digest=APPROVAL,
            )
            if replay:
                result = middleware.invoke(
                    tool_name="support.close_ticket",
                    arguments=arguments,
                    envelope=authority,
                    expected_roots=ROOTS,
                    expected_approval_digest=APPROVAL,
                )
        scenarios.append(
            {
                "name": name,
                "status": result.status,
                "reason": result.reason,
                "adapter_calls": tool_adapter.calls,
            }
        )

    run("valid_observed_call", suffix="0001")
    run(
        "mutated_parameters",
        suffix="0002",
        call_arguments={**arguments, "notify_customer": True},
    )
    run("stale_state", suffix="0003", roots={**ROOTS, "state": "8" * 64})
    run("replay", suffix="0004", replay=True)
    run("timeout_ambiguity", suffix="0005", adapter=Adapter(timeout=True))
    run("false_success", suffix="0006", observer=Observer(status="failed"))

    report = {
        "kind": "proofrail.mcp-reference-artifact.v1",
        "generated_at": "2026-06-15T12:00:00Z",
        "profile": "proofrail-mcp-authority-v1",
        "scenarios": scenarios,
        "expected": {
            "valid_observed_call": ["success", "observed_success", 1],
            "mutated_parameters": ["denied", "parameters_changed", 0],
            "stale_state": ["denied", "state_root_changed", 0],
            "replay": ["denied", "authority_already_consumed", 1],
            "timeout_ambiguity": [
                "reconciliation_failed",
                "ambiguous_tool_timeout",
                1,
            ],
            "false_success": [
                "reconciliation_failed",
                "false_success_denied",
                1,
            ],
        },
    }
    return sign_record(report, private_key, key_id="mcp-artifact-verifier")


def write_artifact(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.from_private_bytes(PRIVATE_KEY_BYTES)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    report = build_report()
    (directory / "mcp-reference-report.json").write_bytes(canonical_json(report) + b"\n")
    (directory / "verifier-public-key.hex").write_text(
        public_bytes.hex() + "\n",
        encoding="ascii",
    )


def verify_artifact(directory: Path) -> bool:
    try:
        report_path = directory / "mcp-reference-report.json"
        public_key_path = directory / "verifier-public-key.hex"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        public_key = bytes.fromhex(public_key_path.read_text(encoding="ascii").strip())
        verify_signature(report, public_key)
        expected_report = build_report()
        return canonical_json(report) == canonical_json(expected_report)
    except (OSError, ValueError, json.JSONDecodeError, ProofRailError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    if bool(arguments.out) == bool(arguments.verify):
        parser.error("provide exactly one of --out or --verify")
    if arguments.out:
        write_artifact(arguments.out)
        return 0
    return 0 if verify_artifact(arguments.verify) else 4


if __name__ == "__main__":
    raise SystemExit(main())

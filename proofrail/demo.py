from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .checkpoint import create_checkpoint, verify_checkpoint, verify_ledger
from .control_plane import ControlPlane
from .core import ProofRailError, digest_ledger_entry
from .permit import PermitError, execute_github_merge, mint_permit, verify_permit

DEMO_TIME = datetime(2026, 6, 11, 21, 30, tzinfo=timezone.utc)
ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL_DIGEST = "5" * 64
HEAD_SHA = "abcdef1234567890"


class _RecordingAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        self.calls.append((action, idempotency_key))
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "demo-merge-sha",
            "status": "success",
            "side_effect_confirmed": True,
            "retry_safe": True,
            "receipt_evidence": {"provider": "demo", "observed": True},
        }


class _ReconcilingFalseSuccessAdapter:
    """Simulates a success claim contradicted by an independent provider read."""

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": None,
            "status": "unknown",
            "side_effect_confirmed": False,
            "retry_safe": False,
            "receipt_evidence": {
                "phase": "reconciliation",
                "executor_claim": {"merged": True, "sha": "claimed"},
                "provider_observation": {
                    "merged": False,
                    "head_sha": action["execution"]["expected_head_sha"],
                },
            },
        }


def run_github_merge_authority_demo(output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    outcomes: list[dict[str, Any]] = []
    with TemporaryDirectory() as temporary:
        temp = Path(temporary)
        registry = temp / "permits.sqlite3"

        valid_permit = _permit(private_key, "demo-nonce-valid-0001")
        adapter = _RecordingAdapter()
        allowed = execute_github_merge(
            valid_permit,
            adapter=adapter,
            registry_path=registry,
            public_key=public_key,
            expected_identity_root=ROOTS["identity"],
            expected_evidence_root=ROOTS["evidence"],
            expected_policy_root=ROOTS["policy"],
            expected_state_root=ROOTS["state"],
            expected_approval_digest=APPROVAL_DIGEST,
            executor_id="executor:demo",
            now=DEMO_TIME,
        )
        outcomes.append(
            _outcome(
                "valid_permit",
                allowed["authority_state"] == "RECONCILED" and len(adapter.calls) == 1,
                allowed["authority_state"],
            )
        )

        try:
            verify_permit(
                _permit(private_key, "demo-nonce-head-00001"),
                public_key=public_key,
                expected_identity_root=ROOTS["identity"],
                expected_evidence_root=ROOTS["evidence"],
                expected_policy_root=ROOTS["policy"],
                expected_state_root=ROOTS["state"],
                expected_approval_digest=APPROVAL_DIGEST,
                repository="example/repository",
                pull_number=42,
                expected_head_sha="deadbeef",
                merge_method="squash",
                now=DEMO_TIME,
            )
            head_denied = False
            head_reason = "unexpectedly_allowed"
        except PermitError as exc:
            head_denied = exc.code == "pr_head_changed"
            head_reason = exc.code
        outcomes.append(_outcome("changed_pr_head", head_denied, head_reason))

        try:
            execute_github_merge(
                valid_permit,
                adapter=_RecordingAdapter(),
                registry_path=registry,
                public_key=public_key,
                expected_identity_root=ROOTS["identity"],
                expected_evidence_root=ROOTS["evidence"],
                expected_policy_root=ROOTS["policy"],
                expected_state_root=ROOTS["state"],
                expected_approval_digest=APPROVAL_DIGEST,
                executor_id="executor:demo",
                now=DEMO_TIME,
            )
            replay_denied = False
            replay_reason = "unexpectedly_allowed"
        except PermitError as exc:
            replay_denied = exc.code == "permit_replayed"
            replay_reason = exc.code
        outcomes.append(_outcome("consumed_permit_replay", replay_denied, replay_reason))

        false_success = execute_github_merge(
            _permit(private_key, "demo-nonce-false-0001"),
            adapter=_ReconcilingFalseSuccessAdapter(),
            registry_path=registry,
            public_key=public_key,
            expected_identity_root=ROOTS["identity"],
            expected_evidence_root=ROOTS["evidence"],
            expected_policy_root=ROOTS["policy"],
            expected_state_root=ROOTS["state"],
            expected_approval_digest=APPROVAL_DIGEST,
            executor_id="executor:demo",
            now=DEMO_TIME,
        )
        outcomes.append(
            _outcome(
                "false_merge_success",
                false_success["authority_state"] == "RECONCILIATION_FAILED",
                false_success["authority_state"],
            )
        )

        control = ControlPlane(temp / "control.sqlite3")
        tenant = control.create_tenant("ProofRail Demo")
        control.grant_role(tenant, "governor:demo", "governor")
        control.grant_role(tenant, "learner:demo", "learner")
        policy = control.publish_policy(
            tenant_id=tenant,
            principal_id="governor:demo",
            policy_name="github-merge",
            document={"allowed_action_types": ["github_merge"]},
        )
        try:
            control.activate_policy(
                tenant_id=tenant,
                principal_id="learner:demo",
                policy_name="github-merge",
                version=policy.version,
            )
            learner_denied = False
            learner_reason = "unexpectedly_allowed"
        except ProofRailError:
            learner_denied = True
            learner_reason = "policy_activation_forbidden"
        outcomes.append(_outcome("learner_promotion", learner_denied, learner_reason))

    ledger_path = output / "proofrail-ledger.jsonl"
    _write_demo_ledger(ledger_path, outcomes)

    tampered_path = output / "tampered-ledger.jsonl"
    tampered_records = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    tampered_records[0]["result"] = "fabricated"
    tampered_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in tampered_records) + "\n",
        encoding="utf-8",
    )
    tamper_result = verify_ledger(tampered_path)
    outcomes.append(
        _outcome(
            "ledger_mutation",
            not tamper_result["valid"],
            ",".join(tamper_result["errors"]),
        )
    )
    _write_demo_ledger(ledger_path, outcomes)
    ledger_result = verify_ledger(ledger_path)

    checkpoint = create_checkpoint(
        ledger_path,
        private_key=private_key,
        key_id="demo-checkpoint-key",
        now=DEMO_TIME + timedelta(minutes=1),
    )
    checkpoint_path = output / "proofrail-checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    public_key_path = output / "checkpoint-public-key.txt"
    public_key_path.write_text(
        base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii") + "\n",
        encoding="utf-8",
    )
    checkpoint_result = verify_checkpoint(
        checkpoint,
        ledger_path,
        public_key=public_key,
    )

    valid = (
        all(item["passed"] for item in outcomes)
        and ledger_result["valid"]
        and checkpoint_result["valid"]
    )
    transcript = _transcript(
        outcomes,
        ledger_result=ledger_result,
        checkpoint_result=checkpoint_result,
        output=output,
        valid=valid,
    )
    (output / "TRANSCRIPT.md").write_text(transcript + "\n", encoding="utf-8")
    return {
        "valid": valid,
        "transcript": transcript,
        "output_dir": str(output),
        "ledger": str(ledger_path),
        "checkpoint": str(checkpoint_path),
        "public_key": str(public_key_path),
        "tampered_ledger": str(tampered_path),
    }


def _permit(private_key: Ed25519PrivateKey, nonce: str) -> dict[str, Any]:
    return mint_permit(
        identity_root=ROOTS["identity"],
        evidence_root=ROOTS["evidence"],
        policy_root=ROOTS["policy"],
        state_root=ROOTS["state"],
        approval_digest=APPROVAL_DIGEST,
        repository="example/repository",
        pull_number=42,
        expected_head_sha=HEAD_SHA,
        merge_method="squash",
        nonce=nonce,
        expires_at=DEMO_TIME + timedelta(minutes=5),
        issuer_principal_id="verifier:demo",
        issuer_role="verifier",
        private_key=private_key,
        key_id="demo-verifier-key",
        now=DEMO_TIME,
    )


def _outcome(scenario: str, passed: bool, result: str) -> dict[str, Any]:
    return {"scenario": scenario, "passed": passed, "result": result}


def _write_demo_ledger(path: Path, outcomes: list[dict[str, Any]]) -> None:
    previous_hash = "GENESIS"
    records = []
    for sequence, outcome in enumerate(outcomes, start=1):
        record = {
            "kind": "proofrail.demo-proof.v0.3",
            "sequence": sequence,
            "recorded_at": (
                DEMO_TIME + timedelta(seconds=sequence)
            ).isoformat().replace("+00:00", "Z"),
            **outcome,
            "previous_hash": previous_hash,
        }
        record["entry_hash"] = digest_ledger_entry(record)
        previous_hash = record["entry_hash"]
        records.append(record)
    path.write_text(
        "\n".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def _transcript(
    outcomes: list[dict[str, Any]],
    *,
    ledger_result: dict[str, Any],
    checkpoint_result: dict[str, Any],
    output: Path,
    valid: bool,
) -> str:
    lines = [
        "# ProofRail GitHub Merge Authority Demo",
        "",
        f"Overall: {'PASS' if valid else 'FAIL'}",
        "",
    ]
    labels = {
        "valid_permit": "valid permit -> execution allowed",
        "changed_pr_head": "changed PR head -> denied",
        "consumed_permit_replay": "consumed permit replay -> denied",
        "false_merge_success": "false merge success -> reconciliation failed",
        "learner_promotion": "learner promotion attempt -> denied",
        "ledger_mutation": "ledger mutation -> tamper detected",
    }
    for outcome in outcomes:
        lines.append(
            f"- [{'PASS' if outcome['passed'] else 'FAIL'}] "
            f"{labels[outcome['scenario']]} ({outcome['result']})"
        )
    lines.extend(
        [
            "",
            f"Ledger entries: {ledger_result['entries']}",
            f"Merkle root: `{ledger_result['merkle_root']}`",
            f"Checkpoint signature: {'valid' if checkpoint_result['valid'] else 'invalid'}",
            f"Artifacts: `{output}`",
        ]
    )
    return "\n".join(lines)

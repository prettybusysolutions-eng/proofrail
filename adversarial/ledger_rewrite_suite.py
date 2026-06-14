from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.checkpoint import (
    create_checkpoint,
    read_ledger,
    verify_checkpoint,
    verify_ledger,
)
from proofrail.anchor import create_anchor, verify_anchor
from proofrail.trust import EMPTY_ROOT

from .common import result, write_ledger


def run() -> list[dict]:
    key = Ed25519PrivateKey.generate()
    with TemporaryDirectory() as directory:
        ledger = Path(directory) / "ledger.jsonl"
        write_ledger(ledger)
        checkpoint = create_checkpoint(
            ledger,
            private_key=key,
            key_id="checkpoint-key",
        )
        anchor = create_anchor(
            ledger,
            trust_checkpoint_hash=EMPTY_ROOT,
            private_key=key,
            key_id="anchor-key",
            anchor_provider="local-file",
            anchor_reference="file:anchor.pub",
        )
        records = read_ledger(ledger)
        records[0]["result"] = "fabricated"
        ledger.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
            encoding="utf-8",
        )
        mutation = verify_ledger(ledger)

        write_ledger(ledger)
        records = read_ledger(ledger)
        ledger.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records[:-1]) + "\n",
            encoding="utf-8",
        )
        truncation = verify_ledger(ledger)
        externally_anchored = verify_anchor(anchor, ledger, public_key=key.public_key())
        anchored = verify_checkpoint(checkpoint, ledger, public_key=key.public_key())
    return [
        result(
            attack_id="LEDGER-001",
            suite="ledger_rewrite_suite",
            threat="In-place ledger record mutation",
            trust_assumption="Verification is run against the ledger before relying on history.",
            attack="Rewrite an old record without recomputing its hash chain.",
            expected="Ledger verification exposes tampering.",
            actual=f"Valid: {mutation['valid']}; errors: {mutation['errors']}.",
            passed=not mutation["valid"],
            evidence=["proofrail/checkpoint.py:verify_ledger", "adversarial/ledger_rewrite_suite.py"],
            residual_risk="An attacker able to rewrite all records and all trusted anchors may still replace history.",
        ),
        result(
            attack_id="LEDGER-002",
            suite="ledger_rewrite_suite",
            threat="External-anchor tail truncation",
            trust_assumption="The signed anchor and verification key remain independently available.",
            attack="Delete the final valid ledger record, then verify against its external anchor.",
            expected="External anchor verification detects missing history.",
            actual=(
                f"Standalone ledger valid: {truncation['valid']}; "
                f"external anchor valid: {externally_anchored['valid']}; "
                f"errors: {externally_anchored['errors']}."
            ),
            passed=truncation["valid"] and not externally_anchored["valid"],
            evidence=["proofrail/anchor.py:verify_anchor", "adversarial/ledger_rewrite_suite.py"],
            residual_risk="Deleting or replacing both ledger and independently retained anchor defeats continuity detection.",
        ),
        result(
            attack_id="LEDGER-003",
            suite="ledger_rewrite_suite",
            threat="Anchored tail truncation",
            trust_assumption="The checkpoint public key and checkpoint artifact remain independently available.",
            attack="Verify a truncated ledger against its prior signed checkpoint.",
            expected="Checkpoint verification exposes truncation.",
            actual=f"Valid: {anchored['valid']}; errors: {anchored['errors']}.",
            passed=not anchored["valid"] and any(
                "checkpoint_" in error for error in anchored["errors"]
            ),
            evidence=["proofrail/checkpoint.py:verify_checkpoint", "adversarial/ledger_rewrite_suite.py"],
            residual_risk="Checkpoint deletion or signing-key compromise defeats this detection path.",
        ),
    ]

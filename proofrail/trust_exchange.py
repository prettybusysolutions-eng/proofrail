"""Experimental, portable cross-operator witness verification for ProofRail.

The verifier does not operate a witness, provision keys, issue authority,
observe a provider, or validate SCITT inclusion proofs. Those MUST happen
outside an executing agent for independent provenance claims.

All trust anchors (checkpoint public key, prior commitment and witness roster)
come from caller-controlled inputs, never from the evidence bundle.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .checkpoint import verify_checkpoint
from .core import ProofRailError
from .crypto import hash_record, sign_record, verify_signature

KIND = "proofrail.cross-domain-witness-statement.v0"
RECEIPT_KIND = "proofrail.cross-domain-witness-receipt.v0"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = frozenset({
    "kind", "authority_digest", "effect_digest", "outcome_digest",
    "checkpoint_digest", "previous_checkpoint_digest", "sequence",
    "execution_domain",
})


def _digest(value: Any, field: str) -> None:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise ProofRailError(f"{field}_invalid")


def build_witness_statement(
    *,
    authority_digest: str,
    effect_digest: str,
    outcome_digest: str,
    checkpoint_digest: str,
    previous_checkpoint_digest: str,
    sequence: int,
    execution_domain: str,
) -> dict[str, Any]:
    """Create the exact subject each independent operator may attest to.

    The caller still must independently validate what an outcome digest means;
    signing an assertion never proves an actual external side effect.
    """
    for field, value in (
        ("authority_digest", authority_digest), ("effect_digest", effect_digest),
        ("outcome_digest", outcome_digest), ("checkpoint_digest", checkpoint_digest),
    ):
        _digest(value, field)
    if previous_checkpoint_digest != "GENESIS":
        _digest(previous_checkpoint_digest, "previous_checkpoint_digest")
    if type(sequence) is not int or sequence < 1:
        raise ProofRailError("sequence_invalid")
    if not isinstance(execution_domain, str) or not execution_domain.strip():
        raise ProofRailError("execution_domain_invalid")
    return {
        "kind": KIND,
        "authority_digest": authority_digest,
        "effect_digest": effect_digest,
        "outcome_digest": outcome_digest,
        "checkpoint_digest": checkpoint_digest,
        "previous_checkpoint_digest": previous_checkpoint_digest,
        "sequence": sequence,
        "execution_domain": execution_domain,
    }


def sign_witness_receipt(
    statement: Mapping[str, Any],
    *,
    signer_id: str,
    operator_id: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
) -> dict[str, Any]:
    """Record an operator's signed assertion of the *exact* statement digest.

    This primitive does NOT itself independently verify the reported outcome or
    checkpoint custody. Never place witness private keys with the executor.
    """
    _validate_statement_shape(statement)
    if not isinstance(signer_id, str) or not signer_id.strip():
        raise ProofRailError("signer_id_invalid")
    if not isinstance(operator_id, str) or not operator_id.strip():
        raise ProofRailError("operator_id_invalid")
    record = {
        "kind": RECEIPT_KIND,
        "statement_digest": hash_record(statement),
        "signer_id": signer_id,
        "operator_id": operator_id,
    }
    return sign_record(record, private_key, key_id=key_id)


def verify_witness_exchange(
    statement: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    ledger_path: str | Path,
    signed_checkpoint: Mapping[str, Any],
    checkpoint_public_key: Ed25519PublicKey | bytes,
    trusted_witnesses: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Any],
    minimum_distinct_operators: int = 2,
) -> dict[str, Any]:
    """Verify a witness quorum over a trusted, exact ProofRail commitment.

    expected MUST come from independently trusted policy/state, including the
    previous checkpoint digest and next sequence. Neither is inferred from
    statement or receipt values. A valid result certifies agreement on signed
    digests, not that the underlying provider truly performed the action.
    """
    errors: list[str] = []
    operators: set[str] = set()
    seen_signers: set[str] = set()
    if type(minimum_distinct_operators) is not int or minimum_distinct_operators < 2:
        raise ProofRailError("independent_operator_threshold_invalid")
    if not isinstance(trusted_witnesses, Mapping) or not trusted_witnesses:
        raise ProofRailError("trusted_witnesses_missing")
    if not isinstance(expected, Mapping) or set(expected) != (FIELDS - {"kind"}):
        raise ProofRailError("independent_expected_statement_missing")
    _validate_statement_shape(statement)
    for field in sorted(FIELDS - {"kind"}):
        if statement[field] != expected[field]:
            errors.append(f"expected_{field}_mismatch")

    if (statement["sequence"] == 1) != (
        statement["previous_checkpoint_digest"] == "GENESIS"
    ):
        errors.append("previous_checkpoint_sequence_invalid")

    try:
        checkpoint_result = verify_checkpoint(
            signed_checkpoint, ledger_path, public_key=checkpoint_public_key
        )
        if not checkpoint_result["valid"]:
            errors.append("checkpoint_invalid")
        if statement["checkpoint_digest"] != hash_record(signed_checkpoint):
            errors.append("checkpoint_digest_mismatch")
    except (ProofRailError, KeyError, ValueError, TypeError, OSError):
        errors.append("checkpoint_invalid")

    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ProofRailError("receipts_invalid")
    if len(receipts) > 100:
        raise ProofRailError("too_many_receipts")
    subject_digest = hash_record(statement)

    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, Mapping):
            errors.append(f"receipt_{index}_not_object")
            continue
        signer_id = receipt.get("signer_id")
        if not isinstance(signer_id, str):
            errors.append(f"receipt_{index}_signer_invalid")
            continue
        if signer_id in seen_signers:
            errors.append(f"receipt_{index}_duplicate_signer")
            continue
        seen_signers.add(signer_id)
        roster = trusted_witnesses.get(signer_id)
        if not isinstance(roster, Mapping):
            errors.append(f"receipt_{index}_unknown_signer")
            continue
        operator_id = roster.get("operator_id")
        if (not isinstance(operator_id, str) or not operator_id
            or receipt.get("operator_id") != operator_id
            or receipt.get("kind") != RECEIPT_KIND
            or receipt.get("statement_digest") != subject_digest):
            errors.append(f"receipt_{index}_scope_mismatch")
            continue
        signature = receipt.get("signature")
        if (not isinstance(signature, Mapping)
            or not isinstance(roster.get("key_id"), str)
            or signature.get("key_id") != roster["key_id"]):
            errors.append(f"receipt_{index}_untrusted_key")
            continue
        try:
            verify_signature(receipt, roster["public_key"])
        except (ProofRailError, KeyError, ValueError, TypeError):
            errors.append(f"receipt_{index}_signature_invalid")
            continue
        operators.add(operator_id)

    if len(operators) < minimum_distinct_operators:
        errors.append("independent_operator_quorum_missing")
    return {
        "valid": not errors,
        "statement_digest": subject_digest,
        "distinct_operators": sorted(operators),
        "required_distinct_operators": minimum_distinct_operators,
        "checkpoint_bound": "checkpoint_invalid" not in errors
                            and "checkpoint_digest_mismatch" not in errors,
        "externally_retained_checkpoint_proven": False,
        "external_effect_proven": False,
        "errors": errors,
    }


def _validate_statement_shape(statement: Mapping[str, Any]) -> None:
    if not isinstance(statement, Mapping) or set(statement) != FIELDS:
        raise ProofRailError("witness_statement_shape_invalid")
    if statement.get("kind") != KIND:
        raise ProofRailError("witness_statement_kind_invalid")
    build_witness_statement(
        authority_digest=statement["authority_digest"],
        effect_digest=statement["effect_digest"],
        outcome_digest=statement["outcome_digest"],
        checkpoint_digest=statement["checkpoint_digest"],
        previous_checkpoint_digest=statement["previous_checkpoint_digest"],
        sequence=statement["sequence"],
        execution_domain=statement["execution_domain"],
    )

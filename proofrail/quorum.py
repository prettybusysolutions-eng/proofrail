from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import ProofRailError
from .crypto import hash_record, sign_record, verify_signature


def observation_subject(action: Mapping[str, Any]) -> str:
    execution = action.get("execution")
    if not isinstance(execution, Mapping):
        raise ProofRailError("Observation action is missing execution details")
    return hash_record(
        {
            "kind": "proofrail.observation-subject.v0.5.1",
            "action_type": action.get("action_type"),
            "execution": dict(execution),
        }
    )


def sign_attestation(
    *,
    kind: str,
    subject_digest: str,
    statement: Mapping[str, Any],
    signer_id: str,
    signer_role: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
) -> dict[str, Any]:
    if not kind.strip() or not signer_id.strip() or not signer_role.strip():
        raise ProofRailError("Attestation identity fields are required")
    _require_digest(subject_digest, "subject_digest")
    record = {
        "kind": kind,
        "subject_digest": subject_digest,
        "statement": dict(statement),
        "statement_hash": hash_record(
            {"kind": "proofrail.quorum-statement.v0.5.1", "statement": dict(statement)}
        ),
        "signer": {"principal_id": signer_id, "role": signer_role},
    }
    return sign_record(record, private_key, key_id=key_id)


def verify_quorum(
    attestations: Sequence[Mapping[str, Any]],
    *,
    trusted_signers: Mapping[str, tuple[str, Ed25519PublicKey | bytes]],
    threshold: int,
    expected_kind: str,
    expected_subject_digest: str,
) -> dict[str, Any]:
    if threshold < 1:
        raise ProofRailError("Quorum threshold must be positive")
    if threshold > len(trusted_signers):
        raise ProofRailError("Quorum threshold exceeds trusted signer count")
    verified_by_signer: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    verified_attestations: list[Mapping[str, Any]] = []
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for attestation in attestations:
        signer = attestation.get("signer")
        if not isinstance(signer, Mapping):
            continue
        signer_id = signer.get("principal_id")
        trusted = trusted_signers.get(str(signer_id))
        if trusted is None:
            continue
        expected_role, public_key = trusted
        if signer.get("role") != expected_role:
            continue
        if attestation.get("kind") != expected_kind:
            continue
        if attestation.get("subject_digest") != expected_subject_digest:
            continue
        try:
            verify_signature(attestation, public_key)
        except ProofRailError:
            continue
        candidate_hash = attestation.get("statement_hash")
        if not isinstance(candidate_hash, str):
            continue
        statement = attestation.get("statement")
        if not isinstance(statement, Mapping):
            continue
        expected_statement_hash = hash_record(
            {
                "kind": "proofrail.quorum-statement.v0.5.1",
                "statement": dict(statement),
            }
        )
        if candidate_hash != expected_statement_hash:
            continue
        verified_by_signer[str(signer_id)].append(attestation)
        verified_attestations.append(attestation)
    equivocal_signers: set[str] = set()
    for signer_id, signer_attestations in verified_by_signer.items():
        statement_hashes = {
            str(attestation["statement_hash"]) for attestation in signer_attestations
        }
        if len(statement_hashes) != 1:
            equivocal_signers.add(signer_id)
            continue
        groups[next(iter(statement_hashes))].append(signer_attestations[0])
    qualifying = [group for group in groups.values() if len(group) >= threshold]
    conflict = len(qualifying) > 1
    accepted = max(
        groups.values(),
        key=lambda group: (len(group), sorted(str(item["record_hash"]) for item in group)),
        default=[],
    )
    signer_ids = {
        str(attestation["signer"]["principal_id"]) for attestation in accepted
    }
    met = len(accepted) >= threshold and not conflict
    root = hash_record(
        {
            "kind": "proofrail.quorum-root.v0.5.1",
            "attestation_hashes": sorted(
                str(attestation["record_hash"]) for attestation in verified_attestations
            ),
            "threshold": threshold,
        }
    )
    return {
        "met": met,
        "threshold": threshold,
        "accepted": len(accepted),
        "signers": sorted(signer_ids),
        "statement": dict(accepted[0]["statement"]) if met else None,
        "observation_root": root,
        "conflict": conflict,
        "equivocal_signers": sorted(equivocal_signers),
    }


class QuorumObservationAdapter:
    """Execute with one adapter, reconcile only through signed M-of-N observers."""

    def __init__(
        self,
        *,
        executor_adapter: Any,
        observation_sources: Mapping[str, Any],
        trusted_observers: Mapping[str, tuple[str, Ed25519PublicKey | bytes]],
        threshold: int,
    ) -> None:
        self.executor_adapter = executor_adapter
        self.observation_sources = dict(observation_sources)
        self.trusted_observers = dict(trusted_observers)
        self.threshold = threshold

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        return self.executor_adapter.execute(action, idempotency_key=idempotency_key)

    def observe(self, action: dict[str, Any]) -> dict[str, Any]:
        subject_digest = observation_subject(action)
        attestations = [
            source.observe(action)
            for source in self.observation_sources.values()
        ]
        quorum = verify_quorum(
            attestations,
            trusted_signers=self.trusted_observers,
            threshold=self.threshold,
            expected_kind="proofrail.github-observation.v0.5.1",
            expected_subject_digest=subject_digest,
        )
        statement = quorum.get("statement") or {}
        return {
            "provider": "github-quorum",
            "quorum_met": quorum["met"],
            "threshold": quorum["threshold"],
            "accepted": quorum["accepted"],
            "signers": quorum["signers"],
            "observation_root": quorum["observation_root"],
            "merged": quorum["met"] and statement.get("merged") is True,
            "merge_commit_sha": (
                statement.get("merge_commit_sha") if quorum["met"] else None
            ),
        }


def _require_digest(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ProofRailError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProofRailError(f"{name} must be hexadecimal") from exc

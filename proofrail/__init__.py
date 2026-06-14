"""ProofRail evidence-bound action gate."""

from .core import (
    GateDecision,
    Ledger,
    ProofRailError,
    approve_action,
    evaluate_action,
    sign_document,
    verify_document,
)
from .checkpoint import (
    create_checkpoint,
    export_ledger,
    merkle_root,
    verify_checkpoint,
    verify_ledger,
)
from .audit_export import (
    ecs_security_events,
    jsonl_audit_export,
    permit_lifecycle_report,
    reason_code_summary,
)
from .crypto import canonical_json, hash_record, sign_record, verify_signature
from .anchor import create_anchor, verify_anchor
from .reproduce import reproduce_artifact
from .permit import (
    PermitError,
    consume_permit,
    execute_github_merge,
    mint_permit,
    verify_permit,
)
from .migration import (
    execute_database_migration,
    migration_digest,
    mint_database_migration_permit,
    verify_database_migration_permit,
)
from .rbac import AuthorizationError, Principal, ROLE_PERMISSIONS
from .quorum import (
    QuorumObservationAdapter,
    observation_subject,
    sign_attestation,
    verify_quorum,
)
from .trust import (
    create_trust_checkpoint,
    next_trust_checkpoint,
    read_trust_checkpoint,
    replay_registry_root,
    verify_trust_checkpoint,
    write_trust_checkpoint,
)

__all__ = [
    "GateDecision",
    "Ledger",
    "ProofRailError",
    "approve_action",
    "AuthorizationError",
    "canonical_json",
    "consume_permit",
    "create_anchor",
    "create_checkpoint",
    "create_trust_checkpoint",
    "evaluate_action",
    "ecs_security_events",
    "execute_github_merge",
    "execute_database_migration",
    "export_ledger",
    "hash_record",
    "jsonl_audit_export",
    "merkle_root",
    "migration_digest",
    "mint_permit",
    "mint_database_migration_permit",
    "PermitError",
    "permit_lifecycle_report",
    "Principal",
    "QuorumObservationAdapter",
    "reason_code_summary",
    "reproduce_artifact",
    "ROLE_PERMISSIONS",
    "next_trust_checkpoint",
    "observation_subject",
    "read_trust_checkpoint",
    "replay_registry_root",
    "sign_attestation",
    "sign_document",
    "sign_record",
    "verify_document",
    "verify_checkpoint",
    "verify_anchor",
    "verify_ledger",
    "verify_database_migration_permit",
    "verify_permit",
    "verify_signature",
    "verify_quorum",
    "verify_trust_checkpoint",
    "write_trust_checkpoint",
]

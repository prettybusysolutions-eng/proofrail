"""OpenClaw orchestration bridge for the ProofRail kernel."""

from .bridge import AdapterRegistry, OpenClawProofRailBridge, SubprocessAdapter
from .repository_change import (
    ACTION_TYPE as REPOSITORY_CHANGE_ACTION_TYPE,
    RepositoryAuthorityError,
    XzeniaCoderRepositoryAdapter,
    canonical_job_digest,
    canonicalize_job,
    consume_repository_change_authority,
    load_consumption_verification_key,
    mint_repository_change_authority,
    mint_consumption_grant,
    parameters_from_job,
    read_canonical_job_file,
    reconcile_repository_change,
    reconciled_artifact_manifest,
    repository_change_parameters,
    verify_consumption_grant,
    write_consumption_trust_store,
)

__all__ = [
    "AdapterRegistry",
    "OpenClawProofRailBridge",
    "SubprocessAdapter",
    "REPOSITORY_CHANGE_ACTION_TYPE",
    "RepositoryAuthorityError",
    "XzeniaCoderRepositoryAdapter",
    "canonical_job_digest",
    "canonicalize_job",
    "consume_repository_change_authority",
    "load_consumption_verification_key",
    "mint_repository_change_authority",
    "mint_consumption_grant",
    "parameters_from_job",
    "read_canonical_job_file",
    "reconcile_repository_change",
    "reconciled_artifact_manifest",
    "repository_change_parameters",
    "verify_consumption_grant",
    "write_consumption_trust_store",
]

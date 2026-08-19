"""OpenClaw orchestration bridge for the ProofRail kernel."""

from .bridge import AdapterRegistry, OpenClawProofRailBridge, SubprocessAdapter
from .repository_change import (
    ACTION_TYPE as REPOSITORY_CHANGE_ACTION_TYPE,
    RepositoryAuthorityError,
    XzeniaCoderRepositoryAdapter,
    canonical_job_digest,
    canonicalize_job,
    consume_repository_change_authority,
    mint_repository_change_authority,
    mint_consumption_grant,
    parameters_from_job,
    read_canonical_job_file,
    reconcile_repository_change,
    repository_change_parameters,
    verify_consumption_grant,
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
    "mint_repository_change_authority",
    "mint_consumption_grant",
    "parameters_from_job",
    "read_canonical_job_file",
    "reconcile_repository_change",
    "repository_change_parameters",
    "verify_consumption_grant",
]

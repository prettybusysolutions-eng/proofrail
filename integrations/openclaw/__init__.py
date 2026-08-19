"""OpenClaw orchestration bridge for the ProofRail kernel."""

from .bridge import AdapterRegistry, OpenClawProofRailBridge, SubprocessAdapter
from .repository_change import (
    ACTION_TYPE as REPOSITORY_CHANGE_ACTION_TYPE,
    RepositoryAuthorityError,
    XzeniaCoderRepositoryAdapter,
    consume_repository_change_authority,
    mint_repository_change_authority,
    parameters_from_job,
    reconcile_repository_change,
    repository_change_parameters,
)

__all__ = [
    "AdapterRegistry",
    "OpenClawProofRailBridge",
    "SubprocessAdapter",
    "REPOSITORY_CHANGE_ACTION_TYPE",
    "RepositoryAuthorityError",
    "XzeniaCoderRepositoryAdapter",
    "consume_repository_change_authority",
    "mint_repository_change_authority",
    "parameters_from_job",
    "reconcile_repository_change",
    "repository_change_parameters",
]

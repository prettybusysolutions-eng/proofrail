from __future__ import annotations

from dataclasses import dataclass

from .core import ProofRailError


PILOT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "proposer": frozenset({"intent:create", "evidence:create"}),
    "verifier": frozenset({"evaluation:create", "permit:mint", "policy:read"}),
    "executor": frozenset({"action:execute", "policy:read"}),
    "reconciler": frozenset(
        {"outcome:reconcile", "audit:read", "policy:read"}
    ),
    "learner": frozenset({"proposal:create", "policy:read"}),
    "governor": frozenset(
        {"policy:publish", "policy:activate", "policy:read", "audit:read"}
    ),
    "auditor": frozenset(
        {
            "ledger:read",
            "checkpoint:read",
            "audit:read",
            "audit:export",
            "policy:read",
        }
    ),
}

LEGACY_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(
        permission
        for permissions in PILOT_ROLE_PERMISSIONS.values()
        for permission in permissions
    ),
    "approver": frozenset({"policy:read", "action:approve", "audit:export"}),
    "operator": frozenset({"policy:read", "action:execute"}),
}

ROLE_PERMISSIONS = {**PILOT_ROLE_PERMISSIONS, **LEGACY_ROLE_PERMISSIONS}


class AuthorizationError(ProofRailError):
    def __init__(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        role: str | None,
        permission: str,
    ):
        self.tenant_id = tenant_id
        self.principal_id = principal_id
        self.role = role
        self.permission = permission
        super().__init__(
            f"Principal {principal_id!r} with role {role!r} lacks "
            f"{permission!r} in tenant {tenant_id!r}"
        )


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    principal_id: str
    role: str

    def can(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise AuthorizationError(
                tenant_id=self.tenant_id,
                principal_id=self.principal_id,
                role=self.role,
                permission=permission,
            )


def authorize_role(
    *,
    tenant_id: str,
    principal_id: str,
    role: str | None,
    permission: str,
) -> Principal:
    if role not in ROLE_PERMISSIONS:
        raise AuthorizationError(
            tenant_id=tenant_id,
            principal_id=principal_id,
            role=role,
            permission=permission,
        )
    principal = Principal(tenant_id, principal_id, role)
    principal.require(permission)
    return principal

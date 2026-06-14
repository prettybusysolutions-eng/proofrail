from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import ProofRailError, digest_document, utc_now
from .quorum import verify_quorum
from .rbac import ROLE_PERMISSIONS, authorize_role


@dataclass(frozen=True)
class PolicyVersion:
    tenant_id: str
    policy_name: str
    version: int
    digest: str
    document: dict[str, Any]
    active: bool

    @property
    def reference(self) -> str:
        return f"{self.tenant_id}/{self.policy_name}@{self.version}:{self.digest}"


class ControlPlane:
    """Small multi-tenant authority for identities and immutable policies."""

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_tenant(self, name: str) -> str:
        if not name.strip():
            raise ProofRailError("Tenant name is required")
        tenant_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tenants(tenant_id, name, created_at) VALUES (?, ?, ?)",
                (tenant_id, name.strip(), self._timestamp()),
            )
        return tenant_id

    def grant_role(self, tenant_id: str, principal_id: str, role: str) -> None:
        if role not in ROLE_PERMISSIONS:
            raise ProofRailError(f"Unknown role: {role}")
        self._require_tenant(tenant_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO principals(tenant_id, principal_id, role, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, principal_id)
                DO UPDATE SET role = excluded.role
                """,
                (tenant_id, principal_id, role, self._timestamp()),
            )

    def authorize(self, tenant_id: str, principal_id: str, permission: str) -> None:
        role = self.principal_role(tenant_id, principal_id)
        authorize_role(
            tenant_id=tenant_id,
            principal_id=principal_id,
            role=role,
            permission=permission,
        )

    def principal_role(self, tenant_id: str, principal_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM principals WHERE tenant_id = ? AND principal_id = ?",
                (tenant_id, principal_id),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def identity_root(self, tenant_id: str) -> str:
        self._require_tenant(tenant_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT principal_id, role FROM principals
                WHERE tenant_id = ? ORDER BY principal_id
                """,
                (tenant_id,),
            ).fetchall()
        return digest_document(
            {
                "kind": "proofrail.identity-root.v0.4",
                "tenant_id": tenant_id,
                "principals": [
                    {"principal_id": row[0], "role": row[1]}
                    for row in rows
                ],
            }
        )

    def publish_policy(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        policy_name: str,
        document: dict[str, Any],
    ) -> PolicyVersion:
        self.authorize(tenant_id, principal_id, "policy:publish")
        if not policy_name.strip():
            raise ProofRailError("Policy name is required")
        digest = digest_document(document)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM policies WHERE tenant_id = ? AND policy_name = ?",
                (tenant_id, policy_name),
            ).fetchone()
            version = int(row[0]) + 1
            connection.execute(
                """
                INSERT INTO policies(
                    tenant_id, policy_name, version, digest, document_json,
                    active, published_by, published_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    tenant_id,
                    policy_name,
                    version,
                    digest,
                    json.dumps(document, sort_keys=True, separators=(",", ":")),
                    principal_id,
                    self._timestamp(),
                ),
            )
            connection.commit()
        return PolicyVersion(tenant_id, policy_name, version, digest, document, False)

    def activate_policy(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        policy_name: str,
        version: int,
    ) -> PolicyVersion:
        self.authorize(tenant_id, principal_id, "policy:activate")
        return self._activate_policy(
            tenant_id=tenant_id,
            policy_name=policy_name,
            version=version,
            allow_rollback=False,
        )

    def activate_policy_with_quorum(
        self,
        *,
        tenant_id: str,
        policy_name: str,
        version: int,
        approvals: list[dict[str, Any]],
        trusted_governors: dict[str, tuple[str, Any]],
        threshold: int,
    ) -> PolicyVersion:
        target = self._get_policy(tenant_id, policy_name, version)
        quorum = verify_quorum(
            approvals,
            trusted_signers=trusted_governors,
            threshold=threshold,
            expected_kind="proofrail.policy-promotion-approval.v0.5.1",
            expected_subject_digest=target.digest,
        )
        statement = quorum.get("statement")
        if not quorum["met"] or not isinstance(statement, dict):
            raise ProofRailError("Governor quorum not met")
        expected = {
            "tenant_id": tenant_id,
            "policy_name": policy_name,
            "version": version,
            "policy_digest": target.digest,
            "action": statement.get("action"),
        }
        if statement != expected or statement["action"] not in {"promote", "rollback"}:
            raise ProofRailError("Governor quorum statement does not match policy target")
        return self._activate_policy(
            tenant_id=tenant_id,
            policy_name=policy_name,
            version=version,
            allow_rollback=statement["action"] == "rollback",
        )

    def _activate_policy(
        self,
        *,
        tenant_id: str,
        policy_name: str,
        version: int,
        allow_rollback: bool,
    ) -> PolicyVersion:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                """
                SELECT version FROM policies
                WHERE tenant_id = ? AND policy_name = ? AND active = 1
                """,
                (tenant_id, policy_name),
            ).fetchone()
            if active is not None and version < int(active[0]) and not allow_rollback:
                raise ProofRailError("Stale policy activation requires rollback quorum")
            row = connection.execute(
                """
                SELECT digest, document_json FROM policies
                WHERE tenant_id = ? AND policy_name = ? AND version = ?
                """,
                (tenant_id, policy_name, version),
            ).fetchone()
            if row is None:
                raise ProofRailError("Policy version not found")
            connection.execute(
                "UPDATE policies SET active = 0 WHERE tenant_id = ? AND policy_name = ?",
                (tenant_id, policy_name),
            )
            connection.execute(
                """
                UPDATE policies SET active = 1
                WHERE tenant_id = ? AND policy_name = ? AND version = ?
                """,
                (tenant_id, policy_name, version),
            )
            connection.commit()
        return PolicyVersion(
            tenant_id,
            policy_name,
            version,
            row[0],
            json.loads(row[1]),
            True,
        )

    def _get_policy(
        self,
        tenant_id: str,
        policy_name: str,
        version: int,
    ) -> PolicyVersion:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT digest, document_json, active FROM policies
                WHERE tenant_id = ? AND policy_name = ? AND version = ?
                """,
                (tenant_id, policy_name, version),
            ).fetchone()
        if row is None:
            raise ProofRailError("Policy version not found")
        return PolicyVersion(
            tenant_id,
            policy_name,
            version,
            row[0],
            json.loads(row[1]),
            bool(row[2]),
        )

    def get_active_policy(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        policy_name: str,
    ) -> PolicyVersion:
        self.authorize(tenant_id, principal_id, "policy:read")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT version, digest, document_json FROM policies
                WHERE tenant_id = ? AND policy_name = ? AND active = 1
                """,
                (tenant_id, policy_name),
            ).fetchone()
        if row is None:
            raise ProofRailError("No active policy")
        return PolicyVersion(
            tenant_id,
            policy_name,
            int(row[0]),
            row[1],
            json.loads(row[2]),
            True,
        )

    def _require_tenant(self, tenant_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        if row is None:
            raise ProofRailError("Unknown tenant")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS principals (
                    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                    principal_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, principal_id)
                );
                CREATE TABLE IF NOT EXISTS policies (
                    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                    policy_name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0,
                    published_by TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, policy_name, version),
                    UNIQUE(tenant_id, policy_name, digest)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_policy
                ON policies(tenant_id, policy_name) WHERE active = 1;
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _timestamp() -> str:
        return utc_now().isoformat().replace("+00:00", "Z")

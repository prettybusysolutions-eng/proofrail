from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from proofrail.core import ProofRailError
from proofrail.crypto import hash_record
from proofrail.migration import migration_digest


class SQLiteMigrationAdapter:
    """Execute one exact SQLite migration and independently observe its schema."""

    def __init__(self, database: str | Path, *, database_id: str):
        if not database_id.strip():
            raise ProofRailError("database_id is required")
        self.database = Path(database)
        self.database_id = database_id
        self._resolved_database = self._resolve_database()

    def observe(self, action: dict[str, Any]) -> dict[str, Any]:
        execution = self._require_target(action)
        fingerprint = self._instance_fingerprint()
        self._require_instance(execution, fingerprint)
        connection = self._connect_checked(read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()
        schema = [
            {
                "type": row[0],
                "name": row[1],
                "table": row[2],
                "sql": row[3],
            }
            for row in rows
        ]
        return {
            "provider": "sqlite",
            "database_id": self.database_id,
            "database_instance_fingerprint": fingerprint,
            "user_version": user_version,
            "schema_root": hash_record(
                {
                    "kind": "proofrail.sqlite-schema.v0.6",
                    "database_id": self.database_id,
                    "user_version": user_version,
                    "schema": schema,
                }
            ),
            "schema": schema,
        }

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        execution = self._require_target(action)
        fingerprint = self._instance_fingerprint()
        self._require_instance(execution, fingerprint)
        sql = execution.get("migration_sql")
        target_version = execution.get("target_version")
        if not isinstance(sql, str) or execution.get("migration_digest") != migration_digest(sql):
            raise ProofRailError("Migration source does not match its digest")
        if not isinstance(target_version, int) or target_version <= 0:
            raise ProofRailError("target_version must be a positive integer")

        connection = self._connect_checked(read_only=False)
        try:
            connection.set_authorizer(_migration_authorizer)
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {target_version};\nCOMMIT;"
            )
        except sqlite3.DatabaseError as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.DatabaseError:
                pass
            return {
                "contract": "proofrail.adapter-receipt.v1",
                "idempotency_key": idempotency_key,
                "remote_operation_id": None,
                "status": "failed",
                "side_effect_confirmed": False,
                "retry_safe": False,
                "receipt_evidence": {
                    "provider": "sqlite",
                    "database_id": self.database_id,
                    "error_type": type(exc).__name__,
                },
            }
        finally:
            connection.close()
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": f"sqlite:{self.database_id}:{target_version}",
            "status": "success",
            "side_effect_confirmed": False,
            "retry_safe": False,
            "receipt_evidence": {
                "provider": "sqlite",
                "database_id": self.database_id,
                "migration_digest": execution["migration_digest"],
                "target_version": target_version,
                "executor_claim": "migration_committed",
            },
        }

    def _require_target(self, action: dict[str, Any]) -> dict[str, Any]:
        execution = action.get("execution")
        if not isinstance(execution, dict):
            raise ProofRailError("Database migration requires execution details")
        if execution.get("database_id") != self.database_id:
            raise ProofRailError("Database identity mismatch")
        return execution

    def _resolve_database(self) -> Path:
        if self.database.is_symlink():
            raise ProofRailError("Database path cannot be a symlink")
        try:
            return self.database.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ProofRailError("Database does not exist") from exc

    def _file_identity(self) -> tuple[int, int]:
        if self.database.is_symlink():
            raise ProofRailError("Database path cannot be a symlink")
        try:
            resolved = self.database.resolve(strict=True)
            stat = os.stat(resolved)
        except FileNotFoundError as exc:
            raise ProofRailError("Database does not exist") from exc
        if resolved != self._resolved_database:
            raise ProofRailError("Database path target changed")
        return stat.st_dev, stat.st_ino

    def _instance_fingerprint(self) -> str:
        device, inode = self._file_identity()
        return hash_record(
            {
                "kind": "proofrail.sqlite-instance.v0.6",
                "database_id": self.database_id,
                "resolved_path": str(self._resolved_database),
                "device": device,
                "inode": inode,
            }
        )

    def _require_instance(
        self,
        execution: dict[str, Any],
        observed_fingerprint: str,
    ) -> None:
        expected = execution.get("database_instance_fingerprint")
        if expected is not None and expected != observed_fingerprint:
            raise ProofRailError("Database instance fingerprint mismatch")

    def _connect_checked(self, *, read_only: bool) -> sqlite3.Connection:
        before = self._file_identity()
        if read_only:
            connection = sqlite3.connect(
                f"file:{self._resolved_database}?mode=ro",
                uri=True,
            )
        else:
            connection = sqlite3.connect(
                self._resolved_database,
                isolation_level=None,
            )
        after = self._file_identity()
        if before != after:
            connection.close()
            raise ProofRailError("Database instance changed while opening")
        return connection


def _migration_authorizer(
    action: int,
    argument_one: str | None,
    argument_two: str | None,
    database_name: str | None,
    trigger_name: str | None,
) -> int:
    del argument_two, database_name, trigger_name
    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (argument_one or "").lower() != "user_version":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK

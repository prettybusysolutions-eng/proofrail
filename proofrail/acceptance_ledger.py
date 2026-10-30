"""SQLite-backed atomic acceptance reservation for the optional reliance gate.

The verifier's `already_accepted` callback is a *check* API by name, but
a read-then-write implementation is racy. This module provides a callback
that atomically RESERVES an accepted pair using SQLite uniqueness constraints.

It does not change or authorize an external provider operation, cannot make
the provider outcome true, and is not a distributed consensus or payment ledger.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA_VERSION = 1


def _scope(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 160:
        raise ValueError(f"{label} must be 1-160 characters")
    if value != value.strip() or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{label} contains whitespace/control ambiguity")
    return value


class SQLiteAcceptanceLedger:
    """Atomic, buyer-scoped local reservation store.

    **Reservation is permanent.** A crash after COMMIT but before the caller
    receives the verdict deliberately causes retry refusal, never a second
    acceptance. Do not use this as proof of payment or delivery.

    Each reservation is unique BOTH on (relying_party, authorization_hash)
    and on (relying_party, provider, provider_event_id). The first constraint
    prevents changing event IDs to reuse one authorization; the second
    prevents reusing a provider event with a different authorization.

    A distinct SQLite connection is created for each call so threads and
    processes on one host synchronize through SQLite's database writer lock.
    WAL, NFS/shared network filesystems and distributed failover are not
    validated. All callers must use the same trusted file and stable scope.
    """

    def __init__(self, path: str | Path, *, timeout_seconds: float = 5.0):
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than 0 and no more than 30")
        self.path = Path(path).absolute()
        self.timeout_seconds = float(timeout_seconds)
        if self.path.is_symlink():
            raise ValueError("acceptance database must not be a symlink")
        if not self.path.parent.is_dir():
            raise ValueError("acceptance database parent directory must exist")
        # Ensure a newly created ledger is private even with a permissive umask.
        try:
            fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("acceptance database must be an ordinary file")
        if os.name == "posix" and self.path.stat().st_mode & 0o077:
            raise PermissionError("acceptance database must not be group/world accessible")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, _SCHEMA_VERSION):
                    raise ValueError("unsupported acceptance ledger schema version")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS acceptance_reservations (
                        relying_party TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        authorization_hash TEXT NOT NULL,
                        provider_event_id TEXT NOT NULL,
                        reserved_at TEXT NOT NULL,
                        PRIMARY KEY (relying_party, authorization_hash),
                        UNIQUE (relying_party, provider, provider_event_id)
                    )
                    """
                )
                # Reject an unrelated database that happens to declare v1
                # but lacks the two replay constraints.
                indexes = connection.execute(
                    "PRAGMA index_list(acceptance_reservations)"
                ).fetchall()
                if sum(1 for row in indexes if row[2]) < 2:
                    raise ValueError("acceptance uniqueness constraints missing")
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path), timeout=self.timeout_seconds, isolation_level=None
        )
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def reserve(
        self, relying_party: str, provider: str,
        authorization_hash: str, provider_event_id: str,
    ) -> bool:
        """Insert once and commit; True if new, False if already reserved.

        All database failures are raised. The reliance verifier translates a
        callback failure into INSUFFICIENT_EVIDENCE rather than acceptance.
        """
        relying_party = _scope(relying_party, "relying_party")
        provider = _scope(provider, "provider")
        provider_event_id = _scope(provider_event_id, "provider_event_id")
        if not isinstance(authorization_hash, str) or not _HASH.fullmatch(authorization_hash):
            raise ValueError("authorization_hash must be 64 lowercase hex characters")
        # One atomic writer transaction, including uniqueness enforcement.
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO acceptance_reservations
                    (relying_party, provider, authorization_hash,
                     provider_event_id, reserved_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        relying_party, provider, authorization_hash,
                        provider_event_id,
                        datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    ),
                )
                conn.execute("COMMIT")
                return True
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")
                return False
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def replay_guard(self, *, relying_party: str, provider: str) -> Callable[[str, str], bool]:
        """Return the reliance callback: True means reject, False means reserved.

        The callback MUST be called only after signature and policy validation.
        It reserves before a successful verdict; retry after a crash is refused.
        """
        relying_party = _scope(relying_party, "relying_party")
        provider = _scope(provider, "provider")

        def reserve_or_reject(authorization_hash: str, provider_event_id: str) -> bool:
            return not self.reserve(
                relying_party, provider, authorization_hash, provider_event_id
            )

        return reserve_or_reject

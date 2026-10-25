"""Buyer-owned monotonic checkpoint observer (local, not a SCITT/Rekor verifier).

A buyer trusts the issuer identity, checkpoint signer, exact expected claim,
and its own SQLite durability boundary. This module verifies signatures and
the current ledger but does not authenticate any transparency receipt or
establish an externally witnessed state. Never use it as a merge permit.

State is only rollback-resistant while the buyer's database remains trusted
and durable. Rollback of both this database and the issuer database remains
possible without another independently retained high-water mark.
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .core import ProofRailError
from .crypto import canonical_json
from .scitt_checkpoint import verify_scitt_checkpoint_statement


def stream_key(issuer: str, subject: str, execution_domain: str) -> str:
    """Stable, collision-resistant identity for one checkpoint history."""
    if any(not isinstance(v, str) or not v.strip() or len(v) > 1024
           for v in (issuer, subject, execution_domain)):
        raise ProofRailError("stream_identity_invalid")
    return hashlib.sha256(canonical_json({
        "issuer": issuer, "subject": subject, "execution_domain": execution_domain,
    })).hexdigest()


class BuyerHighWaterStore:
    """Single-writer transactions for checkpoint continuity in buyer custody.

    SQLite's atomic commit protects concurrent check-and-update, not rollback
    of the database file itself. Never share its path with an issuer/agent.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise ProofRailError("in_memory_highwater_not_durable")
        if self.path.exists() and self.path.is_symlink():
            raise ProofRailError("symlink_highwater_forbidden")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS checkpoint_heads (
                    stream_key TEXT PRIMARY KEY NOT NULL,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    execution_domain TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence > 0),
                    checkpoint_digest TEXT NOT NULL,
                    previous_checkpoint_digest TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def get_head(
        self, *, issuer: str, subject: str, execution_domain: str
    ) -> dict[str, Any] | None:
        key = stream_key(issuer, subject, execution_domain)
        with self._connect() as db:
            row = db.execute(
                "SELECT sequence, checkpoint_digest, previous_checkpoint_digest "
                "FROM checkpoint_heads WHERE stream_key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        return {
            "issuer": issuer, "subject": subject, "execution_domain": execution_domain,
            "sequence": row[0], "checkpoint_digest": row[1],
            "previous_checkpoint_digest": row[2],
        }

    def observe_locally_verified(
        self,
        *,
        statement: bytes,
        issuer_public_key: Ed25519PublicKey,
        expected_issuer: str,
        expected_subject: str,
        expected_key_id: bytes,
        expected_execution_domain: str,
        expected_claim: Mapping[str, Any],
        signed_checkpoint: Mapping[str, Any],
        checkpoint_public_key: Ed25519PublicKey,
        ledger_path: str | Path,
        allow_legacy_eddsa: bool = False,
    ) -> dict[str, Any]:
        """Advance a buyer-local experimental watermark after real sig checks.

        A caller must independently pin issuer keys, checkpoint signer, and
        the expected claim. These values cannot safely be taken uncritically
        from the untrusted bundle. This performs NO live log inclusion check.
        """
        if not isinstance(expected_claim, Mapping):
            raise ProofRailError("expected_claim_missing")
        key = stream_key(
            expected_issuer, expected_subject, expected_execution_domain
        )
        if expected_claim.get("execution_domain") != expected_execution_domain:
            raise ProofRailError("execution_domain_not_pinned")
        check = verify_scitt_checkpoint_statement(
            statement, issuer_public_key=issuer_public_key,
            expected_issuer=expected_issuer,
            expected_subject=expected_subject, expected_key_id=expected_key_id,
            expected_claim=expected_claim,
            checkpoint=signed_checkpoint,
            checkpoint_public_key=checkpoint_public_key,
            ledger_path=str(ledger_path),
            allow_legacy_eddsa=allow_legacy_eddsa,
            require_transparency_receipt=False,
        )
        if not check["valid"]:
            raise ProofRailError(
                "signed_statement_or_checkpoint_invalid: " + ", ".join(check["errors"])
            )
        if check["transparency_receipt_verified"]:
            raise ProofRailError("unexpected_external_receipt_claim")
        seq = expected_claim["sequence"]
        digest = expected_claim["checkpoint_digest"]
        predecessor = expected_claim["previous_checkpoint_digest"]
        with self._connect() as db:
            # BEGIN IMMEDIATE makes the check and the update one serialization
            # point across processes using this DB file.
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = db.execute(
                    "SELECT sequence, checkpoint_digest FROM checkpoint_heads "
                    "WHERE stream_key=?", (key,)
                ).fetchone()
                if previous is None:
                    if seq != 1 or predecessor != "GENESIS":
                        raise ProofRailError("initial_checkpoint_must_be_genesis")
                    db.execute(
                        "INSERT INTO checkpoint_heads "
                        "(stream_key,issuer,subject,execution_domain,sequence,"
                        "checkpoint_digest,previous_checkpoint_digest) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (key, expected_issuer, expected_subject,
                         expected_execution_domain, seq, digest, predecessor),
                    )
                    status = "locally_recorded_genesis"
                else:
                    current_seq, current_digest = previous
                    if seq < current_seq:
                        raise ProofRailError("checkpoint_rollback_detected")
                    if seq == current_seq:
                        if digest != current_digest:
                            raise ProofRailError("checkpoint_fork_detected")
                        # Exact same state is idempotent but never authorizes
                        # another action or proves external log inclusion.
                        status = "already_recorded"
                    elif seq != current_seq + 1:
                        raise ProofRailError("checkpoint_sequence_gap")
                    elif predecessor != current_digest:
                        raise ProofRailError("checkpoint_chain_break")
                    else:
                        db.execute(
                            "UPDATE checkpoint_heads SET sequence=?, "
                            "checkpoint_digest=?, previous_checkpoint_digest=? "
                            "WHERE stream_key=?",
                            (seq, digest, predecessor, key),
                        )
                        status = "locally_advanced"
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return {
            "status": status,
            "stream_key": key,
            "sequence": seq,
            "checkpoint_digest": digest,
            "issuer_signature_verified": True,
            "local_signed_checkpoint_verified": True,
            "rekor_inclusion_verified": False,
            "scitt_receipt_verified": False,
            "externally_anchored": False,
            "merge_authorized": False,
            "buyer_database_rollback_resistance_proven": False,
        }

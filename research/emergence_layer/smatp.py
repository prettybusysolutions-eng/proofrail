"""SMATP v0.1: a verifiable, durable *handoff* reference, not an LLM interceptor.

Requires cryptography. SQLite and loopback HTTP are development-only choices.
Never execute instructions in submitted payloads without separate authorization.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

VERSION = "smatp/0.1"
MAX_ENVELOPE_BYTES = 64 * 1024
MAX_TTL_SECONDS = 24 * 3600
AGENT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


class ProtocolError(ValueError):
    """Rejected untrusted protocol input."""


def canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProtocolError(f"Not canonical JSON: {exc}") from exc


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def unsigned(signed: dict) -> dict:
    return {key: value for key, value in signed.items() if key != "signature"}


def new_identity() -> tuple[Ed25519PrivateKey, str]:
    private = Ed25519PrivateKey.generate()
    return private, encode_public(private.public_key())


def encode_public(pub: Ed25519PublicKey) -> str:
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def key_id(pub_b64: str) -> str:
    try:
        raw = base64.b64decode(pub_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise ProtocolError("Invalid Ed25519 public key") from exc
    return hashlib.sha256(raw).hexdigest()[:24]


def sign(fields: dict, private: Ed25519PrivateKey) -> dict:
    result = dict(fields)
    result["signature"] = base64.b64encode(private.sign(canonical(fields))).decode("ascii")
    return result


def check_signature(message: dict, pub_b64: str) -> None:
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64, validate=True))
        signature = base64.b64decode(message["signature"], validate=True)
        public.verify(signature, canonical(unsigned(message)))
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise ProtocolError("Signature verification failed") from exc


def make_envelope(sender: str, recipient: str, capability: str, payload: Any,
                  private: Ed25519PrivateKey, *, ttl: int = 300,
                  idempotency_key: str | None = None, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    kid = key_id(encode_public(private.public_key()))
    fields = {
        "version": VERSION, "message_id": str(uuid.uuid4()),
        "sender": sender, "recipient": recipient, "sender_key_id": kid,
        "capability": capability, "payload": payload,
        "created_at": now, "expires_at": now + ttl,
        "nonce": secrets.token_hex(16),
        "idempotency_key": idempotency_key or str(uuid.uuid4()),
    }
    return sign(fields, private)


def make_receipt(message_id: str, actor: str, decision: str, previous_hash: str | None,
                 private: Ed25519PrivateKey, *, result: Any = None, now: int | None = None) -> dict:
    fields = {
        "version": VERSION, "receipt_id": str(uuid.uuid4()), "message_id": message_id,
        "actor": actor, "actor_key_id": key_id(encode_public(private.public_key())),
        "decision": decision, "result": result,
        "previous_receipt_hash": previous_hash,
        "created_at": int(time.time()) if now is None else now,
    }
    return sign(fields, private)


class Store:
    """Durable SQLite transport ledger, using atomic transactions for transitions."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=15,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT NOT NULL, key_id TEXT NOT NULL, pubkey TEXT NOT NULL,
            PRIMARY KEY (agent_id, key_id));
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY, sender TEXT NOT NULL, recipient TEXT NOT NULL,
            idempotency_key TEXT NOT NULL, nonce TEXT NOT NULL,
            envelope TEXT NOT NULL, envelope_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE(sender, idempotency_key), UNIQUE(sender, nonce));
        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id TEXT PRIMARY KEY, message_id TEXT NOT NULL,
            seq INTEGER NOT NULL, body TEXT NOT NULL, body_hash TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES messages(message_id),
            UNIQUE(message_id, seq));
        """)

    def close(self):
        self.db.close()

    def register_agent(self, agent_id: str, public_b64: str):
        """Operator-only enrollment. Intentionally not exposed through HTTP."""
        self._agent_check(agent_id)
        kid = key_id(public_b64)
        self.db.execute("INSERT OR IGNORE INTO agents VALUES (?, ?, ?)",
                        (agent_id, kid, public_b64))
        return kid

    @staticmethod
    def _agent_check(value: Any):
        if not isinstance(value, str) or not AGENT_PATTERN.fullmatch(value):
            raise ProtocolError("Invalid agent identifier")

    def _public_key(self, agent: str, kid: str) -> str:
        self._agent_check(agent)
        row = self.db.execute("SELECT pubkey FROM agents WHERE agent_id=? AND key_id=?",
                              (agent, kid)).fetchone()
        if not row:
            raise ProtocolError("Agent key is not registered")
        return row["pubkey"]

    @staticmethod
    def _validate_exact_fields(item: dict, fields: set[str]):
        if not isinstance(item, dict) or set(item) != fields:
            raise ProtocolError("Invalid protocol object or unexpected fields")

    def _check_envelope(self, env: dict):
        required = {"version", "message_id", "sender", "recipient", "sender_key_id",
                    "capability", "payload", "created_at", "expires_at", "nonce",
                    "idempotency_key", "signature"}
        self._validate_exact_fields(env, required)
        if len(canonical(env)) > MAX_ENVELOPE_BYTES:
            raise ProtocolError("Envelope exceeds 64 KiB")
        if env["version"] != VERSION:
            raise ProtocolError("Unsupported protocol version")
        self._agent_check(env["sender"])
        self._agent_check(env["recipient"])
        if not isinstance(env["capability"], str) or not 1 <= len(env["capability"]) <= 128:
            raise ProtocolError("Invalid capability")
        for name in ("nonce", "idempotency_key"):
            if not isinstance(env[name], str) or not 1 <= len(env[name]) <= 128:
                raise ProtocolError(f"Invalid {name}")
        try:
            uuid.UUID(env["message_id"])
        except (TypeError, ValueError, AttributeError) as exc:
            raise ProtocolError("Invalid message_id") from exc
        issued, expires = env["created_at"], env["expires_at"]
        if type(issued) is not int or type(expires) is not int:
            raise ProtocolError("Timestamps must be integer Unix seconds")
        if expires <= issued or expires - issued > MAX_TTL_SECONDS:
            raise ProtocolError("Invalid expiration period")
        now = int(time.time())
        if issued > now + 300 or expires <= now:
            raise ProtocolError("Envelope too early or expired")
        pub = self._public_key(env["sender"], env["sender_key_id"])
        check_signature(env, pub)
        self._public_key(env["recipient"], self._any_key(env["recipient"]))

    def _any_key(self, agent_id):
        row = self.db.execute("SELECT key_id FROM agents WHERE agent_id=? LIMIT 1",
                              (agent_id,)).fetchone()
        if not row:
            raise ProtocolError("Recipient is not registered")
        return row["key_id"]

    def submit(self, env: dict) -> dict:
        self._check_envelope(env)
        body = canonical(env).decode("utf-8")
        sha = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT message_id, envelope_hash, status FROM messages "
                "WHERE (sender=? AND idempotency_key=?) OR message_id=? OR (sender=? AND nonce=?)",
                (env["sender"], env["idempotency_key"], env["message_id"],
                 env["sender"], env["nonce"])).fetchone()
            if existing:
                if existing["message_id"] == env["message_id"] and existing["envelope_hash"] == sha:
                    response = {"message_id": existing["message_id"], "status": existing["status"],
                                "duplicate": True}
                else:
                    raise ProtocolError("Replay or conflicting idempotency key")
            else:
                self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                                (env["message_id"], env["sender"], env["recipient"],
                                 env["idempotency_key"], env["nonce"], body, sha, "RECEIVED"))
                response = {"message_id": env["message_id"], "status": "RECEIVED", "duplicate": False}
            self.db.execute("COMMIT")
            return response
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _check_receipt(self, receipt: dict):
        self._validate_exact_fields(receipt, {"version", "receipt_id", "message_id", "actor",
                                              "actor_key_id", "decision", "result",
                                              "previous_receipt_hash", "created_at", "signature"})
        if len(canonical(receipt)) > MAX_ENVELOPE_BYTES:
            raise ProtocolError("Receipt exceeds 64 KiB")
        if receipt["version"] != VERSION:
            raise ProtocolError("Unsupported protocol version")
        for name in ("message_id", "receipt_id"):
            try:
                uuid.UUID(receipt[name])
            except (TypeError, ValueError, AttributeError) as exc:
                raise ProtocolError(f"Invalid {name}") from exc
        if receipt["decision"] not in ("ACCEPTED", "REJECTED", "COMPLETED", "FAILED"):
            raise ProtocolError("Invalid receipt decision")
        if type(receipt["created_at"]) is not int or abs(receipt["created_at"]-int(time.time())) > 300:
            raise ProtocolError("Receipt timestamp outside allowed window")
        pub = self._public_key(receipt["actor"], receipt["actor_key_id"])
        check_signature(receipt, pub)

    def append_receipt(self, receipt: dict) -> dict:
        self._check_receipt(receipt)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT recipient, status FROM messages WHERE message_id=?",
                                  (receipt["message_id"],)).fetchone()
            if not row:
                raise ProtocolError("Unknown message")
            if receipt["actor"] != row["recipient"]:
                raise ProtocolError("Only the recipient can acknowledge this message")
            if (row["status"], receipt["decision"]) not in {
                    ("RECEIVED", "ACCEPTED"), ("RECEIVED", "REJECTED"),
                    ("ACCEPTED", "COMPLETED"), ("ACCEPTED", "FAILED"),
                    ("ACCEPTED", "REJECTED")}:
                raise ProtocolError("Illegal state transition")
            if receipt["decision"] in {"COMPLETED", "FAILED"} and receipt["result"] is None:
                raise ProtocolError("Terminal execution receipt must include an outcome")
            prior = self.db.execute("SELECT seq, body_hash FROM receipts WHERE message_id=? "
                                    "ORDER BY seq DESC LIMIT 1", (receipt["message_id"],)).fetchone()
            expected = prior["body_hash"] if prior else None
            if receipt["previous_receipt_hash"] != expected:
                raise ProtocolError("Receipt chain mismatch")
            h = digest(receipt)
            seq = prior["seq"] + 1 if prior else 0
            self.db.execute("INSERT INTO receipts VALUES (?,?,?,?,?)",
                            (receipt["receipt_id"], receipt["message_id"], seq,
                             canonical(receipt).decode("utf-8"), h))
            self.db.execute("UPDATE messages SET status=? WHERE message_id=?",
                            (receipt["decision"], receipt["message_id"]))
            self.db.execute("COMMIT")
            return {"message_id": receipt["message_id"], "status": receipt["decision"], "receipt_hash": h}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def get_record(self, message_id: str) -> dict:
        row = self.db.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
        if not row:
            raise ProtocolError("Unknown message")
        receipts = self.db.execute("SELECT * FROM receipts WHERE message_id=? ORDER BY seq",
                                   (message_id,)).fetchall()
        return {"envelope": json.loads(row["envelope"]), "envelope_hash": row["envelope_hash"],
                "status": row["status"], "receipts": [json.loads(r["body"]) for r in receipts]}

    def last_receipt_hash(self, message_id: str) -> str | None:
        row = self.db.execute("SELECT body_hash FROM receipts WHERE message_id=? ORDER BY seq DESC LIMIT 1",
                              (message_id,)).fetchone()
        return row["body_hash"] if row else None

    def verify_record(self, message_id: str) -> bool:
        record = self.get_record(message_id)
        env = record["envelope"]
        if digest(env) != record["envelope_hash"]:
            raise ProtocolError("Stored envelope digest mismatch")
        check_signature(env, self._public_key(env["sender"], env["sender_key_id"]))
        state, last_hash = "RECEIVED", None
        saved = self.db.execute("SELECT seq, body, body_hash FROM receipts WHERE message_id=? ORDER BY seq",
                                (message_id,)).fetchall()
        for seq, (receipt, stored) in enumerate(zip(record["receipts"], saved)):
            if stored["seq"] != seq or digest(receipt) != stored["body_hash"]:
                raise ProtocolError("Stored receipt digest or sequence mismatch")
            self._check_receipt_signature_only(receipt)
            if receipt["message_id"] != message_id or receipt["actor"] != env["recipient"]:
                raise ProtocolError("Receipt ownership mismatch")
            if receipt["previous_receipt_hash"] != last_hash:
                raise ProtocolError("Receipt chain broken")
            target = receipt["decision"]
            if (state, target) not in {("RECEIVED", "ACCEPTED"), ("RECEIVED", "REJECTED"),
                                       ("ACCEPTED", "COMPLETED"), ("ACCEPTED", "FAILED"),
                                       ("ACCEPTED", "REJECTED")}:
                raise ProtocolError("Receipt order invalid")
            state, last_hash = target, digest(receipt)
        if state != record["status"]:
            raise ProtocolError("Stored state does not match receipt chain")
        return True

    def _check_receipt_signature_only(self, receipt):
        pub = self._public_key(receipt["actor"], receipt["actor_key_id"])
        check_signature(receipt, pub)

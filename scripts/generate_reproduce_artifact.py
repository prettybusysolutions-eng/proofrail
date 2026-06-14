#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from proofrail.anchor import create_anchor, encode_public_key
from proofrail.checkpoint import verify_ledger
from proofrail.crypto import sign_record
from proofrail.permit import consume_permit, mint_permit
from proofrail.trust import (
    EMPTY_ROOT,
    create_trust_checkpoint,
    next_trust_checkpoint,
    replay_registry_root,
)

ARTIFACT_TIME = datetime(2026, 6, 11, 23, 45, tzinfo=timezone.utc)
SOURCE = ROOT / "examples" / "github-merge-authority-artifact"
OUTPUT = ROOT / "examples" / "reproduce_artifact"
ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL_DIGEST = "5" * 64
SQLITE_HEADER_VERSION_OFFSET = 96
SQLITE_HEADER_VERSION = bytes.fromhex("002e91e0")


def generate(output: Path = OUTPUT) -> dict:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in (
        "proofrail-ledger.jsonl",
        "tampered-ledger.jsonl",
        "proofrail-checkpoint.json",
        "checkpoint-public-key.txt",
        "TRANSCRIPT.md",
    ):
        shutil.copyfile(SOURCE / name, output / name)
    shutil.copyfile(ROOT / "VALIDATION_REPORT.md", output / "VALIDATION_REPORT.md")
    shutil.copyfile(ROOT / "validation-results.json", output / "validation-results.json")

    checkpoint = _read_json(output / "proofrail-checkpoint.json")
    trust_key = _key("22")
    permit_trust_checkpoint = create_trust_checkpoint(
        replay_root=replay_registry_root(output / "replay-registry.sqlite3"),
        ledger_checkpoint_root=checkpoint["record_hash"],
        observation_root=EMPTY_ROOT,
        epoch=12,
        monotonic_counter=34,
        private_key=trust_key,
        key_id="reproduce-trust-checkpoint",
    )
    _write_json(output / "permit-trust-checkpoint.json", permit_trust_checkpoint)
    _write_key(output / "trust-checkpoint-public-key.txt", trust_key)

    verifier_key = _key("24")
    permit = mint_permit(
        identity_root=ROOTS["identity"],
        evidence_root=ROOTS["evidence"],
        policy_root=ROOTS["policy"],
        state_root=ROOTS["state"],
        approval_digest=APPROVAL_DIGEST,
        repository="example/repository",
        pull_number=42,
        expected_head_sha="abcdef1234567890",
        merge_method="squash",
        nonce="reproduce-valid-nonce-0001",
        expires_at=ARTIFACT_TIME + timedelta(days=1),
        issuer_principal_id="verifier:reproduce",
        issuer_role="verifier",
        private_key=verifier_key,
        key_id="reproduce-verifier",
        now=ARTIFACT_TIME,
        permit_id="proofrail-reproduce-valid-permit",
        trust={
            "replay_root": permit_trust_checkpoint["roots"]["replay"],
            "checkpoint_root": permit_trust_checkpoint["record_hash"],
            "observation_root": permit_trust_checkpoint["roots"]["observation"],
            "minimum_checkpoint_epoch": permit_trust_checkpoint["epoch"],
            "monotonic_counter": permit_trust_checkpoint["monotonic_counter"],
        },
    )
    _write_json(output / "valid-permit.json", permit)
    invalid_permit = deepcopy(permit)
    invalid_permit["effect"]["expected_head_sha"] = "deadbeef"
    _write_json(output / "invalid-permit.json", invalid_permit)
    _write_key(output / "verifier-public-key.txt", verifier_key)
    claim = consume_permit(
        permit,
        registry_path=output / "replay-registry.sqlite3",
        public_key=verifier_key.public_key(),
        expected_identity_root=ROOTS["identity"],
        expected_evidence_root=ROOTS["evidence"],
        expected_policy_root=ROOTS["policy"],
        expected_state_root=ROOTS["state"],
        expected_approval_digest=APPROVAL_DIGEST,
        repository=permit["effect"]["repository"],
        pull_number=permit["effect"]["pull_number"],
        expected_head_sha=permit["effect"]["expected_head_sha"],
        merge_method=permit["effect"]["merge_method"],
        executor_id="executor:reproduce",
        now=ARTIFACT_TIME + timedelta(minutes=1),
        trust_checkpoint=permit_trust_checkpoint,
        checkpoint_public_key=trust_key.public_key(),
    )
    trust_checkpoint = next_trust_checkpoint(
        permit_trust_checkpoint,
        registry_path=output / "replay-registry.sqlite3",
        private_key=trust_key,
        key_id="reproduce-trust-checkpoint",
    )
    _write_json(output / "trust-checkpoint.json", trust_checkpoint)
    executor_key = _key("26")
    consumption_receipt = sign_record(
        {
            "kind": "proofrail.permit-consumption-receipt.v0.5.2",
            "permit_hash": claim["permit_hash"],
            "nonce": permit["nonce"],
            "state": claim["state"],
            "executor_id": claim["executor_id"],
            "consumed_at": claim["consumed_at"],
            "next_replay_root": claim["next_replay_root"],
            "trust_checkpoint_before": permit_trust_checkpoint["record_hash"],
            "trust_checkpoint_after": trust_checkpoint["record_hash"],
        },
        executor_key,
        key_id="reproduce-executor",
    )
    _write_json(output / "consumption-receipt.json", consumption_receipt)
    _write_key(output / "executor-public-key.txt", executor_key)
    _finalize_registry(output / "replay-registry.sqlite3")

    anchor_key = _key("23")
    anchor = create_anchor(
        output / "proofrail-ledger.jsonl",
        trust_checkpoint_hash=trust_checkpoint["record_hash"],
        private_key=anchor_key,
        key_id="reproduce-anchor",
        anchor_provider="local-file",
        anchor_reference="file:anchor-public-key.txt",
        trust_checkpoint_present=True,
        now=ARTIFACT_TIME,
    )
    _write_json(output / "anchor.json", anchor)
    _write_key(output / "anchor-public-key.txt", anchor_key)

    _write_json(
        output / "permit-context.json",
        {
            "roots": ROOTS,
            "approval_digest": APPROVAL_DIGEST,
            "effect": permit["effect"],
            "verification_time": (
                ARTIFACT_TIME + timedelta(minutes=1)
            ).isoformat().replace("+00:00", "Z"),
            "trust": {
                "replay_root": permit_trust_checkpoint["roots"]["replay"],
                "checkpoint_root": permit_trust_checkpoint["record_hash"],
                "observation_root": permit_trust_checkpoint["roots"]["observation"],
                "checkpoint_epoch": permit_trust_checkpoint["epoch"],
                "monotonic_counter": permit_trust_checkpoint["monotonic_counter"],
            },
        },
    )

    manifest_key = _key("25")
    _write_key(output / "manifest-public-key.txt", manifest_key)
    files = {
        path.name: _sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file()
    }
    manifest = sign_record(
        {
            "kind": "proofrail.reproduction-manifest.v0.5.2",
            "created_at": ARTIFACT_TIME.isoformat().replace("+00:00", "Z"),
            "files": files,
            "validation_report_sha256": files["VALIDATION_REPORT.md"],
            "expected_checks": [
                "schemas_valid",
                "manifest_signature",
                "valid_permit_verifies",
                "invalid_permit_denied",
                "ledger_verifies",
                "checkpoint_verifies",
                "anchor_verifies",
                "trust_checkpoint_signature",
                "trust_checkpoint_verifies",
                "consumed_permit_verifies",
                "validation_report_hash_matches",
                "tampered_artifact_fails",
            ],
        },
        manifest_key,
        key_id="reproduce-manifest",
    )
    _write_json(output / "reproduction-manifest.json", manifest)
    return {
        "output": str(output),
        "files": len(files) + 1,
        "ledger_valid": verify_ledger(output / "proofrail-ledger.jsonl")["valid"],
        "checkpoint_hash": checkpoint["record_hash"],
        "trust_checkpoint_hash": trust_checkpoint["record_hash"],
        "anchor_hash": anchor["record_hash"],
        "manifest_hash": manifest["record_hash"],
    }


def _key(byte: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(byte * 32))


def _write_key(path: Path, key: Ed25519PrivateKey) -> None:
    path.write_text(encode_public_key(key.public_key()) + "\n", encoding="utf-8")


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finalize_registry(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.commit()
    finally:
        connection.close()
    data = bytearray(path.read_bytes())
    if data[:16] != b"SQLite format 3\x00" or len(data) < 100:
        raise RuntimeError("generated replay registry is not a valid SQLite file")
    # SQLite writes its library version into an informational header field.
    # Normalize it so identical logical registries have identical artifact bytes.
    data[SQLITE_HEADER_VERSION_OFFSET : SQLITE_HEADER_VERSION_OFFSET + 4] = (
        SQLITE_HEADER_VERSION
    )
    path.write_bytes(data)


if __name__ == "__main__":
    print(json.dumps(generate(), sort_keys=True))

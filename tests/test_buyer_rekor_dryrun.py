"""Check exact signed high-water continuity and strict offline Rekor request bytes.

All keys and receipts in this module are synthetic local fixtures; none is
an external transparency log, production buyer or real independent monitor.
"""
from __future__ import annotations

import base64
import json
import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

from proofrail.buyer_highwater import BuyerHighWaterStore
from proofrail.checkpoint import create_checkpoint
from proofrail.core import ProofRailError, digest_ledger_entry
from proofrail.crypto import hash_record
from proofrail.scitt_checkpoint import checkpoint_claim, sign_scitt_checkpoint_statement
from scripts.rekor_v2_dryrun import build_rekor_v2_request, main as rekor_main


ISSUER = "urn:proofrail:issuer:buyer-fixture"
SUBJECT = "urn:proofrail:stream:buyer-fixture"
DOMAIN = "github:owner/repo"


class BuyerHighWaterAndRekorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.issuer = Ed25519PrivateKey.generate()
        self.checkpoint_signer = Ed25519PrivateKey.generate()
        self.detached = ec.generate_private_key(ec.SECP256R1())
        self.store = BuyerHighWaterStore(self.root / "buyer-only.sqlite3")

    def snapshot(self, sequence, predecessor=None, count=None):
        if count is None:
            count = sequence
        ledger = self.root / f"ledger-{sequence}-{len(list(self.root.glob('ledger-*')))}.jsonl"
        records = []
        last = "GENESIS"
        for i in range(1, count + 1):
            item = {
                "kind": "proofrail.local-highwater-fixture.v0",
                "sequence": i,
                "previous_hash": last,
                "observation": f"fixture-{i}",
            }
            item["entry_hash"] = digest_ledger_entry(item)
            records.append(json.dumps(item, sort_keys=True))
            last = item["entry_hash"]
        ledger.write_text("\n".join(records) + "\n")
        checkpoint = create_checkpoint(
            ledger, private_key=self.checkpoint_signer,
            key_id="fixture-checkpoint-signer",
        )
        if predecessor is None:
            predecessor = "GENESIS" if sequence == 1 else "f" * 64
        claim = checkpoint_claim(
            checkpoint,
            authority_digest="a"*64, consumption_digest="b"*64,
            reconciliation_digest="c"*64,
            previous_checkpoint_digest=predecessor,
            sequence=sequence, domain=DOMAIN,
        )
        statement = sign_scitt_checkpoint_statement(
            claim, issuer=ISSUER, subject=SUBJECT,
            key_id=b"fixture-issuer", private_key=self.issuer,
        )
        return ledger, checkpoint, claim, statement

    def observe(self, fixture, *, store=None, expected_claim=None, domain=DOMAIN,
                signer=None, subject=SUBJECT):
        ledger, checkpoint, claim, statement = fixture
        target = self.store if store is None else store
        return target.observe_locally_verified(
            statement=statement,
            issuer_public_key=(signer or self.issuer).public_key(),
            expected_issuer=ISSUER, expected_subject=subject,
            expected_key_id=b"fixture-issuer",
            expected_execution_domain=domain,
            expected_claim=claim if expected_claim is None else expected_claim,
            signed_checkpoint=checkpoint,
            checkpoint_public_key=self.checkpoint_signer.public_key(),
            ledger_path=ledger,
        )

    def test_genesis_and_extension_and_exact_repeat(self):
        first = self.snapshot(1)
        v1 = self.observe(first)
        self.assertEqual(v1["status"], "locally_recorded_genesis")
        self.assertFalse(v1["externally_anchored"])
        self.assertFalse(v1["rekor_inclusion_verified"])
        self.assertFalse(v1["merge_authorized"])
        second = self.snapshot(2, predecessor=hash_record(first[1]))
        self.assertEqual(self.observe(second)["status"], "locally_advanced")
        self.assertEqual(self.observe(second)["status"], "already_recorded")
        head = self.store.get_head(
            issuer=ISSUER, subject=SUBJECT, execution_domain=DOMAIN
        )
        self.assertEqual(head["sequence"], 2)
        self.assertEqual(head["checkpoint_digest"], hash_record(second[1]))

    def test_old_signed_and_locally_valid_checkpoint_rejected_after_buyer_advance(self):
        first = self.snapshot(1)
        self.observe(first)
        second = self.snapshot(2, predecessor=hash_record(first[1]))
        self.observe(second)
        # An attacker can still present the original signed statement and
        # its original valid ledger snapshot. Buyer rejects it from own state.
        with self.assertRaisesRegex(ProofRailError, "checkpoint_rollback_detected"):
            self.observe(first)

    def test_altered_same_sequence_is_fork_not_idempotent_replay(self):
        first = self.snapshot(1)
        self.observe(first)
        another = self.snapshot(1)
        self.assertNotEqual(first[2]["checkpoint_digest"],
                            another[2]["checkpoint_digest"])
        with self.assertRaisesRegex(ProofRailError, "checkpoint_fork_detected"):
            self.observe(another)

    def test_sequence_gaps_and_wrong_predecessor_rejected(self):
        first = self.snapshot(1)
        self.observe(first)
        third = self.snapshot(3, predecessor="a" * 64)
        with self.assertRaisesRegex(ProofRailError, "checkpoint_sequence_gap"):
            self.observe(third)
        second = self.snapshot(2, predecessor="f" * 64)
        with self.assertRaisesRegex(ProofRailError, "checkpoint_chain_break"):
            self.observe(second)

    def test_initial_non_genesis_checkpoint_refused(self):
        second = self.snapshot(2, predecessor="e" * 64)
        with self.assertRaisesRegex(ProofRailError, "initial_checkpoint_must_be_genesis"):
            self.observe(second)

    def test_wrong_issuer_and_domain_and_expected_action_evidence_refused(self):
        first = self.snapshot(1)
        with self.assertRaisesRegex(ProofRailError, "signed_statement_or_checkpoint_invalid"):
            self.observe(first, signer=Ed25519PrivateKey.generate())
        with self.assertRaisesRegex(ProofRailError, "execution_domain_not_pinned"):
            self.observe(first, domain="github:other/repo")
        mutated = dict(first[2], authority_digest="e"*64)
        with self.assertRaisesRegex(ProofRailError, "signed_statement_or_checkpoint_invalid"):
            self.observe(first, expected_claim=mutated)
        self.assertIsNone(self.store.get_head(
            issuer=ISSUER, subject=SUBJECT, execution_domain=DOMAIN
        ))

    def test_transaction_concurrency_cannot_overwrite_head(self):
        first = self.snapshot(1)
        self.observe(first)
        second = self.snapshot(2, predecessor=hash_record(first[1]))
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(lambda _: self.observe(second)["status"], range(4)))
        self.assertEqual(statuses.count("locally_advanced"), 1)
        self.assertEqual(statuses.count("already_recorded"), 3)
        self.assertEqual(self.store.get_head(
            issuer=ISSUER, subject=SUBJECT, execution_domain=DOMAIN
        )["sequence"], 2)

    def test_buyer_database_restore_is_not_detected_without_second_trust_anchor(self):
        # Demonstrate the known unsolved buyer rollback threat explicitly.
        first = self.snapshot(1)
        self.observe(first)
        saved = self.root / "buyer-snapshot.sqlite3"
        shutil.copy2(self.store.path, saved)
        second = self.snapshot(2, predecessor=hash_record(first[1]))
        self.observe(second)
        self.assertEqual(self.store.get_head(
            issuer=ISSUER, subject=SUBJECT, execution_domain=DOMAIN
        )["sequence"], 2)
        shutil.copy2(saved, self.store.path)
        self.assertEqual(self.store.get_head(
            issuer=ISSUER, subject=SUBJECT, execution_domain=DOMAIN
        )["sequence"], 1)
        self.assertEqual(self.observe(first)["status"], "already_recorded")

    def rekor_materials(self):
        first = self.snapshot(1)
        statement = first[3]
        signature = self.detached.sign(statement, ec.ECDSA(hashes.SHA256()))
        public_der = self.detached.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return statement, signature, public_der

    def test_rekor_request_is_exact_v2_hashedrekord_with_sha256_detached_p256_ecdsa(self):
        import hashlib
        statement, signature, der = self.rekor_materials()
        payload = build_rekor_v2_request(statement, signature, der)
        self.assertEqual(set(payload), {"hashedRekordRequestV002"})
        entry = payload["hashedRekordRequestV002"]
        self.assertEqual(base64.b64decode(entry["digest"]),
                         hashlib.sha256(statement).digest())
        self.assertEqual(base64.b64decode(entry["signature"]["content"]), signature)
        verifier = entry["signature"]["verifier"]
        self.assertEqual(verifier["keyDetails"], "PKIX_ECDSA_P256_SHA_256")
        self.assertEqual(base64.b64decode(verifier["publicKey"]["rawBytes"]), der)
        self.assertNotIn(statement, json.dumps(payload).encode())
        self.assertNotIn("privateKey", json.dumps(payload))

    def test_rekor_signature_and_spki_mismatch_are_denied(self):
        statement, signature, der = self.rekor_materials()
        wrong_sig = ec.generate_private_key(ec.SECP256R1()).sign(
            statement, ec.ECDSA(hashes.SHA256())
        )
        with self.assertRaisesRegex(ProofRailError, "rekor_detached_signature_invalid"):
            build_rekor_v2_request(statement, wrong_sig, der)
        unrelated = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with self.assertRaisesRegex(ProofRailError, "rekor_detached_signature_invalid"):
            build_rekor_v2_request(statement, signature, unrelated)
        with self.assertRaisesRegex(ProofRailError, "rekor_input_encoding_invalid"):
            build_rekor_v2_request(b"hello", signature, der)
        ed25519_der = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with self.assertRaisesRegex(ProofRailError, "rekor_public_key_must_be_ecdsa_p256"):
            build_rekor_v2_request(statement, signature, ed25519_der)

    def test_dry_run_cli_does_not_send_or_reuse_existing_output_directory(self):
        statement, signature, der = self.rekor_materials()
        inputs = [
            ("statement.cose", statement), ("signature.bin", signature),
            ("public-key.der", der),
        ]
        for filename, content in inputs:
            (self.root / filename).write_bytes(content)
        target = self.root / "rekor-request"
        args = [
            "--statement", str(self.root / "statement.cose"),
            "--detached-signature", str(self.root / "signature.bin"),
            "--public-key-spki-der", str(self.root / "public-key.der"),
            "--out-dir", str(target),
        ]
        self.assertEqual(rekor_main(args), 0)
        req = json.loads((target / "rekor-v2-request.json").read_text())
        self.assertEqual(req["hashedRekordRequestV002"]["signature"]["verifier"]["keyDetails"],
                         "PKIX_ECDSA_P256_SHA_256")
        meta = json.loads((target / "dry-run-metadata.json").read_text())
        self.assertFalse(meta["submitted"])
        self.assertFalse(meta["log_receipt_verified"])
        self.assertEqual(meta["api_path"], "/api/v2/log/entries")
        self.assertEqual(rekor_main(args), 4)


if __name__ == "__main__":
    unittest.main()

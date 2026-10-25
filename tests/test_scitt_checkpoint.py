"""Offline COSE_Sign1/ProofRail checkpoint compatibility and negative tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.checkpoint import create_checkpoint, verify_ledger
from proofrail.core import digest_ledger_entry
from proofrail.scitt_checkpoint import (
    checkpoint_claim, sign_scitt_checkpoint_statement,
    verify_scitt_checkpoint_statement, COSE_ALG_EDDSA_LEGACY,
)


class ScittCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "events.jsonl"
        prev = "GENESIS"
        entries = []
        for n in range(3):
            item = {"kind": "proofrail.fixture-ledger.v1",
                    "sequence": n + 1, "previous_hash": prev,
                    "decision": "report_only", "index": n}
            item["entry_hash"] = digest_ledger_entry(item)
            prev = item["entry_hash"]
            entries.append(json.dumps(item, sort_keys=True))
        self.ledger.write_text("\n".join(entries)+"\n")
        self.assertTrue(verify_ledger(self.ledger)["valid"])
        self.checkpoint_signer = Ed25519PrivateKey.generate()
        self.issuer = Ed25519PrivateKey.generate()
        self.checkpoint = create_checkpoint(self.ledger,
                         private_key=self.checkpoint_signer, key_id="operator-checkpoint")
        self.claim = checkpoint_claim(self.checkpoint,
                   authority_digest="a"*64, consumption_digest="b"*64,
                   reconciliation_digest="c"*64, previous_checkpoint_digest="GENESIS",
                   sequence=1, domain="github:owner/repo")
        self.document = sign_scitt_checkpoint_statement(self.claim, issuer="urn:proofrail:issuer:example",
                       subject="urn:proofrail:action:123", key_id=b"issuer-key-1",
                       private_key=self.issuer)

    def verify(self, document=None, claim=None, checkpoint=None, key=None, **options):
        return verify_scitt_checkpoint_statement(
            self.document if document is None else document,
            issuer_public_key=self.issuer.public_key() if key is None else key,
            expected_issuer="urn:proofrail:issuer:example",
            expected_subject="urn:proofrail:action:123",
            expected_key_id=b"issuer-key-1",
            expected_claim=self.claim if claim is None else claim,
            checkpoint=self.checkpoint if checkpoint is None else checkpoint,
            checkpoint_public_key=self.checkpoint_signer.public_key(),
            ledger_path=str(self.ledger), **options,
        )

    def test_valid_offline_proofrail_checkpoint_claim(self):
        result=self.verify()
        self.assertTrue(result["valid"], result)
        self.assertFalse(result["transparency_receipt_verified"])
        self.assertFalse(result["external_effect_proven"])

    def test_cose_uses_rfc9943_required_protected_issuer_subject(self):
        document=cbor2.loads(self.document)
        self.assertEqual(document.tag,18)
        protected=cbor2.loads(document.value[0])
        self.assertEqual(protected[1],-19)
        self.assertEqual(protected[15],{1:"urn:proofrail:issuer:example",2:"urn:proofrail:action:123"})
        self.assertEqual(protected[4],b"issuer-key-1")

    def test_wrong_issuer_key_is_rejected(self):
        self.assertFalse(self.verify(key=Ed25519PrivateKey.generate().public_key())["valid"])

    def test_replaced_claim_rejected_even_with_correct_signature(self):
        expected=dict(self.claim,authority_digest="f"*64)
        self.assertIn("claim_context_mismatch",self.verify(claim=expected)["errors"])

    def test_changed_protected_headers_break_signature(self):
        tagged=cbor2.loads(self.document)
        altered=list(tagged.value)
        headers=cbor2.loads(altered[0])
        headers[15][2]="urn:proofrail:action:forged"
        altered[0]=cbor2.dumps(headers,canonical=True)
        forged=cbor2.dumps(cbor2.CBORTag(18,altered),canonical=True)
        self.assertFalse(self.verify(document=forged)["valid"])

    def test_tampered_signed_checkpoint_rejected(self):
        wrong=dict(self.checkpoint,checkpoint_id="forged")
        self.assertFalse(self.verify(checkpoint=wrong)["valid"])

    def test_truncated_ledger_requires_pinned_checkpoint(self):
        contents=self.ledger.read_text().splitlines()
        self.ledger.write_text("\n".join(contents[:-1])+"\n")
        self.assertTrue(verify_ledger(self.ledger)["valid"])
        self.assertIn("checkpoint_or_ledger_invalid",self.verify()["errors"])

    def test_cose_payload_mutation_breaks_signature(self):
        tagged=cbor2.loads(self.document)
        parts=list(tagged.value)
        payload=json.loads(parts[2])
        payload["authority_digest"]="f"*64
        from proofrail.crypto import canonical_json
        parts[2]=canonical_json(payload)
        modified=cbor2.dumps(cbor2.CBORTag(18,parts),canonical=True)
        self.assertFalse(self.verify(document=modified)["valid"])

    @staticmethod
    def opaque_receipt():
        """A structurally correct test receipt, NOT a verified inclusion proof."""
        protected = cbor2.dumps({1: -19, 395: 1}, canonical=True)
        proof = {396: {-1: [cbor2.dumps([2, 1, []], canonical=True)]}}
        return cbor2.dumps(
            cbor2.CBORTag(18, [protected, proof, None, b"\x00" * 64]),
            canonical=True,
        )

    def with_receipts(self, receipts=None, extra_headers=None):
        signed = cbor2.loads(self.document)
        parts = list(signed.value)
        headers = {394: [self.opaque_receipt()] if receipts is None else receipts}
        if extra_headers:
            headers.update(extra_headers)
        parts[1] = headers
        return cbor2.dumps(cbor2.CBORTag(18, parts), canonical=True)

    def test_registered_receipt_header_preserves_issuer_verification_but_not_receipt_truth(self):
        attached = self.with_receipts()
        result = self.verify(document=attached)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["issuer_signed_statement_verified"])
        self.assertEqual(result["issuer_algorithm"], -19)
        self.assertEqual(result["attached_receipts_count"], 1)
        self.assertFalse(result["transparency_receipt_verified"])
        self.assertFalse(result["externally_retained_history_proven"])
        self.assertIn("transparency_receipt_verification_unavailable",
                      self.verify(document=attached, require_transparency_receipt=True)["errors"])

    def test_several_receipts_are_accepted_as_unverified_structures(self):
        attached = self.with_receipts([self.opaque_receipt(), self.opaque_receipt()])
        result = self.verify(document=attached)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["attached_receipts_count"], 2)
        self.assertFalse(result["transparency_receipt_verified"])

    def test_unprotected_receipt_replacement_does_not_establish_external_truth(self):
        valid = self.with_receipts()
        tagged = cbor2.loads(valid)
        pieces = list(tagged.value)
        # An arbitrary substitute receipt does not alter the issuer's signature.
        pieces[1] = {394: [self.opaque_receipt()]}
        result = self.verify(document=cbor2.dumps(cbor2.CBORTag(18, pieces), canonical=True))
        self.assertTrue(result["issuer_signed_statement_verified"])
        self.assertFalse(result["transparency_receipt_verified"])

    def test_unknown_unsigned_headers_and_invalid_receipts_are_rejected(self):
        for headers in (
            {393: [self.opaque_receipt()]},
            {394: []},
            {394: [b"malformed"]},
            {394: [cbor2.dumps({"not": "cose"})]},
            {394: [self.opaque_receipt()], 395: 1},
            {394: [self.opaque_receipt()] * 17},
        ):
            with self.subTest(headers=str(headers)[:80]):
                parts = list(cbor2.loads(self.document).value)
                parts[1] = headers
                encoded = cbor2.dumps(cbor2.CBORTag(18, parts), canonical=True)
                result = self.verify(document=encoded)
                self.assertFalse(result["valid"], result)

    def test_legacy_minus_8_is_accepted_only_under_explicit_compatibility_policy(self):
        old = sign_scitt_checkpoint_statement(
            self.claim, issuer="urn:proofrail:issuer:example",
            subject="urn:proofrail:action:123", key_id=b"issuer-key-1",
            private_key=self.issuer, algorithm=COSE_ALG_EDDSA_LEGACY,
        )
        accepted = self.verify(document=old)
        self.assertTrue(accepted["valid"], accepted)
        self.assertTrue(accepted["legacy_algorithm"])
        rejected = self.verify(document=old, allow_legacy_eddsa=False)
        self.assertFalse(rejected["valid"])
        self.assertIn("legacy_algorithm_disallowed", rejected["errors"])

    def test_valid_old_checkpoint_with_structural_receipt_is_rejected_against_newer_pinned_tip(self):
        """The later tip is a fixture passed by the caller, NOT proven log state."""
        from proofrail.crypto import hash_record
        latest_ledger = Path(self.tmp.name) / "latest.jsonl"
        latest = {
            "kind": "proofrail.fixture-ledger.v1", "sequence": 4,
            "previous_hash": json.loads(self.ledger.read_text().splitlines()[-1])["entry_hash"],
            "decision": "report_only", "index": 3,
        }
        latest["entry_hash"] = digest_ledger_entry(latest)
        latest_ledger.write_text(self.ledger.read_text() + json.dumps(latest) + "\n")
        later_checkpoint = create_checkpoint(
            latest_ledger, private_key=self.checkpoint_signer,
            key_id="operator-checkpoint",
        )
        later_claim = checkpoint_claim(
            later_checkpoint, authority_digest="a"*64,
            consumption_digest="b"*64, reconciliation_digest="c"*64,
            previous_checkpoint_digest=hash_record(self.checkpoint), sequence=2,
            domain="github:owner/repo",
        )
        pinned_latest = {
            "issuer": "urn:proofrail:issuer:example",
            "subject": "urn:proofrail:action:123",
            "execution_domain": "github:owner/repo",
            "sequence": 2,
            "checkpoint_digest": later_claim["checkpoint_digest"],
        }
        old_with_receipt = self.with_receipts()
        still_valid_signed_statement = self.verify(document=old_with_receipt)
        self.assertTrue(still_valid_signed_statement["valid"])
        self.assertEqual(still_valid_signed_statement["attached_receipts_count"], 1)
        self.assertFalse(still_valid_signed_statement["transparency_receipt_verified"])
        refused = self.verify(document=old_with_receipt, pinned_latest=pinned_latest)
        self.assertFalse(refused["valid"])
        self.assertIn("pinned_latest_sequence_mismatch", refused["errors"])
        new_signed = sign_scitt_checkpoint_statement(
            later_claim, issuer="urn:proofrail:issuer:example",
            subject="urn:proofrail:action:123", key_id=b"issuer-key-1",
            private_key=self.issuer,
        )
        new_result = verify_scitt_checkpoint_statement(
            new_signed, issuer_public_key=self.issuer.public_key(),
            expected_issuer="urn:proofrail:issuer:example",
            expected_subject="urn:proofrail:action:123",
            expected_key_id=b"issuer-key-1", expected_claim=later_claim,
            checkpoint=later_checkpoint,
            checkpoint_public_key=self.checkpoint_signer.public_key(),
            ledger_path=str(latest_ledger), pinned_latest=pinned_latest,
        )
        self.assertTrue(new_result["valid"], new_result)
        self.assertTrue(new_result["pinned_latest_matched"])
        self.assertFalse(new_result["externally_verified_latest_log_state_proven"])

    def test_forged_pinned_tip_or_same_sequence_different_digest_is_rejected(self):
        expected = {
            "issuer": "urn:proofrail:issuer:example",
            "subject": "urn:proofrail:action:123",
            "execution_domain": "github:owner/repo", "sequence": 1,
            "checkpoint_digest": self.claim["checkpoint_digest"],
        }
        self.assertTrue(self.verify(pinned_latest=expected)["valid"])
        for mutated, reason in (
            (dict(expected, issuer="urn:bad:issuer"), "pinned_latest_scope_mismatch"),
            (dict(expected, checkpoint_digest="f"*64), "pinned_latest_checkpoint_digest_mismatch"),
            (dict(expected, sequence=2), "pinned_latest_sequence_mismatch"),
            (dict(expected, sequence=True), "pinned_latest_sequence_invalid"),
        ):
            with self.subTest(reason=reason):
                self.assertIn(reason, self.verify(pinned_latest=mutated)["errors"])

    def test_checkpoint_lineage_must_have_consistent_genesis(self):
        from proofrail.core import ProofRailError
        with self.assertRaises(ProofRailError):
            checkpoint_claim(self.checkpoint, authority_digest="a"*64,
                 consumption_digest="b"*64,reconciliation_digest="c"*64,
                 previous_checkpoint_digest="GENESIS",sequence=2,domain="github:owner/repo")


if __name__=="__main__":
    unittest.main()

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
    verify_scitt_checkpoint_statement,
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

    def verify(self, document=None, claim=None, checkpoint=None, key=None):
        return verify_scitt_checkpoint_statement(
            self.document if document is None else document,
            issuer_public_key=self.issuer.public_key() if key is None else key,
            expected_issuer="urn:proofrail:issuer:example",
            expected_subject="urn:proofrail:action:123",
            expected_key_id=b"issuer-key-1",
            expected_claim=self.claim if claim is None else claim,
            checkpoint=self.checkpoint if checkpoint is None else checkpoint,
            checkpoint_public_key=self.checkpoint_signer.public_key(),
            ledger_path=str(self.ledger),
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
        self.assertEqual(protected[1],-8)
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

    def test_checkpoint_lineage_must_have_consistent_genesis(self):
        from proofrail.core import ProofRailError
        with self.assertRaises(ProofRailError):
            checkpoint_claim(self.checkpoint, authority_digest="a"*64,
                 consumption_digest="b"*64,reconciliation_digest="c"*64,
                 previous_checkpoint_digest="GENESIS",sequence=2,domain="github:owner/repo")


if __name__=="__main__":
    unittest.main()

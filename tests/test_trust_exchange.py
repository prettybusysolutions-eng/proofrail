"""Adversarial tests of portable cross-administrator witness agreement.

Test-generated keys and receipts represent independent actors in a fixture;
they do NOT constitute independently administered real-world trust.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.checkpoint import create_checkpoint, verify_ledger
from proofrail.core import digest_ledger_entry, ProofRailError
from proofrail.crypto import hash_record
from proofrail.trust_exchange import (
    build_witness_statement, sign_witness_receipt, verify_witness_exchange,
)


class CrossDomainWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / "ledger.jsonl"
        previous = "GENESIS"
        lines = []
        for sequence in range(1, 4):
            entry = {
                "kind": "proofrail.fixture-observation.v0",
                "sequence": sequence,
                "previous_hash": previous,
                "outcome": f"fixture-{sequence}",
            }
            entry["entry_hash"] = digest_ledger_entry(entry)
            previous = entry["entry_hash"]
            lines.append(json.dumps(entry, sort_keys=True))
        self.ledger.write_text("\n".join(lines) + "\n")
        self.assertTrue(verify_ledger(self.ledger)["valid"])
        self.checkpoint_key = Ed25519PrivateKey.generate()
        self.checkpoint = create_checkpoint(
            self.ledger, private_key=self.checkpoint_key,
            key_id="operator-checkpoint-key",
        )
        self.statement = build_witness_statement(
            authority_digest="a" * 64, effect_digest="b" * 64,
            outcome_digest="c" * 64,
            checkpoint_digest=hash_record(self.checkpoint),
            previous_checkpoint_digest="d" * 64,
            sequence=2, execution_domain="github:example/repository",
        )
        self.keys = [Ed25519PrivateKey.generate() for _ in range(3)]
        self.roster = {
            "witness-1": {"operator_id": "independent-operator-1",
                          "key_id": "witness-key-1", "public_key": self.keys[0].public_key()},
            "witness-2": {"operator_id": "independent-operator-2",
                          "key_id": "witness-key-2", "public_key": self.keys[1].public_key()},
            "witness-3": {"operator_id": "independent-operator-1",
                          "key_id": "witness-key-3", "public_key": self.keys[2].public_key()},
        }
        self.receipts = [
            sign_witness_receipt(self.statement, signer_id=f"witness-{i+1}",
                                 operator_id=self.roster[f"witness-{i+1}"]["operator_id"],
                                 private_key=self.keys[i], key_id=f"witness-key-{i+1}")
            for i in range(3)
        ]

    def verify(self, *, statement=None, receipts=None, checkpoint=None,
               roster=None, expected=None, threshold=2):
        return verify_witness_exchange(
            self.statement if statement is None else statement,
            self.receipts[:2] if receipts is None else receipts,
            ledger_path=self.ledger,
            signed_checkpoint=self.checkpoint if checkpoint is None else checkpoint,
            checkpoint_public_key=self.checkpoint_key.public_key(),
            trusted_witnesses=self.roster if roster is None else roster,
            expected=self.statement.copy() | {"kind": self.statement["kind"]}
                     if expected is None else expected,
            minimum_distinct_operators=threshold,
        )

    def test_two_independent_operator_signatures_verify_exact_checkpoint(self):
        result = self.verify(expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(len(result["distinct_operators"]), 2)
        self.assertTrue(result["checkpoint_bound"])
        self.assertFalse(result["externally_retained_checkpoint_proven"])
        self.assertFalse(result["external_effect_proven"])

    def test_same_administrator_with_multiple_keys_does_not_form_quorum(self):
        result = self.verify(receipts=[self.receipts[0], self.receipts[2]],
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("independent_operator_quorum_missing", result["errors"])

    def test_valid_hash_chain_after_tail_truncation_fails_against_checkpoint(self):
        lines = self.ledger.read_text().splitlines()
        self.ledger.write_text("\n".join(lines[:-1]) + "\n")
        self.assertTrue(verify_ledger(self.ledger)["valid"])
        result = self.verify(expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("checkpoint_invalid", result["errors"])

    def test_untrusted_witness_key_is_refused(self):
        altered_roster = {key: dict(value) for key, value in self.roster.items()}
        altered_roster["witness-2"]["public_key"] = Ed25519PrivateKey.generate().public_key()
        result = self.verify(roster=altered_roster,
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("receipt_1_signature_invalid", result["errors"])

    def test_signed_receipt_from_another_statement_is_refused(self):
        foreign = dict(self.statement, effect_digest="f" * 64)
        foreign_receipt = sign_witness_receipt(
            foreign, signer_id="witness-2", operator_id="independent-operator-2",
            private_key=self.keys[1], key_id="witness-key-2",
        )
        result = self.verify(receipts=[self.receipts[0], foreign_receipt],
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("receipt_1_scope_mismatch", result["errors"])

    def test_modified_receipt_signature_or_operator_binding_is_refused(self):
        tampered = dict(self.receipts[1], operator_id="independent-operator-1")
        result = self.verify(receipts=[self.receipts[0], tampered],
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("receipt_1_scope_mismatch", result["errors"])
        tampered2 = dict(self.receipts[1], statement_digest="f" * 64)
        result2 = self.verify(receipts=[self.receipts[0], tampered2],
                              expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result2["valid"])

    def test_externally_pinned_prior_root_must_match(self):
        expected = {k: v for k, v in self.statement.items() if k != "kind"}
        expected["previous_checkpoint_digest"] = "0" * 64
        result = self.verify(expected=expected)
        self.assertFalse(result["valid"])
        self.assertIn("expected_previous_checkpoint_digest_mismatch", result["errors"])

    def test_externally_pinned_sequence_must_match(self):
        expected = {k: v for k, v in self.statement.items() if k != "kind"}
        expected["sequence"] += 1
        result = self.verify(expected=expected)
        self.assertFalse(result["valid"])
        self.assertIn("expected_sequence_mismatch", result["errors"])

    def test_authority_or_outcome_mismatch_denied_even_when_both_signatures_valid(self):
        for field in ("authority_digest", "effect_digest", "outcome_digest", "execution_domain"):
            with self.subTest(field=field):
                expected = {k: v for k, v in self.statement.items() if k != "kind"}
                expected[field] = "e" * 64 if field != "execution_domain" else "azure:another-tenant"
                result = self.verify(expected=expected)
                self.assertFalse(result["valid"])
                self.assertIn(f"expected_{field}_mismatch", result["errors"])

    def test_repeated_signer_does_not_count_twice(self):
        result = self.verify(receipts=[self.receipts[0], self.receipts[0]],
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("receipt_1_duplicate_signer", result["errors"])

    def test_untrusted_witness_is_not_adopted_from_bundle(self):
        result = self.verify(roster={"witness-1": self.roster["witness-1"]},
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("receipt_1_unknown_signer", result["errors"])

    def test_unsigned_or_wrong_checkpoint_fails_even_if_witnesses_signed(self):
        bad = dict(self.checkpoint, ledger={"entry_count": 1})
        result = self.verify(checkpoint=bad,
                             expected={k: v for k, v in self.statement.items() if k != "kind"})
        self.assertFalse(result["valid"])
        self.assertIn("checkpoint_invalid", result["errors"])

    def test_trust_policy_cannot_be_inferred_from_untrusted_subject(self):
        with self.assertRaises(ProofRailError):
            verify_witness_exchange(
                self.statement, self.receipts[:2], ledger_path=self.ledger,
                signed_checkpoint=self.checkpoint,
                checkpoint_public_key=self.checkpoint_key.public_key(),
                trusted_witnesses=self.roster, expected={},
            )

    def test_threshold_cannot_be_lowered_to_one(self):
        with self.assertRaises(ProofRailError):
            self.verify(threshold=1)

    def test_genesis_and_sequence_are_consistent(self):
        with self.assertRaises(ProofRailError):
            build_witness_statement(
                authority_digest="a"*64, effect_digest="b"*64,
                outcome_digest="c"*64, checkpoint_digest="d"*64,
                previous_checkpoint_digest="GENESIS", sequence=True,
                execution_domain="github:test/repo",
            )


if __name__ == "__main__":
    unittest.main()

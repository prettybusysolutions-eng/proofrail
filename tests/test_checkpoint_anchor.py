import base64
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from proofrail.checkpoint import (
    create_checkpoint,
    export_ledger,
    merkle_root,
    read_ledger,
    verify_checkpoint,
    verify_ledger,
)
from proofrail.core import ProofRailError, digest_ledger_entry


NOW = datetime(2026, 6, 11, 22, 0, tzinfo=timezone.utc)


def write_ledger(path: Path, count: int = 3) -> None:
    previous_hash = "GENESIS"
    entries = []
    for sequence in range(1, count + 1):
        entry = {
            "kind": "proofrail.test-event.v0.3",
            "sequence": sequence,
            "recorded_at": f"2026-06-11T22:00:0{sequence}Z",
            "result": f"event-{sequence}",
            "previous_hash": previous_hash,
        }
        entry["entry_hash"] = digest_ledger_entry(entry)
        previous_hash = entry["entry_hash"]
        entries.append(entry)
    path.write_text(
        "\n".join(json.dumps(entry, sort_keys=True) for entry in entries) + "\n",
        encoding="utf-8",
    )


class CheckpointAnchorTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()

    def test_merkle_root_is_stable_and_order_sensitive(self):
        records = [{"sequence": 1}, {"sequence": 2}, {"sequence": 3}]
        self.assertEqual(merkle_root(records), merkle_root(records))
        self.assertNotEqual(merkle_root(records), merkle_root(list(reversed(records))))

    def test_signed_checkpoint_verifies_against_exact_ledger(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            checkpoint = create_checkpoint(
                ledger,
                private_key=self.private_key,
                key_id="checkpoint-key",
                now=NOW,
            )
            result = verify_checkpoint(
                checkpoint,
                ledger,
                public_key=self.public_key,
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result["entries"], 3)
            self.assertEqual(
                checkpoint["ledger"]["merkle_root"],
                verify_ledger(ledger)["merkle_root"],
            )

    def test_ledger_mutation_breaks_chain_and_checkpoint(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            checkpoint = create_checkpoint(
                ledger,
                private_key=self.private_key,
                key_id="checkpoint-key",
                now=NOW,
            )
            entries = read_ledger(ledger)
            entries[0]["result"] = "fabricated"
            ledger.write_text(
                "\n".join(json.dumps(entry, sort_keys=True) for entry in entries) + "\n",
                encoding="utf-8",
            )
            ledger_result = verify_ledger(ledger)
            checkpoint_result = verify_checkpoint(
                checkpoint,
                ledger,
                public_key=self.public_key,
            )
            self.assertFalse(ledger_result["valid"])
            self.assertIn("line_1:invalid_entry_hash", ledger_result["errors"])
            self.assertFalse(checkpoint_result["valid"])
            self.assertIn(
                "checkpoint_merkle_root_mismatch",
                checkpoint_result["errors"],
            )

    def test_checkpoint_signature_tampering_is_detected(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            checkpoint = create_checkpoint(
                ledger,
                private_key=self.private_key,
                key_id="checkpoint-key",
                now=NOW,
            )
            checkpoint["ledger"]["entry_count"] = 99
            result = verify_checkpoint(
                checkpoint,
                ledger,
                public_key=self.public_key,
            )
            self.assertFalse(result["valid"])
            self.assertTrue(
                any(error.startswith("invalid_checkpoint_signature") for error in result["errors"])
            )

    def test_wrong_checkpoint_key_is_rejected(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            checkpoint = create_checkpoint(
                ledger,
                private_key=self.private_key,
                key_id="checkpoint-key",
                now=NOW,
            )
            result = verify_checkpoint(
                checkpoint,
                ledger,
                public_key=Ed25519PrivateKey.generate().public_key(),
            )
            self.assertFalse(result["valid"])
            self.assertTrue(
                any(error.startswith("invalid_checkpoint_signature") for error in result["errors"])
            )

    def test_export_refuses_invalid_source_and_preserves_valid_bytes(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            exported = Path(directory) / "exported.jsonl"
            write_ledger(source)
            result = export_ledger(source, exported)
            self.assertTrue(result["valid"])
            self.assertEqual(source.read_bytes(), exported.read_bytes())
            entries = read_ledger(source)
            entries[-1]["previous_hash"] = "wrong"
            source.write_text(
                "\n".join(json.dumps(entry, sort_keys=True) for entry in entries) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProofRailError, "Refusing to export invalid ledger"):
                export_ledger(source, exported)

    def test_export_wraps_legacy_unhashed_records_without_mutating_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.jsonl"
            exported = Path(directory) / "exported.jsonl"
            original = (
                '{"event":"created","at":"2026-06-11T22:00:00Z"}\n'
                '{"event":"verified","at":"2026-06-11T22:01:00Z"}\n'
            )
            source.write_text(original, encoding="utf-8")
            result = export_ledger(source, exported)
            self.assertTrue(result["valid"])
            self.assertTrue(result["legacy_records_wrapped"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            envelopes = read_ledger(exported)
            self.assertEqual(envelopes[0]["payload"]["event"], "created")
            self.assertTrue(verify_ledger(exported)["valid"])

    def test_committed_demo_artifact_is_independently_verifiable(self):
        artifact = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "github-merge-authority-artifact"
        )
        checkpoint = json.loads(
            (artifact / "proofrail-checkpoint.json").read_text(encoding="utf-8")
        )
        encoded_key = (artifact / "checkpoint-public-key.txt").read_text(
            encoding="utf-8"
        ).strip()
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(encoded_key + "=" * (-len(encoded_key) % 4))
        )
        authentic = verify_checkpoint(
            checkpoint,
            artifact / "proofrail-ledger.jsonl",
            public_key=public_key,
        )
        tampered = verify_checkpoint(
            checkpoint,
            artifact / "tampered-ledger.jsonl",
            public_key=public_key,
        )
        self.assertTrue(authentic["valid"])
        self.assertFalse(tampered["valid"])


if __name__ == "__main__":
    unittest.main()

import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.anchor import create_anchor, verify_anchor
from proofrail.checkpoint import read_ledger
from proofrail.core import ProofRailError
from proofrail.reproduce import reproduce_artifact
from proofrail.trust import EMPTY_ROOT
from scripts.generate_reproduce_artifact import generate
from tests.test_checkpoint_anchor import write_ledger

NOW = datetime(2026, 6, 11, 23, 55, tzinfo=timezone.utc)


class ExternalAnchorTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()

    def test_external_anchor_detects_valid_tail_truncation(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            anchor = create_anchor(
                ledger,
                trust_checkpoint_hash=EMPTY_ROOT,
                private_key=self.key,
                key_id="anchor-key",
                anchor_provider="local-file",
                anchor_reference="file:anchor.pub",
                now=NOW,
            )
            records = read_ledger(ledger)
            ledger.write_text(
                "\n".join(json.dumps(record, sort_keys=True) for record in records[:-1]) + "\n",
                encoding="utf-8",
            )
            result = verify_anchor(anchor, ledger, public_key=self.key.public_key())
            self.assertFalse(result["valid"])
            self.assertIn("anchor_ledger_merkle_root_mismatch", result["errors"])
            self.assertIn("anchor_sequence_entry_count_mismatch", result["errors"])

    def test_anchor_signature_and_trust_checkpoint_binding_are_verified(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            write_ledger(ledger)
            anchor = create_anchor(
                ledger,
                trust_checkpoint_hash="a" * 64,
                private_key=self.key,
                key_id="anchor-key",
                anchor_provider="local-file",
                anchor_reference="file:anchor.pub",
                now=NOW,
            )
            wrong_trust = verify_anchor(
                anchor,
                ledger,
                public_key=self.key.public_key(),
                expected_trust_checkpoint_hash="b" * 64,
            )
            self.assertFalse(wrong_trust["valid"])
            self.assertIn("anchor_trust_checkpoint_hash_mismatch", wrong_trust["errors"])
            anchor["ledger_merkle_root"] = "c" * 64
            tampered = verify_anchor(anchor, ledger, public_key=self.key.public_key())
            self.assertFalse(tampered["valid"])
            self.assertTrue(
                any(error.startswith("invalid_anchor_signature") for error in tampered["errors"])
            )

    def test_committed_reproduction_artifact_verifies(self):
        artifact = Path(__file__).resolve().parents[1] / "examples" / "reproduce_artifact"
        result = reproduce_artifact(artifact)
        self.assertTrue(result["valid"])
        self.assertTrue(all(check["passed"] for check in result["checks"]))

    def test_reproduction_detects_file_substitution(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "reproduce_artifact"
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            shutil.copytree(source, artifact)
            report = artifact / "VALIDATION_REPORT.md"
            report.write_text(report.read_text(encoding="utf-8") + "\nforged\n", encoding="utf-8")
            result = reproduce_artifact(artifact)
            self.assertFalse(result["valid"])
            failed = {check["name"] for check in result["checks"] if not check["passed"]}
            self.assertIn("file_hash:VALIDATION_REPORT.md", failed)
            self.assertIn("validation_report_hash_matches", failed)

    def test_reproduction_artifact_regenerates_deterministically(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "reproduce_artifact"
        with TemporaryDirectory() as directory:
            generated = Path(directory) / "artifact"
            generate(generated)
            source_files = {
                path.name: path.read_bytes() for path in source.iterdir() if path.is_file()
            }
            generated_files = {
                path.name: path.read_bytes() for path in generated.iterdir() if path.is_file()
            }
            self.assertEqual(generated_files, source_files)

    def test_reproduction_rejects_symlinked_artifact_input(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "reproduce_artifact"
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            shutil.copytree(source, artifact)
            report = artifact / "VALIDATION_REPORT.md"
            report.unlink()
            report.symlink_to(source / "VALIDATION_REPORT.md")
            with self.assertRaisesRegex(ProofRailError, "unsafe entries"):
                reproduce_artifact(artifact)

    def test_reproduction_detects_replay_registry_loss(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "reproduce_artifact"
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact"
            shutil.copytree(source, artifact)
            (artifact / "replay-registry.sqlite3").unlink()
            result = reproduce_artifact(artifact)
            self.assertFalse(result["valid"])
            failed = {check["name"] for check in result["checks"] if not check["passed"]}
            self.assertIn("file_hash:replay-registry.sqlite3", failed)
            self.assertIn("trust_checkpoint_verifies", failed)
            self.assertIn("consumed_permit_verifies", failed)


if __name__ == "__main__":
    unittest.main()

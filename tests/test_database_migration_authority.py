import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from integrations.openclaw.database_adapter import SQLiteMigrationAdapter
from proofrail.core import ProofRailError
from proofrail.migration import (
    execute_database_migration,
    migration_digest,
    mint_database_migration_permit,
)
from proofrail.permit import PermitError


NOW = datetime(2026, 6, 12, 13, 0, tzinfo=timezone.utc)
ROOTS = {
    "identity_root": "1" * 64,
    "evidence_root": "2" * 64,
    "policy_root": "3" * 64,
    "state_root": "4" * 64,
}
APPROVAL_DIGEST = "5" * 64
MIGRATION = "ALTER TABLE accounts ADD COLUMN status TEXT NOT NULL DEFAULT 'active';"


class LyingMigrationAdapter:
    def __init__(self, delegate):
        self.delegate = delegate

    def observe(self, action):
        return self.delegate.observe(action)

    def execute(self, action, *, idempotency_key):
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "lie",
            "status": "success",
            "side_effect_confirmed": True,
            "retry_safe": True,
            "receipt_evidence": {"executor_claim": "success"},
        }


class RaisingMigrationAdapter:
    def __init__(self, delegate, *, fail_phase):
        self.delegate = delegate
        self.fail_phase = fail_phase
        self.observations = 0

    def observe(self, action):
        self.observations += 1
        if self.fail_phase == "reconciliation" and self.observations > 1:
            raise RuntimeError("observation boundary failed")
        return self.delegate.observe(action)

    def execute(self, action, *, idempotency_key):
        if self.fail_phase == "execution":
            raise RuntimeError("execution boundary failed")
        return self.delegate.execute(action, idempotency_key=idempotency_key)


class DatabaseMigrationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()

    def database(self, directory):
        path = Path(directory) / "customer.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        connection.close()
        return path

    def permit(self, adapter, migration=MIGRATION, **overrides):
        before = adapter.observe(
            {"execution": {"database_id": "customer-primary"}}
        )
        with TemporaryDirectory() as expected_directory:
            expected_db = self.database(expected_directory)
            expected_adapter = SQLiteMigrationAdapter(
                expected_db,
                database_id="customer-primary",
            )
            expected_adapter.execute(
                {
                    "execution": {
                        "database_id": "customer-primary",
                        "migration_sql": migration,
                        "migration_digest": migration_digest(migration),
                        "target_version": 2,
                    }
                },
                idempotency_key="expected",
            )
            after = expected_adapter.observe(
                {"execution": {"database_id": "customer-primary"}}
            )
        values = {
            **ROOTS,
            "approval_digest": APPROVAL_DIGEST,
            "database_id": "customer-primary",
            "database_instance_fingerprint": before[
                "database_instance_fingerprint"
            ],
            "expected_schema_root": before["schema_root"],
            "expected_result_schema_root": after["schema_root"],
            "migration_sql": migration,
            "target_version": 2,
            "nonce": "migration-nonce-00000001",
            "expires_at": NOW + timedelta(minutes=10),
            "issuer_principal_id": "verifier:primary",
            "issuer_role": "verifier",
            "private_key": self.private_key,
            "key_id": "migration-verifier",
            "now": NOW,
        }
        values.update(overrides)
        return mint_database_migration_permit(**values)

    def execute(self, permit, adapter, registry, migration=MIGRATION, **overrides):
        values = {
            "adapter": adapter,
            "migration_sql": migration,
            "registry_path": registry,
            "public_key": self.public_key,
            "expected_identity_root": ROOTS["identity_root"],
            "expected_evidence_root": ROOTS["evidence_root"],
            "expected_policy_root": ROOTS["policy_root"],
            "expected_state_root": ROOTS["state_root"],
            "expected_approval_digest": APPROVAL_DIGEST,
            "executor_id": "executor:database",
            "now": NOW,
        }
        values.update(overrides)
        return execute_database_migration(permit, **values)

    def test_exact_migration_executes_once_and_reconciles_from_schema(self):
        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter)
            registry = Path(directory) / "permits.sqlite3"
            result = self.execute(permit, adapter, registry)
            self.assertEqual(result["authority_state"], "RECONCILED")
            self.assertEqual(result["observations"]["after"]["user_version"], 2)
            self.assertFalse(result["adapter_receipt"]["side_effect_confirmed"])
            with self.assertRaisesRegex(PermitError, "schema_root_changed|permit_replayed"):
                self.execute(permit, adapter, registry)

    def test_changed_migration_is_denied_before_consumption(self):
        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter)
            with self.assertRaisesRegex(PermitError, "migration_changed"):
                self.execute(
                    permit,
                    adapter,
                    Path(directory) / "permits.sqlite3",
                    migration="ALTER TABLE accounts ADD COLUMN role TEXT;",
                )

    def test_schema_drift_is_denied_before_consumption(self):
        with TemporaryDirectory() as directory:
            database = self.database(directory)
            adapter = SQLiteMigrationAdapter(database, database_id="customer-primary")
            permit = self.permit(adapter)
            connection = sqlite3.connect(database)
            connection.execute("CREATE INDEX accounts_email ON accounts(email)")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(PermitError, "schema_root_changed"):
                self.execute(permit, adapter, Path(directory) / "permits.sqlite3")

    def test_executor_success_claim_cannot_replace_observation(self):
        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter)
            result = self.execute(
                permit,
                LyingMigrationAdapter(adapter),
                Path(directory) / "permits.sqlite3",
            )
            self.assertEqual(result["authority_state"], "RECONCILIATION_FAILED")

    def test_same_schema_on_another_database_does_not_match_instance(self):
        with TemporaryDirectory() as directory:
            first_directory = Path(directory) / "first"
            second_directory = Path(directory) / "second"
            first_directory.mkdir()
            second_directory.mkdir()
            first_adapter = SQLiteMigrationAdapter(
                self.database(first_directory),
                database_id="customer-primary",
            )
            second_adapter = SQLiteMigrationAdapter(
                self.database(second_directory),
                database_id="customer-primary",
            )
            permit = self.permit(first_adapter)
            with self.assertRaisesRegex(
                ProofRailError,
                "instance fingerprint mismatch",
            ):
                self.execute(
                    permit,
                    second_adapter,
                    Path(directory) / "permits.sqlite3",
                )

    def test_path_replacement_is_denied_before_consumption(self):
        with TemporaryDirectory() as directory:
            database = self.database(directory)
            adapter = SQLiteMigrationAdapter(
                database,
                database_id="customer-primary",
            )
            permit = self.permit(adapter)
            replacement = Path(directory) / "replacement.sqlite3"
            database.rename(replacement)
            database.symlink_to(replacement)
            with self.assertRaisesRegex(ProofRailError, "cannot be a symlink"):
                self.execute(
                    permit,
                    adapter,
                    Path(directory) / "permits.sqlite3",
                )

    def test_post_consumption_exceptions_return_ambiguous_state(self):
        for phase in ("execution", "reconciliation"):
            with self.subTest(phase=phase), TemporaryDirectory() as directory:
                adapter = SQLiteMigrationAdapter(
                    self.database(directory),
                    database_id="customer-primary",
                )
                permit = self.permit(adapter)
                result = self.execute(
                    permit,
                    RaisingMigrationAdapter(adapter, fail_phase=phase),
                    Path(directory) / "permits.sqlite3",
                )
                self.assertEqual(
                    result["authority_state"],
                    "RECONCILIATION_FAILED",
                )
                self.assertEqual(result["adapter_receipt"]["status"], "unknown")
                self.assertFalse(result["adapter_receipt"]["retry_safe"])

    def test_failed_migration_consumes_authority_and_cannot_be_retried(self):
        invalid_migration = "ALTER TABLE missing_table ADD COLUMN value TEXT;"
        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter, migration=invalid_migration)
            registry = Path(directory) / "permits.sqlite3"
            result = self.execute(
                permit,
                adapter,
                registry,
                migration=invalid_migration,
            )
            self.assertEqual(result["authority_state"], "EXECUTION_FAILED")
            with self.assertRaisesRegex(PermitError, "permit_replayed"):
                self.execute(
                    permit,
                    adapter,
                    registry,
                    migration=invalid_migration,
                )

    def test_cross_database_effect_is_denied_after_authority_consumption(self):
        with TemporaryDirectory() as directory:
            escaped_database = Path(directory) / "escape.sqlite3"
            attach_migration = (
                f"ATTACH DATABASE '{escaped_database.as_posix()}' AS escape;"
            )
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter, migration=attach_migration)
            registry = Path(directory) / "permits.sqlite3"
            result = self.execute(
                permit,
                adapter,
                registry,
                migration=attach_migration,
            )
            self.assertEqual(result["authority_state"], "EXECUTION_FAILED")
            self.assertFalse(escaped_database.exists())
            with self.assertRaisesRegex(PermitError, "permit_replayed"):
                self.execute(
                    permit,
                    adapter,
                    registry,
                    migration=attach_migration,
                )

    def test_expired_permit_is_denied_before_consumption(self):
        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(
                adapter,
                expires_at=NOW + timedelta(seconds=1),
            )
            with self.assertRaisesRegex(PermitError, "permit_expired"):
                self.execute(
                    permit,
                    adapter,
                    Path(directory) / "permits.sqlite3",
                    now=NOW + timedelta(seconds=1),
                )

    def test_permit_schema_accepts_generated_permit(self):
        import json

        with TemporaryDirectory() as directory:
            adapter = SQLiteMigrationAdapter(
                self.database(directory),
                database_id="customer-primary",
            )
            permit = self.permit(adapter)
            schema = json.loads(
                (
                    Path(__file__).parents[1]
                    / "schemas"
                    / "database_migration_permit.schema.json"
                ).read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(permit)


if __name__ == "__main__":
    unittest.main()

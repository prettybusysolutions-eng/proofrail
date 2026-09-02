import copy
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrations.openclaw.repository_change import (
    RepositoryAuthorityError,
    XzeniaCoderRepositoryAdapter,
    consume_repository_change_authority,
    DEFAULT_EXECUTOR_CONTRACT_VERSION,
    default_consumption_trust_store_path,
    default_worker_registry_path,
    executable_fingerprint,
    mint_consumption_grant,
    mint_repository_change_authority,
    parameters_from_job,
    reconcile_repository_change,
    write_consumption_trust_store,
    write_worker_registry,
)


NOW = datetime(2099, 8, 18, 20, 0, tzinfo=timezone.utc)
ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL = "5" * 64


class GovernedCoderRepositoryChangeTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.consumption_private_key = Ed25519PrivateKey.generate()
        self.consumption_public_key = self.consumption_private_key.public_key()
        self.installation_trust_store = default_consumption_trust_store_path()
        self._existing_trust_store = (
            self.installation_trust_store.read_bytes()
            if self.installation_trust_store.exists()
            else None
        )
        self._write_installation_trust_store({"execution-key": self.consumption_public_key})
        self.installation_worker_registry = default_worker_registry_path()
        self._existing_worker_registry = (
            self.installation_worker_registry.read_bytes()
            if self.installation_worker_registry.exists()
            else None
        )
        self.installation_worker_registry.unlink(missing_ok=True)

    def tearDown(self):
        if self._existing_trust_store is None:
            self.installation_trust_store.unlink(missing_ok=True)
        else:
            self.installation_trust_store.parent.mkdir(parents=True, exist_ok=True)
            self.installation_trust_store.write_bytes(self._existing_trust_store)
        if self._existing_worker_registry is None:
            self.installation_worker_registry.unlink(missing_ok=True)
        else:
            self.installation_worker_registry.parent.mkdir(parents=True, exist_ok=True)
            self.installation_worker_registry.write_bytes(self._existing_worker_registry)

    def _write_installation_trust_store(self, keys):
        return write_consumption_trust_store(self.installation_trust_store, keys=keys)

    def _write_installation_worker_registry(self, worker, *, fingerprint=None):
        fingerprint = fingerprint or executable_fingerprint(worker)
        write_worker_registry(
            self.installation_worker_registry,
            workers={
                "xzenia-coder": {
                    "path": str(Path(worker).resolve()),
                    "contract_version": DEFAULT_EXECUTOR_CONTRACT_VERSION,
                    "executable_identity_digest": fingerprint,
                }
            },
        )
        return fingerprint

    def test_missing_authority_is_denied_before_worker(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            with self.assertRaisesRegex(RepositoryAuthorityError, "authority_missing"):
                adapter.execute(
                    _action(job, repo, directory, authority=None),
                    idempotency_key="x" * 64,
                )
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_authorized_change_reconciles_and_replay_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            first = adapter.execute(
                _action(job, repo, directory, authority=authority),
                idempotency_key="x" * 64,
            )
            self.assertEqual(first["status"], "success")
            self.assertEqual(
                first["receipt_evidence"]["reconciliation"]["state"],
                "RECONCILED",
            )
            manifest = first["receipt_evidence"]["reconciliation"]["artifact_manifest"]
            self.assertEqual(manifest["kind"], "proofrail.reconciled-artifact-manifest.v1")
            self.assertTrue(all(item["present"] for item in manifest["artifacts"]))
            self.assertEqual(
                first["receipt_evidence"]["reconciliation"]["worker_hashes_json_trust_level"],
                "untrusted_evidence",
            )
            with self.assertRaisesRegex(RepositoryAuthorityError, "authority_replayed"):
                adapter.execute(
                    _action(job, repo, directory, authority=authority),
                    idempotency_key="y" * 64,
                )

    def test_mutated_scope_and_path_expansion_are_denied_before_worker(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            expanded = copy.deepcopy(job)
            expanded["allowed_paths"] = ["allowed.py", "escape.py"]
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            with self.assertRaisesRegex(Exception, "parameters_changed"):
                adapter.execute(
                    _action(expanded, repo, directory, authority=authority),
                    idempotency_key="z" * 64,
                )
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_job_object_and_job_file_mismatch_is_denied_before_worker(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            action = _action(job, repo, directory, authority=authority)
            split_job = copy.deepcopy(job)
            split_job["allowed_paths"] = ["allowed.py", "escape.py"]
            Path(action["execution"]["job_file"]).write_text(
                json.dumps(split_job, sort_keys=True),
                encoding="utf-8",
            )
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            with self.assertRaisesRegex(RepositoryAuthorityError, "job_file_mismatch"):
                adapter.execute(action, idempotency_key="split")
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_forged_consumption_receipt_cannot_directly_dispatch(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            job_file = Path(directory) / "job.json"
            job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
            output = Path(directory) / "evidence"
            fake = output / "proofrail-consumption.json"
            fake.parent.mkdir(parents=True)
            fake.write_text(
                json.dumps(
                    {
                        "state": "CONSUMED",
                        "authority_digest": "a" * 64,
                        "executor_id": "xzenia-coder",
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(fake),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("consumption_signing_key_missing", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_signer_substitution_is_denied_by_trust_store(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            attacker_key = Ed25519PrivateKey.generate()
            fake_grant = mint_consumption_grant(
                authority_digest="a" * 64,
                authority_nonce="attacker-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=attacker_key,
                key_id="execution-key",
            )
            completed = _direct_dispatch(directory, repo, job, output, fake_grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("invalid_consumption_grant", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_legit_consumption_grant_with_wrong_trust_key_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            grant = mint_consumption_grant(
                authority_digest="b" * 64,
                authority_nonce="legit-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
            )
            self._write_installation_trust_store({"execution-key": self.public_key})
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("invalid_consumption_grant", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_unknown_consumption_key_id_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            grant = mint_consumption_grant(
                authority_digest="c" * 64,
                authority_nonce="unknown-key-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="unknown-key",
            )
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("untrusted_consumption_signer", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_modified_trust_store_fingerprint_fails_closed(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            grant = mint_consumption_grant(
                authority_digest="d" * 64,
                authority_nonce="fingerprint-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
            )
            store = self._write_installation_trust_store({"execution-key": self.consumption_public_key})
            store["keys"][0]["public_key_fingerprint"] = "0" * 64
            self.installation_trust_store.write_text(json.dumps(store), encoding="utf-8")
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("consumption_trust_store_fingerprint_mismatch", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_environment_selected_trust_store_is_ignored_by_dispatcher(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            attacker_key = Ed25519PrivateKey.generate()
            attacker_grant = mint_consumption_grant(
                authority_digest="e" * 64,
                authority_nonce="env-override-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=attacker_key,
                key_id="attacker-key",
            )
            attacker_store = Path(directory) / "attacker-trust-store.json"
            write_consumption_trust_store(attacker_store, keys={"attacker-key": attacker_key.public_key()})
            completed = _direct_dispatch(
                directory,
                repo,
                job,
                output,
                attacker_grant,
                env={**os.environ, "XZENIA_PROOFRAIL_CONSUMPTION_TRUST_STORE": str(attacker_store)},
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("untrusted_consumption_signer", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_missing_installation_trust_store_fails_closed(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            grant = mint_consumption_grant(
                authority_digest="6" * 64,
                authority_nonce="missing-config-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
            )
            self.installation_trust_store.unlink()
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("consumption_trust_store_invalid", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_caller_selected_cli_trust_store_is_impossible(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            attacker_key = Ed25519PrivateKey.generate()
            attacker_grant = mint_consumption_grant(
                authority_digest="7" * 64,
                authority_nonce="cli-override-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=attacker_key,
                key_id="attacker-key",
            )
            attacker_store = Path(directory) / "attacker-trust-store.json"
            write_consumption_trust_store(attacker_store, keys={"attacker-key": attacker_key.public_key()})
            job_file = Path(directory) / "job.json"
            job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
            consumption_file = output / "proofrail-consumption.json"
            consumption_file.write_text(json.dumps(attacker_grant, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(consumption_file),
                    "--proofrail-consumption-trust-store",
                    str(attacker_store),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unrecognized arguments", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_valid_authority_wrong_job_digest_is_denied_before_worker(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            mutated = copy.deepcopy(job)
            mutated["objective"] = "Change value to 3."
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            with self.assertRaisesRegex(Exception, "parameters_changed"):
                adapter.execute(
                    _action(mutated, repo, directory, authority=authority),
                    idempotency_key="digest",
                )
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_authorized_job_file_modified_after_consumption_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            parameters = parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo))
            grant = consume_repository_change_authority(
                authority,
                registry_path=Path(directory) / "registry.sqlite3",
                public_key=self.public_key,
                expected_roots=ROOTS,
                expected_approval_digest=APPROVAL,
                parameters=parameters,
                executor_id="xzenia-coder",
                private_key=self.consumption_private_key,
                key_id="execution-key",
            )
            job_file = Path(directory) / "job.json"
            mutated = copy.deepcopy(job)
            mutated["objective"] = "Do something else."
            job_file.write_text(json.dumps(mutated, sort_keys=True), encoding="utf-8")
            output = Path(directory) / "evidence"
            output.mkdir()
            consumption_file = output / "proofrail-consumption.json"
            consumption_file.write_text(json.dumps(grant), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(consumption_file),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("job_digest_mismatch", completed.stderr + completed.stdout)
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_worker_receives_verified_job_snapshot_not_original_file(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            job_file = Path(directory) / "job.json"
            job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
            worker = _recording_worker(directory, mutate_original_job=job_file)
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="f" * 64,
                authority_nonce="snapshot-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            consumption_file = output / "proofrail-consumption.json"
            consumption_file.write_text(json.dumps(grant, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(consumption_file),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            dispatch = json.loads(completed.stdout)
            worker_seen_path = output / "worker-seen-job.json"
            for _ in range(50):
                if worker_seen_path.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(worker_seen_path.exists())
            worker_seen = json.loads(worker_seen_path.read_text(encoding="utf-8"))
            self.assertEqual(worker_seen["objective"], "Change value to 2.")
            self.assertEqual(dispatch["verified_worker_input_digest"], parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo))["canonical_job_digest"])
            self.assertEqual(dispatch["verified_input_transport"], "stdin_pipe")
            self.assertEqual(dispatch["resolved_executor_identity"], "xzenia-coder")
            self.assertEqual(dispatch["resolved_executor_contract_version"], DEFAULT_EXECUTOR_CONTRACT_VERSION)
            self.assertEqual(dispatch["resolved_executor_fingerprint"], fingerprint)


    def test_verified_snapshot_replacement_race_cannot_change_worker_input(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            job_file = Path(directory) / "job.json"
            job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
            worker = _recording_worker(directory, marker="legitimate")
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="8" * 64,
                authority_nonce="snapshot-race-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            consumption_file = output / "proofrail-consumption.json"
            consumption_file.write_text(json.dumps(grant, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(consumption_file),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            (output / "dispatch" / "verified-job.json").write_text(
                json.dumps({"objective": "attacker replacement"}),
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            worker_seen_path = output / "worker-seen-job.json"
            for _ in range(50):
                if worker_seen_path.exists():
                    break
                time.sleep(0.05)
            worker_seen = json.loads(worker_seen_path.read_text(encoding="utf-8"))
            self.assertEqual(worker_seen["objective"], "Change value to 2.")

    def test_attacker_cli_worker_override_is_impossible(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="9" * 64,
                authority_nonce="cli-worker-override-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            job_file = Path(directory) / "job.json"
            job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
            consumption_file = output / "proofrail-consumption.json"
            consumption_file.write_text(json.dumps(grant, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/xzenia-coder-dispatch",
                    "--job-file",
                    str(job_file),
                    "--repo-path",
                    str(repo),
                    "--output-dir",
                    str(output),
                    "--proofrail-consumption-file",
                    str(consumption_file),
                    "--worker-path",
                    str(_recording_worker(directory, marker="attacker")),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unrecognized arguments", completed.stderr + completed.stdout)
            self.assertFalse((output / "worker-marker.txt").exists())

    def test_attacker_env_worker_override_is_ignored(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            attacker = _recording_worker(directory, marker="attacker")
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="a1" * 32,
                authority_nonce="env-worker-override-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            completed = _direct_dispatch(
                directory,
                repo,
                job,
                output,
                grant,
                env={**os.environ, "XZENIA_CODER_WORKER": str(attacker)},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            marker_path = output / "worker-marker.txt"
            marker_text = ""
            for _ in range(50):
                if marker_path.exists():
                    marker_text = marker_path.read_text(encoding="utf-8")
                    if marker_text:
                        break
                time.sleep(0.05)
            self.assertEqual(marker_text, "legitimate")

    def test_substituted_binary_same_filename_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="a2" * 32,
                authority_nonce="substituted-worker-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            Path(worker).write_text("#!/usr/bin/env python3\nraise SystemExit('attacker')\n", encoding="utf-8")
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("installed_worker_fingerprint_mismatch", completed.stderr + completed.stdout)

    def test_wrong_worker_fingerprint_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="a3" * 32,
                authority_nonce="wrong-worker-fingerprint-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest="0" * 64,
            )
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("executor_fingerprint_mismatch", completed.stderr + completed.stdout)

    def test_missing_installed_worker_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            fingerprint = self._write_installation_worker_registry(worker)
            Path(worker).unlink()
            grant = mint_consumption_grant(
                authority_digest="a4" * 32,
                authority_nonce="missing-worker-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("installed_worker_missing", completed.stderr + completed.stdout)

    def test_legitimate_installed_worker_dispatches_with_fingerprint_receipt(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            output = Path(directory) / "evidence"
            output.mkdir()
            worker = _recording_worker(directory, marker="legitimate")
            fingerprint = self._write_installation_worker_registry(worker)
            grant = mint_consumption_grant(
                authority_digest="a5" * 32,
                authority_nonce="legitimate-installed-worker-nonce",
                parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
                executor_id="xzenia-coder",
                consumed_at=NOW.isoformat(),
                expires_at=(NOW + timedelta(minutes=5)).isoformat(),
                private_key=self.consumption_private_key,
                key_id="execution-key",
                executor_contract_version=DEFAULT_EXECUTOR_CONTRACT_VERSION,
                executable_identity_digest=fingerprint,
            )
            completed = _direct_dispatch(directory, repo, job, output, grant)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            dispatch = json.loads(completed.stdout)
            self.assertEqual(dispatch["resolved_executor_fingerprint"], fingerprint)
            self.assertEqual(dispatch["verified_input_transport"], "stdin_pipe")
            self.assertEqual(len(dispatch["consumption_grant_digest"]), 64)

    def test_repo_base_drift_is_denied_before_worker(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            (repo / "drift.txt").write_text("drift\n", encoding="utf-8")
            subprocess.run(["git", "add", "drift.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "drift"], cwd=repo, check=True)
            dispatcher = _dispatcher(directory, "success")
            adapter = self._adapter(directory, dispatcher)
            with self.assertRaisesRegex(Exception, "target_changed"):
                adapter.execute(
                    _action(job, repo, directory, authority=authority),
                    idempotency_key="b" * 64,
                )
            self.assertFalse((Path(directory) / "called.txt").exists())

    def test_fake_tests_json_pass_but_actual_acceptance_test_fails(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            dispatcher = _dispatcher(directory, "fake_tests")
            adapter = self._adapter(directory, dispatcher)
            result = adapter.execute(
                _action(job, repo, directory, authority=authority),
                idempotency_key="fake-tests",
            )
            self.assertEqual(result["status"], "failed")
            self.assertIn(
                "tests_failed",
                result["receipt_evidence"]["reconciliation"]["errors"],
            )

    def test_committed_unauthorized_change_is_reconciliation_failure(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            dispatcher = _dispatcher(directory, "unauthorized_commit")
            adapter = self._adapter(directory, dispatcher)
            result = adapter.execute(
                _action(job, repo, directory, authority=authority),
                idempotency_key="unauthorized-commit",
            )
            reconciliation = result["receipt_evidence"]["reconciliation"]
            self.assertEqual(reconciliation["state"], "RECONCILIATION_FAILED")
            self.assertIn("unauthorized_changes", reconciliation["errors"])
            self.assertIn("escape.py", reconciliation["unauthorized_changes"])

    def test_allowed_committed_change_is_visible_and_reconciles(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            dispatcher = _dispatcher(directory, "allowed_commit")
            adapter = self._adapter(directory, dispatcher)
            result = adapter.execute(
                _action(job, repo, directory, authority=authority),
                idempotency_key="allowed-commit",
            )
            reconciliation = result["receipt_evidence"]["reconciliation"]
            self.assertEqual(reconciliation["state"], "RECONCILED")
            self.assertIn("allowed.py", reconciliation["changed_files"])

    def test_untracked_unauthorized_file_is_reconciliation_failure(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            dispatcher = _dispatcher(directory, "untracked_unauthorized")
            adapter = self._adapter(directory, dispatcher)
            result = adapter.execute(
                _action(job, repo, directory, authority=authority),
                idempotency_key="untracked",
            )
            reconciliation = result["receipt_evidence"]["reconciliation"]
            self.assertEqual(reconciliation["state"], "RECONCILIATION_FAILED")
            self.assertIn("escape.py", reconciliation["unauthorized_changes"])

    def test_expired_authority_is_denied(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            parameters = parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo))
            authority = mint_repository_change_authority(
                roots=ROOTS,
                approval_digest=APPROVAL,
                parameters=parameters,
                executor_identity="xzenia-coder",
                issuer_principal_id="verifier",
                issuer_role="verifier",
                nonce="expired-authority-0001",
                expires_at=NOW + timedelta(seconds=1),
                private_key=self.private_key,
                key_id="verifier-key",
                now=NOW,
            )
            with self.assertRaisesRegex(Exception, "permit_expired"):
                consume_repository_change_authority(
                    authority,
                    registry_path=Path(directory) / "registry.sqlite3",
                    public_key=self.public_key,
                    expected_roots=ROOTS,
                    expected_approval_digest=APPROVAL,
                    parameters=parameters,
                    executor_id="xzenia-coder",
                    private_key=self.consumption_private_key,
                    key_id="execution-key",
                    now=NOW + timedelta(seconds=1),
                )

    def test_two_workers_race_same_authority_only_one_consumes(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            authority = self._authority(job, repo)
            parameters = parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo))
            registry = Path(directory) / "registry.sqlite3"
            outcomes = []

            def consume():
                try:
                    consume_repository_change_authority(
                        authority,
                        registry_path=registry,
                        public_key=self.public_key,
                        expected_roots=ROOTS,
                        expected_approval_digest=APPROVAL,
                        parameters=parameters,
                        executor_id="xzenia-coder",
                        private_key=self.consumption_private_key,
                        key_id="execution-key",
                    )
                    outcomes.append("consumed")
                except Exception as exc:
                    outcomes.append(str(exc))

            threads = [threading.Thread(target=consume), threading.Thread(target=consume)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(outcomes.count("consumed"), 1)
            self.assertTrue(any("authority_replayed" in item for item in outcomes))
            with sqlite3.connect(registry) as db:
                count = db.execute("SELECT COUNT(*) FROM permit_claims").fetchone()[0]
            self.assertEqual(count, 1)

    def _authority(self, job, repo):
        return mint_repository_change_authority(
            roots=ROOTS,
            approval_digest=APPROVAL,
            parameters=parameters_from_job(job, repo_path=repo, base_commit_sha=_head(repo)),
            executor_identity="xzenia-coder",
            issuer_principal_id="verifier",
            issuer_role="verifier",
            nonce="repository-authority-0001",
            expires_at=NOW + timedelta(minutes=5),
            private_key=self.private_key,
            key_id="verifier-key",
            now=NOW,
        )

    def _adapter(self, directory, dispatcher):
        return XzeniaCoderRepositoryAdapter(
            dispatcher_path=dispatcher,
            registry_path=Path(directory) / "registry.sqlite3",
            public_key=self.public_key,
            consumption_private_key=self.consumption_private_key,
            consumption_key_id="execution-key",
            consumption_public_key=self.consumption_public_key,
            expected_roots=ROOTS,
            expected_approval_digest=APPROVAL,
            executor_id="xzenia-coder",
        )


def _repo(directory):
    repo = Path(directory) / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "proofrail@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "ProofRail Test"], cwd=repo, check=True)
    (repo / "allowed.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (repo / "test_allowed.py").write_text(
        "import unittest\n\nfrom allowed import value\n\n\n"
        "class AllowedTests(unittest.TestCase):\n"
        "    def test_value(self):\n"
        "        self.assertEqual(value(), 2)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "allowed.py", "test_allowed.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    return repo


def _job(repo):
    return {
        "job_id": "governed-job",
        "objective": "Change value to 2.",
        "repo_path": str(repo),
        "allowed_paths": ["allowed.py"],
        "forbidden_paths": [],
        "allowed_commands": [[sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"]],
        "acceptance_tests": [[sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"]],
        "max_runtime_seconds": 30,
        "max_model_calls": 1,
    }


def _action(job, repo, directory, *, authority):
    output = Path(directory) / "evidence"
    job_file = Path(directory) / "job.json"
    job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
    return {
        "action_type": "repository_change",
        "execution": {
            "authority": authority,
            "job": job,
            "job_file": str(job_file),
            "repo_path": str(repo),
            "output_dir": str(output),
        },
    }


def _direct_dispatch(directory, repo, job, output, consumption_grant, env=None):
    job_file = Path(directory) / "job.json"
    job_file.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
    consumption_file = Path(output) / "proofrail-consumption.json"
    consumption_file.write_text(json.dumps(consumption_grant, sort_keys=True), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "scripts/xzenia-coder-dispatch",
            "--job-file",
            str(job_file),
            "--repo-path",
            str(repo),
            "--output-dir",
            str(output),
            "--proofrail-consumption-file",
            str(consumption_file),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _dispatcher(directory, mode):
    path = Path(directory) / "dispatcher.py"
    path.write_text(
        f"""#!/usr/bin/env python3
import json, pathlib, subprocess, sys
mode = {mode!r}
repo = pathlib.Path(sys.argv[sys.argv.index('--repo-path') + 1])
if mode == 'fake_tests':
    pathlib.Path(repo, 'allowed.py').write_text('def value():\\n    return 3\\n')
elif mode in ('unauthorized_commit', 'untracked_unauthorized'):
    pathlib.Path(repo, 'allowed.py').write_text('def value():\\n    return 2\\n')
    pathlib.Path(repo, 'escape.py').write_text('escape = True\\n')
    if mode == 'unauthorized_commit':
        subprocess.run(['git', 'add', 'allowed.py', 'escape.py'], cwd=repo, check=True)
        subprocess.run(['git', 'commit', '-m', 'worker change'], cwd=repo, check=True, stdout=subprocess.DEVNULL)
elif mode == 'allowed_commit':
    pathlib.Path(repo, 'allowed.py').write_text('def value():\\n    return 2\\n')
    subprocess.run(['git', 'add', 'allowed.py'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'worker change'], cwd=repo, check=True, stdout=subprocess.DEVNULL)
else:
    pathlib.Path(repo, 'allowed.py').write_text('def value():\\n    return 2\\n')
out = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
out.mkdir(parents=True, exist_ok=True)
for name in ('transcript.jsonl', 'commands.jsonl', 'patch.diff'):
    (out / name).write_text('x\\n')
(out / 'job.json').write_text(pathlib.Path(sys.argv[sys.argv.index('--job-file') + 1]).read_text())
(out / 'tests.json').write_text(json.dumps({{'final': [{{'returncode': 0}}]}}))
(out / 'hashes.json').write_text('{{}}')
(out / 'final_report.json').write_text(json.dumps({{'status': 'PASS', 'changed_files': ['allowed.py']}}))
pathlib.Path(pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1]).parent, 'called.txt').write_text('called')
print(json.dumps({{'status': 'DISPATCHED'}}))
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)
    return path


def _worker(directory):
    path = Path(directory) / "worker.py"
    path.write_text(
        "#!/usr/bin/env python3\nraise SystemExit('worker_should_not_start')\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)
    return path


def _recording_worker(directory, *, mutate_original_job=None, marker=None):
    path = Path(directory) / f"recording_worker_{marker or 'default'}.py"
    mutation = (
        f"pathlib.Path({str(mutate_original_job)!r}).write_text(json.dumps({{'objective': 'unauthorized mutation'}}))"
        if mutate_original_job is not None
        else ""
    )
    path.write_text(
        f"""#!/usr/bin/env python3
import json, pathlib, sys
job_bytes = sys.stdin.buffer.read()
output_dir = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
{mutation}
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / 'worker-seen-job.json').write_bytes(job_bytes)
(output_dir / 'worker-marker.txt').write_text({(marker or 'legitimate')!r})
for name in ('transcript.jsonl', 'commands.jsonl', 'patch.diff'):
    (output_dir / name).write_text('x\\n')
(output_dir / 'job.json').write_bytes(job_bytes)
(output_dir / 'tests.json').write_text(json.dumps({{'final': [{{'returncode': 0}}]}}))
(output_dir / 'hashes.json').write_text('{{}}')
(output_dir / 'final_report.json').write_text(json.dumps({{'status': 'PASS', 'changed_files': []}}))
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)
    return path


def _public_key_hex(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _head(repo):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    unittest.main()

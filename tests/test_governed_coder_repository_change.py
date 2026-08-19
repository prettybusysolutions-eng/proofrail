import copy
import json
import os
import sqlite3
import subprocess
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrations.openclaw.repository_change import (
    RepositoryAuthorityError,
    XzeniaCoderRepositoryAdapter,
    consume_repository_change_authority,
    mint_repository_change_authority,
    parameters_from_job,
    reconcile_repository_change,
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

    def test_false_success_and_failing_tests_are_reconciliation_failures(self):
        with TemporaryDirectory() as directory:
            repo = _repo(directory)
            job = _job(repo)
            before = {"state_root": "before", "changed_files": []}
            after = {"state_root": "after", "changed_files": ["allowed.py"]}
            output = Path(directory) / "evidence"
            output.mkdir()
            for name in ("job.json", "transcript.jsonl", "patch.diff", "commands.jsonl", "hashes.json", "final_report.json"):
                (output / name).write_text("{}\n", encoding="utf-8")
            (output / "tests.json").write_text(
                json.dumps({"final": [{"returncode": 1}]}),
                encoding="utf-8",
            )
            result = reconcile_repository_change(
                job=job,
                before=before,
                after=after,
                worker_report={"status": "PASS", "changed_files": ["allowed.py"]},
                output_dir=output,
            )
            self.assertEqual(result["state"], "RECONCILIATION_FAILED")
            self.assertIn("tests_failed", result["errors"])

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
    subprocess.run(["git", "add", "allowed.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    return repo


def _job(repo):
    return {
        "job_id": "governed-job",
        "objective": "Change value to 2.",
        "repo_path": str(repo),
        "allowed_paths": ["allowed.py"],
        "forbidden_paths": [],
        "allowed_commands": [[sys.executable, "-m", "pytest", "-q"]],
        "acceptance_tests": [[sys.executable, "-m", "pytest", "-q"]],
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


def _dispatcher(directory, mode):
    path = Path(directory) / "dispatcher.py"
    path.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys
pathlib.Path(sys.argv[sys.argv.index('--repo-path') + 1], 'allowed.py').write_text('def value():\\n    return 2\\n')
out = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
out.mkdir(parents=True, exist_ok=True)
for name in ('transcript.jsonl', 'commands.jsonl', 'patch.diff'):
    (out / name).write_text('x\\n')
(out / 'job.json').write_text(pathlib.Path(sys.argv[sys.argv.index('--job-file') + 1]).read_text())
(out / 'tests.json').write_text(json.dumps({'final': [{'returncode': 0}]}))
(out / 'hashes.json').write_text('{}')
(out / 'final_report.json').write_text(json.dumps({'status': 'PASS', 'changed_files': ['allowed.py']}))
pathlib.Path(pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1]).parent, 'called.txt').write_text('called')
print(json.dumps({'status': 'DISPATCHED'}))
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o755)
    return path


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

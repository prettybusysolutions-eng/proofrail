from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from proofrail.core import ProofRailError
from proofrail.crypto import canonical_json, hash_record, sign_record, verify_signature
from proofrail.envelope import (
    mint_action_authority_envelope,
    verify_action_authority_envelope,
)


ACTION_TYPE = "repository_change"
JOB_CONTRACT = "proofrail.xzenia-job.v1"
CONSUMPTION_GRANT_KIND = "proofrail.execution-consumption-grant.v1"
CONSUMPTION_TRUST_STORE_KIND = "proofrail.consumption-trust-store.v1"
RECONCILED_ARTIFACT_MANIFEST_KIND = "proofrail.reconciled-artifact-manifest.v1"
REQUIRED_WORKER_ARTIFACTS = (
    "job.json",
    "transcript.jsonl",
    "patch.diff",
    "commands.jsonl",
    "tests.json",
    "hashes.json",
    "final_report.json",
)
TERMINAL_WORKER_STATES = {
    "PASS",
    "FAILED_TESTS",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_QUOTA",
    "TIMEOUT",
    "CANCELLED",
    "POLICY_DENIED",
    "INVALID_JOB",
    "INTERNAL_ERROR",
}


class RepositoryAuthorityError(ProofRailError):
    pass


def repository_change_parameters(
    *,
    repository_identity: str,
    repository_path: str | Path,
    base_commit_sha: str,
    allowed_paths: list[str],
    forbidden_paths: list[str],
    allowed_commands: list[list[str]],
    objective: str,
    acceptance_tests: list[list[str]],
    max_runtime_seconds: int,
    max_model_calls: int,
    canonical_job_digest: str,
    expected_effect_class: str = "code_patch",
) -> dict[str, Any]:
    _require_digest(canonical_job_digest, "canonical_job_digest")
    return {
        "repository_identity": repository_identity,
        "repository_path": str(Path(repository_path).resolve()),
        "base_commit_sha": base_commit_sha,
        "allowed_paths": sorted(allowed_paths),
        "forbidden_paths": sorted(forbidden_paths),
        "allowed_commands": sorted(allowed_commands),
        "objective_digest": _sha256_text(objective),
        "acceptance_test_digest": _sha256_json(acceptance_tests),
        "canonical_job_digest": canonical_job_digest,
        "max_runtime_seconds": max_runtime_seconds,
        "max_model_calls": max_model_calls,
        "expected_effect_class": expected_effect_class,
    }


def mint_repository_change_authority(
    *,
    roots: Mapping[str, str],
    approval_digest: str,
    parameters: Mapping[str, Any],
    executor_identity: str,
    issuer_principal_id: str,
    issuer_role: str,
    nonce: str,
    expires_at,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    now=None,
) -> dict[str, Any]:
    target = f"repo:{parameters['repository_identity']}@{parameters['base_commit_sha']}"
    return mint_action_authority_envelope(
        roots=roots,
        approval_digest=approval_digest,
        action_type=ACTION_TYPE,
        target=target,
        parameters=parameters,
        subject_principal_id=executor_identity,
        subject_role="executor",
        issuer_principal_id=issuer_principal_id,
        issuer_role=issuer_role,
        adapter_contract={
            "name": "xzenia-coder-dispatch",
            "version": "v1",
            "idempotency_required": True,
        },
        observation_contract={
            "name": "proofrail.local-repository-reconciler",
            "version": "v1",
            "minimum_confirmations": 1,
            "success_predicate_digest": _sha256_text("tests_pass_and_no_unauthorized_changes"),
        },
        nonce=nonce,
        expires_at=expires_at,
        private_key=private_key,
        key_id=key_id,
        now=now,
        constraints={"single_use": True, "consume_before_effect": True},
    )


def consume_repository_change_authority(
    authority: Mapping[str, Any] | None,
    *,
    registry_path: str | Path,
    public_key: Ed25519PublicKey | bytes,
    expected_roots: Mapping[str, str],
    expected_approval_digest: str,
    parameters: Mapping[str, Any],
    executor_id: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    now=None,
) -> dict[str, Any]:
    if authority is None:
        raise RepositoryAuthorityError("authority_missing")
    target = f"repo:{parameters['repository_identity']}@{parameters['base_commit_sha']}"
    verify_action_authority_envelope(
        authority,
        public_key=public_key,
        expected_roots=expected_roots,
        expected_approval_digest=expected_approval_digest,
        action_type=ACTION_TYPE,
        target=target,
        parameters=parameters,
        now=now,
    )
    permit_hash = _required_text(authority, "record_hash")
    nonce = _required_text(authority, "nonce")
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    consumed_at = _timestamp_ms()
    _insert_consumption_claim(
        path=path,
        permit_hash=permit_hash,
        nonce=nonce,
        executor_id=executor_id,
        consumed_at=consumed_at,
    )
    return mint_consumption_grant(
        authority_digest=permit_hash,
        authority_nonce=nonce,
        parameters=parameters,
        executor_id=executor_id,
        consumed_at=consumed_at,
        expires_at=_required_text(authority, "expires_at"),
        private_key=private_key,
        key_id=key_id,
        registry_path=path,
    )


def mint_consumption_grant(
    *,
    authority_digest: str,
    authority_nonce: str,
    parameters: Mapping[str, Any],
    executor_id: str,
    consumed_at: str,
    expires_at: str,
    private_key: Ed25519PrivateKey | bytes,
    key_id: str,
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    _require_digest(authority_digest, "authority_digest")
    _require_digest(str(parameters.get("canonical_job_digest")), "canonical_job_digest")
    record = {
        "kind": CONSUMPTION_GRANT_KIND,
        "state": "CONSUMED",
        "authority_digest": authority_digest,
        "authority_nonce": authority_nonce,
        "canonical_job_digest": parameters["canonical_job_digest"],
        "repository_identity": parameters["repository_identity"],
        "repository_path": parameters["repository_path"],
        "base_commit_sha": parameters["base_commit_sha"],
        "executor_id": executor_id,
        "issued_at": consumed_at,
        "expires_at": expires_at,
        "signing_key_id": key_id,
    }
    if registry_path is not None:
        record["registry_path"] = str(Path(registry_path))
    return sign_record(record, private_key, key_id=key_id)


def verify_consumption_grant(
    grant: Mapping[str, Any],
    *,
    public_key: Ed25519PublicKey | bytes | None = None,
    parameters: Mapping[str, Any],
    executor_id: str,
    now: datetime | None = None,
) -> bool:
    public_key = public_key or load_consumption_verification_key(grant)
    try:
        verify_signature(grant, public_key)
    except Exception as exc:
        raise RepositoryAuthorityError("invalid_consumption_grant") from exc
    if grant.get("kind") != CONSUMPTION_GRANT_KIND:
        raise RepositoryAuthorityError("invalid_consumption_grant_kind")
    if grant.get("state") != "CONSUMED":
        raise RepositoryAuthorityError("proofrail_authority_consumption_required")
    if grant.get("executor_id") != executor_id:
        raise RepositoryAuthorityError("proofrail_authority_executor_mismatch")
    signature = grant.get("signature")
    if not isinstance(signature, Mapping) or grant.get("signing_key_id") != signature.get("key_id"):
        raise RepositoryAuthorityError("consumption_signing_key_mismatch")
    comparisons = (
        ("canonical_job_digest", parameters["canonical_job_digest"], "job_digest_mismatch"),
        ("repository_identity", parameters["repository_identity"], "repository_identity_mismatch"),
        ("repository_path", parameters["repository_path"], "repository_path_mismatch"),
        ("base_commit_sha", parameters["base_commit_sha"], "base_commit_mismatch"),
    )
    for field, expected, code in comparisons:
        if grant.get(field) != expected:
            raise RepositoryAuthorityError(code)
    expiry = datetime.fromisoformat(str(grant["expires_at"]).replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if current.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
        raise RepositoryAuthorityError("consumption_grant_expired")
    return True


def default_consumption_trust_store_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "proofrail-consumption-trust-store.json"


def write_consumption_trust_store(
    path: str | Path,
    *,
    keys: Mapping[str, Ed25519PublicKey | bytes],
) -> dict[str, Any]:
    entries = []
    for key_id, public_key in sorted(keys.items()):
        key_hex = _public_key_hex(public_key)
        entries.append(
            {
                "key_id": key_id,
                "algorithm": "ed25519",
                "public_key_hex": key_hex,
                "public_key_fingerprint": _sha256_text(key_hex),
            }
        )
    trust_store = {
        "kind": CONSUMPTION_TRUST_STORE_KIND,
        "keys": entries,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(trust_store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return trust_store


def load_consumption_verification_key(
    grant: Mapping[str, Any],
) -> Ed25519PublicKey:
    key_id = grant.get("signing_key_id")
    signature = grant.get("signature")
    if not isinstance(key_id, str) or not key_id:
        raise RepositoryAuthorityError("consumption_signing_key_missing")
    if not isinstance(signature, Mapping) or signature.get("key_id") != key_id:
        raise RepositoryAuthorityError("consumption_signing_key_mismatch")
    store_path = default_consumption_trust_store_path()
    trust_store = _read_json(store_path, default=None)
    if not isinstance(trust_store, Mapping) or trust_store.get("kind") != CONSUMPTION_TRUST_STORE_KIND:
        raise RepositoryAuthorityError("consumption_trust_store_invalid")
    matches = [
        item
        for item in trust_store.get("keys", [])
        if isinstance(item, Mapping) and item.get("key_id") == key_id
    ]
    if len(matches) != 1:
        raise RepositoryAuthorityError("untrusted_consumption_signer")
    entry = matches[0]
    if entry.get("algorithm") != "ed25519":
        raise RepositoryAuthorityError("untrusted_consumption_signer")
    public_key_hex = entry.get("public_key_hex")
    expected_fingerprint = entry.get("public_key_fingerprint")
    if not isinstance(public_key_hex, str) or not isinstance(expected_fingerprint, str):
        raise RepositoryAuthorityError("consumption_trust_store_invalid")
    if _sha256_text(public_key_hex) != expected_fingerprint:
        raise RepositoryAuthorityError("consumption_trust_store_fingerprint_mismatch")
    try:
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    except ValueError as exc:
        raise RepositoryAuthorityError("consumption_trust_store_invalid") from exc


class XzeniaCoderRepositoryAdapter:
    def __init__(
        self,
        *,
        dispatcher_path: str | Path,
        registry_path: str | Path,
        public_key: Ed25519PublicKey | bytes,
        consumption_private_key: Ed25519PrivateKey | bytes,
        consumption_key_id: str,
        consumption_public_key: Ed25519PublicKey | bytes | None = None,
        expected_roots: Mapping[str, str],
        expected_approval_digest: str,
        executor_id: str,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self.dispatcher_path = Path(dispatcher_path)
        self.registry_path = Path(registry_path)
        self.public_key = public_key
        self.consumption_private_key = consumption_private_key
        self.consumption_key_id = consumption_key_id
        self.consumption_public_key = consumption_public_key or public_key
        self.consumption_trust_store_path = default_consumption_trust_store_path()
        self.expected_roots = dict(expected_roots)
        self.expected_approval_digest = expected_approval_digest
        self.executor_id = executor_id
        self.poll_interval_seconds = poll_interval_seconds

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        execution = _mapping(action, "execution")
        authority = execution.get("authority")
        repo_path = Path(_required_text(execution, "repo_path")).resolve()
        output_dir = Path(_required_text(execution, "output_dir")).resolve()
        job_file = Path(_required_text(execution, "job_file")).resolve()
        job = read_canonical_job_file(job_file, expected_repo_path=repo_path)
        if "job" in execution and canonicalize_job(_mapping(execution, "job"), repo_path=repo_path) != dict(job):
            raise RepositoryAuthorityError("job_file_mismatch")
        current_base = git_head(repo_path)
        parameters = parameters_from_job(job, repo_path=repo_path, base_commit_sha=current_base)
        claim = consume_repository_change_authority(
            authority,
            registry_path=self.registry_path,
            public_key=self.public_key,
            expected_roots=self.expected_roots,
            expected_approval_digest=self.expected_approval_digest,
            parameters=parameters,
            executor_id=self.executor_id,
            private_key=self.consumption_private_key,
            key_id=self.consumption_key_id,
        )
        verify_consumption_grant(
            claim,
            parameters=parameters,
            executor_id=self.executor_id,
        )
        consumption_file = output_dir / "proofrail-consumption.json"
        consumption_file.parent.mkdir(parents=True, exist_ok=True)
        consumption_file.write_text(
            json.dumps(claim, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before = observe_repository(
            repo_path,
            allowed_paths=job["allowed_paths"],
            base_commit_sha=current_base,
        )
        dispatch = _run_dispatcher(
            self.dispatcher_path,
            job_file=job_file,
            repo_path=repo_path,
            output_dir=output_dir,
            consumption_file=consumption_file,
            timeout=int(job["max_runtime_seconds"]),
        )
        worker_report = _read_worker_report(
            output_dir,
            timeout_seconds=int(job["max_runtime_seconds"]),
        )
        after = observe_repository(
            repo_path,
            allowed_paths=job["allowed_paths"],
            base_commit_sha=current_base,
        )
        reconciliation = reconcile_repository_change(
            job=job,
            before=before,
            after=after,
            worker_report=worker_report,
            output_dir=output_dir,
            repo_path=repo_path,
            consumption_grant=claim,
            base_commit_sha=current_base,
        )
        status = "success" if reconciliation["state"] == "RECONCILED" else "failed"
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": f"xzenia-coder:{job['job_id']}",
            "status": status,
            "side_effect_confirmed": status == "success",
            "retry_safe": False,
            "receipt_evidence": {
                "authority_digest": claim["authority_digest"],
                "dispatch": dispatch,
                "worker_final_status": worker_report.get("status"),
                "reconciliation": reconciliation,
                "worker_execution_ledger_hash": _optional_sha256(output_dir / "final_report.json"),
                "patch_hash": _optional_sha256(output_dir / "patch.diff"),
                "tests_hash": _optional_sha256(output_dir / "tests.json"),
                "command_log_hash": _optional_sha256(output_dir / "commands.jsonl"),
                "final_repo_state_root": after["state_root"],
            },
        }


def parameters_from_job(
    job: Mapping[str, Any],
    *,
    repo_path: str | Path,
    base_commit_sha: str,
    repository_identity: str | None = None,
) -> dict[str, Any]:
    canonical_job = canonicalize_job(job, repo_path=repo_path)
    return repository_change_parameters(
        repository_identity=repository_identity or str(Path(repo_path).resolve()),
        repository_path=repo_path,
        base_commit_sha=base_commit_sha,
        allowed_paths=list(canonical_job["allowed_paths"]),
        forbidden_paths=list(canonical_job["forbidden_paths"]),
        allowed_commands=list(canonical_job["allowed_commands"]),
        objective=str(canonical_job["objective"]),
        acceptance_tests=list(canonical_job["acceptance_tests"]),
        max_runtime_seconds=int(canonical_job["max_runtime_seconds"]),
        max_model_calls=int(canonical_job["max_model_calls"]),
        canonical_job_digest=canonical_job_digest(canonical_job),
    )


def canonicalize_job(job: Mapping[str, Any], *, repo_path: str | Path | None = None) -> dict[str, Any]:
    required = (
        "job_id",
        "objective",
        "repo_path",
        "allowed_paths",
        "allowed_commands",
        "acceptance_tests",
        "max_runtime_seconds",
    )
    for field in required:
        if field not in job:
            raise RepositoryAuthorityError(f"{field}_missing")
    resolved_repo = str(Path(repo_path or str(job["repo_path"])).resolve())
    canonical = {
        "kind": JOB_CONTRACT,
        "job_id": str(job["job_id"]),
        "objective": str(job["objective"]),
        "repo_path": resolved_repo,
        "allowed_paths": sorted(str(item) for item in job["allowed_paths"]),
        "forbidden_paths": sorted(str(item) for item in job.get("forbidden_paths", [])),
        "allowed_commands": sorted(_canonical_command(item) for item in job["allowed_commands"]),
        "acceptance_tests": sorted(_canonical_command(item) for item in job["acceptance_tests"]),
        "max_runtime_seconds": int(job["max_runtime_seconds"]),
        "max_model_calls": int(job.get("max_model_calls", 1)),
    }
    return canonical


def canonical_job_digest(job: Mapping[str, Any]) -> str:
    canonical = dict(job) if job.get("kind") == JOB_CONTRACT else canonicalize_job(job)
    return hashlib.sha256(canonical_json(canonical)).hexdigest()


def read_canonical_job_file(path: str | Path, *, expected_repo_path: str | Path | None = None) -> dict[str, Any]:
    raw = _read_json(Path(path), default=None)
    if not isinstance(raw, Mapping):
        raise RepositoryAuthorityError("invalid_job_file")
    return canonicalize_job(raw, repo_path=expected_repo_path)


def observe_repository(
    repo_path: str | Path,
    *,
    allowed_paths: list[str],
    base_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    changed = _git_lines(repo, ["status", "--short"])
    changed_files = set()
    for line in changed:
        if len(line) >= 4:
            changed_files.add(line[3:])
    if base_commit_sha:
        for args in (
            ["diff", "--name-only", base_commit_sha, "HEAD"],
            ["diff", "--name-only", base_commit_sha],
            ["diff", "--cached", "--name-only"],
        ):
            changed_files.update(_git_lines(repo, args))
    changed_files.update(_git_lines(repo, ["ls-files", "--others", "--exclude-standard"]))
    diff = subprocess.run(
        ["git", "diff", "--binary", *( [base_commit_sha] if base_commit_sha else [] )],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout
    file_hashes = {}
    for rel in allowed_paths:
        path = (repo / rel).resolve()
        if path.exists() and path.is_file():
            file_hashes[rel] = _sha256_bytes(path.read_bytes())
    state = {
        "head": git_head(repo),
        "changed_files": sorted(path for path in changed_files if path),
        "diff_sha256": _sha256_text(diff),
        "allowed_file_hashes": file_hashes,
    }
    state["state_root"] = hash_record({"kind": "proofrail.repository-observation.v1", **state})
    return state


def reconcile_repository_change(
    *,
    job: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    worker_report: Mapping[str, Any],
    output_dir: str | Path,
    repo_path: str | Path | None = None,
    consumption_grant: Mapping[str, Any] | None = None,
    public_key: Ed25519PublicKey | bytes | None = None,
    base_commit_sha: str | None = None,
) -> dict[str, Any]:
    allowed = set(job.get("allowed_paths", []))
    changed = set(after.get("changed_files", []))
    unauthorized = sorted(path for path in changed if path not in allowed)
    report_changed = set(worker_report.get("changed_files", []))
    missing_artifacts = [name for name in REQUIRED_WORKER_ARTIFACTS if not (Path(output_dir) / name).exists()]
    worker_hash_errors = verify_hashes_json(Path(output_dir))
    independent_tests = []
    if repo_path is not None:
        independent_tests = run_acceptance_tests(repo_path, job.get("acceptance_tests", []))
    else:
        tests = _read_json(Path(output_dir) / "tests.json", default={"final": []})
        independent_tests = tests.get("final", [])
    command_failures = [item for item in independent_tests if isinstance(item, Mapping) and item.get("returncode") != 0]
    errors: list[str] = []
    if consumption_grant is not None and base_commit_sha is not None:
        try:
            verify_consumption_grant(
                consumption_grant,
                public_key=public_key,
                parameters=parameters_from_job(job, repo_path=repo_path or job["repo_path"], base_commit_sha=base_commit_sha),
                executor_id="xzenia-coder",
            )
        except RepositoryAuthorityError as exc:
            errors.append(str(exc))
    if worker_report.get("status") != "PASS":
        errors.append("worker_status_not_pass")
    if unauthorized:
        errors.append("unauthorized_changes")
    if missing_artifacts:
        errors.append("evidence_missing")
    if command_failures:
        errors.append("tests_failed")
    if changed and not changed.issubset(report_changed):
        errors.append("worker_report_omitted_changed_files")
    if before.get("state_root") == after.get("state_root"):
        errors.append("no_repository_change_observed")
    independent_test_digest = _sha256_json(independent_tests)
    final_repo_state_root = str(after.get("state_root"))
    state = "RECONCILED" if not errors else "RECONCILIATION_FAILED"
    artifact_manifest = reconciled_artifact_manifest(
        output_dir=Path(output_dir),
        authority_digest=str(consumption_grant.get("authority_digest")) if isinstance(consumption_grant, Mapping) else "",
        canonical_job_digest=str(job.get("canonical_job_digest") or canonical_job_digest(job)),
        base_commit_sha=base_commit_sha or "",
        final_repo_state_root=final_repo_state_root,
        independent_acceptance_test_digest=independent_test_digest,
        reconciliation_state=state,
    )
    (Path(output_dir) / "reconciled-artifact-manifest.json").write_text(
        json.dumps(artifact_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "state": state,
        "errors": errors,
        "changed_files": sorted(changed),
        "unauthorized_changes": unauthorized,
        "tests_passed": not command_failures,
        "independent_tests": independent_tests,
        "artifact_manifest": artifact_manifest,
        "authoritative_artifact_root": artifact_manifest["manifest_hash"],
        "worker_hashes_json_trust_level": "untrusted_evidence",
        "worker_hash_errors": worker_hash_errors,
    }


def reconciled_artifact_manifest(
    *,
    output_dir: Path,
    authority_digest: str,
    canonical_job_digest: str,
    base_commit_sha: str,
    final_repo_state_root: str,
    independent_acceptance_test_digest: str,
    reconciliation_state: str,
) -> dict[str, Any]:
    artifacts = []
    for name in REQUIRED_WORKER_ARTIFACTS:
        path = output_dir / name
        artifacts.append(
            {
                "path": name,
                "sha256": _optional_sha256(path),
                "present": path.exists(),
            }
        )
    manifest = {
        "kind": RECONCILED_ARTIFACT_MANIFEST_KIND,
        "authority_digest": authority_digest,
        "canonical_job_digest": canonical_job_digest,
        "base_commit_sha": base_commit_sha,
        "final_repo_state_root": final_repo_state_root,
        "artifacts": artifacts,
        "independent_acceptance_test_digest": independent_acceptance_test_digest,
        "reconciliation_state": reconciliation_state,
        "worker_hashes_json_trust_level": "untrusted_evidence",
    }
    manifest["manifest_hash"] = hash_record(manifest)
    return manifest


def run_acceptance_tests(repo_path: str | Path, commands: Any) -> list[dict[str, Any]]:
    results = []
    for command in commands:
        argv = _canonical_command(command)
        start = time.time()
        completed = subprocess.run(
            argv,
            cwd=Path(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        results.append(
            {
                "command": argv,
                "returncode": completed.returncode,
                "stdout_sha256": _sha256_text(completed.stdout),
                "stderr_sha256": _sha256_text(completed.stderr),
                "duration_ms": int((time.time() - start) * 1000),
            }
        )
    return results


def verify_hashes_json(output_dir: Path) -> list[str]:
    hashes = _read_json(output_dir / "hashes.json", default={})
    if not isinstance(hashes, Mapping):
        return ["hashes_json_invalid"]
    errors = []
    for name, expected in hashes.items():
        if not isinstance(name, str) or not isinstance(expected, str) or len(expected) != 64:
            continue
        actual = _optional_sha256(output_dir / name)
        if actual != expected:
            errors.append(name)
    return errors


def git_head(repo_path: str | Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(repo_path),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()


def _insert_consumption_claim(
    *,
    path: Path,
    permit_hash: str,
    nonce: str,
    executor_id: str,
    consumed_at: str,
) -> None:
    for attempt in range(20):
        database = sqlite3.connect(path, isolation_level=None, timeout=30)
        try:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS permit_claims (
                    permit_hash TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL UNIQUE,
                    executor_id TEXT NOT NULL,
                    executing_at TEXT NOT NULL,
                    consumed_at TEXT NOT NULL
                )
                """
            )
            database.execute("BEGIN IMMEDIATE")
            try:
                database.execute(
                    """
                    INSERT INTO permit_claims
                        (permit_hash, nonce, executor_id, executing_at, consumed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (permit_hash, nonce, executor_id, consumed_at, consumed_at),
                )
                database.execute("COMMIT")
                return
            except sqlite3.IntegrityError as exc:
                database.execute("ROLLBACK")
                raise RepositoryAuthorityError("authority_replayed") from exc
            except Exception:
                database.execute("ROLLBACK")
                raise
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 19:
                raise
            time.sleep(0.05)
        finally:
            database.close()


def _run_dispatcher(
    dispatcher_path: Path,
    *,
    job_file: Path,
    repo_path: Path,
    output_dir: Path,
    consumption_file: Path,
    timeout: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(dispatcher_path),
            "--job-file",
            str(job_file),
            "--repo-path",
            str(repo_path),
            "--output-dir",
            str(output_dir),
            "--proofrail-consumption-file",
            str(consumption_file),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        parsed = {}
    return {
        "returncode": completed.returncode,
        "stdout_sha256": _sha256_text(completed.stdout),
        "stderr_sha256": _sha256_text(completed.stderr),
        "result": parsed,
    }


def _read_worker_report(output_dir: Path, *, timeout_seconds: int) -> dict[str, Any]:
    report = output_dir / "final_report.json"
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if report.exists():
            data = _read_json(report, default={})
            if data.get("status") in TERMINAL_WORKER_STATES:
                return data
        time.sleep(0.1)
    raise RepositoryAuthorityError("worker_timeout")


def _mapping(document: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = document.get(field)
    if not isinstance(value, Mapping):
        raise RepositoryAuthorityError(f"{field}_missing")
    return value


def _required_text(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise RepositoryAuthorityError(f"{field}_missing")
    return value


def _require_digest(value: object, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise RepositoryAuthorityError(f"{field}_invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise RepositoryAuthorityError(f"{field}_invalid") from exc


def _canonical_command(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RepositoryAuthorityError("invalid_command")
    return [str(item) for item in value]


def _public_key_hex(value: Ed25519PublicKey | bytes) -> str:
    if isinstance(value, bytes):
        return value.hex()
    return value.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _git_lines(repo_path: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.stdout.splitlines()


def _read_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _optional_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return _sha256_bytes(path.read_bytes())


def _sha256_json(value: Any) -> str:
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp_ms() -> str:
    return str(int(time.time() * 1000))

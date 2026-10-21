from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from tempfile import TemporaryDirectory
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
WORKER_REGISTRY_KIND = "proofrail.worker-registry.v1"
DEFAULT_EXECUTOR_CONTRACT_VERSION = "xzenia-coder.v1"
DISPATCH_SUPERVISION_GRACE_SECONDS = 30
# Repository files that configure what git executes (hooks, fsmonitor,
# filters, excludes). A worker that changes any of them must fail
# reconciliation before the reconciler runs git in that repository.
GIT_CONTROL_SURFACES = (
    ".git/config",
    ".git/hooks",
    ".git/info",
    ".git/modules",
    # Redirect where git reads config/objects from: commondir and worktrees
    # can point config at another file; alternates add foreign object stores.
    ".git/commondir",
    ".git/worktrees",
    ".git/objects/info",
    # Replace refs make git substitute one object for another (a committed
    # file can be hidden from every git view); shallow grafts rewrite history.
    ".git/refs/replace",
    ".git/shallow",
)
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
    executor_contract_version: str | None = None,
    executable_identity_digest: str | None = None,
) -> dict[str, Any]:
    _require_digest(canonical_job_digest, "canonical_job_digest")
    parameters = {
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
    if executor_contract_version is not None:
        parameters["executor_contract_version"] = str(executor_contract_version)
    if executable_identity_digest is not None:
        _require_digest(executable_identity_digest, "executable_identity_digest")
        parameters["executable_identity_digest"] = executable_identity_digest
    return parameters


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
    executor_contract_version: str | None = None,
    executable_identity_digest: str | None = None,
) -> dict[str, Any]:
    _require_digest(authority_digest, "authority_digest")
    _require_digest(str(parameters.get("canonical_job_digest")), "canonical_job_digest")
    executor_contract_version = executor_contract_version or parameters.get("executor_contract_version")
    executable_identity_digest = executable_identity_digest or parameters.get("executable_identity_digest")
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
    if executor_contract_version is not None:
        record["executor_contract_version"] = str(executor_contract_version)
    if executable_identity_digest is not None:
        _require_digest(str(executable_identity_digest), "executable_identity_digest")
        record["executable_identity_digest"] = str(executable_identity_digest)
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
    for field in ("executor_contract_version", "executable_identity_digest"):
        if field in parameters and grant.get(field) != parameters[field]:
            raise RepositoryAuthorityError(f"{field}_mismatch")
    expiry = datetime.fromisoformat(str(grant["expires_at"]).replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if current.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
        raise RepositoryAuthorityError("consumption_grant_expired")
    return True


def default_consumption_trust_store_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "proofrail-consumption-trust-store.json"


def default_worker_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "proofrail-worker-registry.json"


def default_dispatch_claims_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "proofrail-dispatch-claims.sqlite3"


def record_dispatch_claim(
    *,
    authority_digest: str,
    authority_nonce: str,
    grant_digest: str,
    executor_id: str,
    path: str | Path | None = None,
) -> None:
    """Atomically record that a consumption grant started a worker.

    The authority is single-use at consumption; this makes the *grant*
    single-use at dispatch, so one grant cannot start the worker repeatedly.
    """
    _require_digest(authority_digest, "authority_digest")
    target = Path(path) if path is not None else default_dispatch_claims_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(target, isolation_level=None, timeout=30)
    try:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS dispatch_claims (
                authority_digest TEXT PRIMARY KEY,
                authority_nonce TEXT NOT NULL UNIQUE,
                grant_digest TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                dispatched_at TEXT NOT NULL
            )
            """
        )
        database.execute("BEGIN IMMEDIATE")
        try:
            database.execute(
                "INSERT INTO dispatch_claims VALUES (?, ?, ?, ?, ?)",
                (authority_digest, authority_nonce, grant_digest, executor_id, _timestamp_ms()),
            )
            database.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            database.execute("ROLLBACK")
            raise RepositoryAuthorityError("consumption_grant_replayed") from exc
    finally:
        database.close()


def executable_fingerprint(path: str | Path) -> str:
    target = Path(path)
    if not target.exists() or not target.is_file() or target.is_symlink():
        raise RepositoryAuthorityError("installed_worker_missing")
    return _sha256_file(target)


def write_worker_registry(
    path: str | Path,
    *,
    workers: Mapping[str, Mapping[str, Any] | str | Path],
) -> dict[str, Any]:
    entries = []
    for executor_id, value in sorted(workers.items()):
        if isinstance(value, Mapping):
            worker_path = Path(_required_text(value, "path")).resolve()
            contract_version = str(value.get("contract_version") or DEFAULT_EXECUTOR_CONTRACT_VERSION)
            fingerprint = str(value.get("executable_identity_digest") or executable_fingerprint(worker_path))
            environment = sorted({str(name) for name in value.get("environment", [])})
        else:
            worker_path = Path(value).resolve()
            contract_version = DEFAULT_EXECUTOR_CONTRACT_VERSION
            fingerprint = executable_fingerprint(worker_path)
            environment = []
        _require_digest(fingerprint, "executable_identity_digest")
        entries.append({
            "executor_id": str(executor_id),
            "contract_version": contract_version,
            "path": str(worker_path),
            "executable_identity_digest": fingerprint,
            "environment": environment,
        })
    registry = {"kind": WORKER_REGISTRY_KIND, "workers": entries}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registry


def load_worker_registry_executor(
    executor_id: str,
    *,
    contract_version: str | None = None,
    executable_identity_digest: str | None = None,
) -> dict[str, str]:
    registry = _read_json(default_worker_registry_path(), default=None)
    if not isinstance(registry, Mapping) or registry.get("kind") != WORKER_REGISTRY_KIND:
        raise RepositoryAuthorityError("worker_registry_invalid")
    matches = [
        item for item in registry.get("workers", [])
        if isinstance(item, Mapping) and item.get("executor_id") == executor_id
    ]
    if contract_version is not None:
        matches = [item for item in matches if item.get("contract_version") == contract_version]
    if len(matches) != 1:
        raise RepositoryAuthorityError("untrusted_executor_identity")
    entry = matches[0]
    path_text = entry.get("path")
    entry_contract_version = entry.get("contract_version")
    entry_fingerprint = entry.get("executable_identity_digest")
    if not isinstance(path_text, str) or not isinstance(entry_contract_version, str) or not isinstance(entry_fingerprint, str):
        raise RepositoryAuthorityError("worker_registry_invalid")
    _require_digest(entry_fingerprint, "executable_identity_digest")
    if executable_identity_digest is not None and entry_fingerprint != executable_identity_digest:
        raise RepositoryAuthorityError("executor_fingerprint_mismatch")
    worker_path = Path(path_text)
    actual = executable_fingerprint(worker_path)
    if actual != entry_fingerprint:
        raise RepositoryAuthorityError("installed_worker_fingerprint_mismatch")
    environment = entry.get("environment", [])
    if not isinstance(environment, list):
        raise RepositoryAuthorityError("worker_registry_invalid")
    _validate_environment_names(environment)
    return {
        "executor_id": executor_id,
        "contract_version": entry_contract_version,
        "path": str(worker_path.resolve()),
        "executable_identity_digest": entry_fingerprint,
        "environment": list(environment),
    }


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
        if authority is None:
            raise RepositoryAuthorityError("authority_missing")
        unsafe = unsafe_repository_reasons(repo_path)
        if unsafe:
            # Refuse before consuming authority: the reconciler could not run
            # git here without executing repository-chosen configuration.
            raise RepositoryAuthorityError("unsafe_repository:" + ",".join(unsafe))
        current_base = git_head(repo_path)
        # The governor's authority must name the installed worker: parameters
        # include its contract and fingerprint, so an envelope minted for a
        # different (or unspecified) worker fails verification here.
        worker = load_worker_registry_executor(self.executor_id)
        parameters = parameters_from_job(
            job, repo_path=repo_path, base_commit_sha=current_base, worker=worker,
        )
        _preflight_descendant_containment()
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
            baseline=before,
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
    worker: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Authority parameters for a job.

    Pass `worker` (from load_worker_registry_executor) to bind the exact
    executor contract and executable fingerprint into the parameters the
    governor signs. The adapter always does; verifiers that only need to
    re-derive job/repository bindings may omit it.
    """
    canonical_job = canonicalize_job(job, repo_path=repo_path)
    return repository_change_parameters(
        executor_contract_version=worker["contract_version"] if worker else None,
        executable_identity_digest=worker["executable_identity_digest"] if worker else None,
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
    contradictions = [
        path for path in canonical["allowed_paths"]
        if is_forbidden_path(path, canonical["forbidden_paths"])
    ]
    if contradictions:
        # A path both allowed and forbidden makes the signed scope
        # self-contradictory; refuse before any authority is minted or spent.
        raise RepositoryAuthorityError("allowed_path_forbidden:" + ",".join(contradictions))
    return canonical


def is_forbidden_path(path: str, forbidden_paths: list[str]) -> bool:
    """A forbidden entry covers that exact path and, as a directory, everything under it."""
    candidate = path.strip("/")
    for entry in forbidden_paths:
        prefix = str(entry).strip("/")
        if prefix and (candidate == prefix or candidate.startswith(prefix + "/")):
            return True
    return False


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
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Observe repository state without trusting worker-controlled git config.

    The working tree and git's control surfaces (config, hooks, info, modules)
    are snapshotted from the filesystem first, without running git. When a
    `baseline` observation is supplied and any control surface changed, the
    observation stops there: running git would execute worker-chosen hooks,
    fsmonitor commands or filters. Files hidden from git (excludes, ignores)
    still appear in the filesystem tree comparison.
    """
    repo = Path(repo_path).resolve()
    control = _control_snapshot(repo)
    tree = _tree_snapshot(repo)
    tree_changed: set[str] = set()
    if baseline is not None:
        before_tree = baseline.get("tree", {})
        tree_changed = {
            path for path in set(before_tree) | set(tree)
            if before_tree.get(path) != tree.get(path)
        }
        if control != baseline.get("control") or unsafe_repository_reasons(repo):
            before_control = baseline.get("control", {})
            touched = sorted(
                path for path in set(before_control) | set(control)
                if before_control.get(path) != control.get(path)
            )
            state = {
                "head": None,
                "control_tampered": True,
                "control": control,
                "tree": tree,
                "changed_files": sorted(tree_changed | set(touched)),
                "diff_sha256": None,
                "allowed_file_hashes": {},
            }
            state["state_root"] = hash_record({"kind": "proofrail.repository-observation.v1", **state})
            return state
    changed_files = set(tree_changed)
    for line in _git_lines(repo, ["status", "--porcelain", "--untracked-files=all", "--ignored", "--ignore-submodules=all"]):
        if len(line) >= 4:
            changed_files.add(line[3:])
    if base_commit_sha:
        for args in (
            ["diff", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--name-only", base_commit_sha, "HEAD"],
            ["diff", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--name-only", base_commit_sha],
            ["diff", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--cached", "--name-only"],
        ):
            changed_files.update(_git_lines(repo, args))
    diff = subprocess.run(
        [_git_executable(), *_HARDENED_GIT, "diff", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--binary",
         *([base_commit_sha] if base_commit_sha else [])],
        cwd=repo,
        env=_git_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout
    file_hashes = {}
    for rel in allowed_paths:
        entry = tree.get(rel)
        if entry is not None and entry.startswith("file:"):
            file_hashes[rel] = entry[len("file:"):]
    state = {
        "head": git_head(repo),
        "control_tampered": False,
        "control": control,
        "tree": tree,
        "changed_files": sorted(path for path in changed_files if path),
        "diff_sha256": _sha256_text(diff),
        "allowed_file_hashes": file_hashes,
    }
    state["state_root"] = hash_record({"kind": "proofrail.repository-observation.v1", **state})
    return state


_HARDENED_GIT = (
    "--no-replace-objects",
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.untrackedCache=false",
    "-c", "core.excludesFile=/dev/null",
)


# Installation-trusted search path for git and worker interpreters. The
# caller's PATH is never used: a writable directory placed first in it could
# substitute `git` (defeating the live-base and reconciliation checks).
TRUSTED_PATH = "/usr/local/bin:/usr/bin:/bin"
# Variables a worker always receives; anything else must be named by the
# installation's worker registry entry ("environment").
def _validate_environment_names(names):
    # Registry additions are application credentials, never runtime controls.
    # Restrict the grammar rather than trying to enumerate every loader variable.
    for name in names:
        if (not isinstance(name, str) or
                not re.fullmatch(r"[A-Z][A-Z0-9_]*_(?:API_KEY|TOKEN|SECRET)", name) or
                name.startswith(("LD_", "DYLD_", "PYTHON", "GIT_", "BASH_"))):
            raise RepositoryAuthorityError("worker_environment_name_forbidden")


def _git_executable() -> str:
    found = shutil.which("git", path=TRUSTED_PATH)
    if not found:
        raise RepositoryAuthorityError("trusted_git_missing")
    return found


def worker_environment(allowed_names: list[str] | tuple[str, ...] = ()) -> dict[str, str]:
    """Fixed runtime settings plus explicitly enrolled application credentials."""
    _validate_environment_names(allowed_names)
    env = {"PATH": TRUSTED_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0"}
    for name in allowed_names:
        if name in os.environ:
            env[name] = os.environ[name]
    return env


@contextmanager
def execution_environment(allowed_names=()):
    # Fixed parent; tempfile must not honor the caller's TMPDIR.
    with TemporaryDirectory(prefix="proofrail-execution-", dir="/tmp") as root:
        home, temporary = Path(root) / "home", Path(root) / "tmp"
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
        env = worker_environment(allowed_names)
        env.update(HOME=str(home), TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
        yield env


def _git_env() -> dict[str, str]:
    """No caller loader, interpreter, git config or credential variables."""
    env = worker_environment(())
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1"})
    return env


def _entry_digest(path: Path) -> str:
    """Describe one filesystem entry without following symlinks."""
    if path.is_symlink():
        return "symlink:" + _sha256_text(os.readlink(path))
    if path.is_file():
        return "file:" + _sha256_file(path)
    if path.is_dir():
        return "dir"
    return "other"


def _control_snapshot(repo: Path) -> dict[str, str]:
    snapshot = {".git": _entry_digest(repo / ".git") if (repo / ".git").exists() or (repo / ".git").is_symlink() else "absent"}
    for surface in GIT_CONTROL_SURFACES:
        root = repo / surface
        if not root.exists() and not root.is_symlink():
            snapshot[surface] = "absent"
            continue
        snapshot[surface] = _entry_digest(root)
        if root.is_dir() and not root.is_symlink():
            for item in sorted(root.rglob("*")):
                snapshot[str(item.relative_to(repo))] = _entry_digest(item)
    return snapshot


def unsafe_repository_reasons(repo: str | Path) -> list[str]:
    """Repository shapes whose git config the reconciler cannot neutralise.

    `include`/`includeIf` in .git/config can pull config (filters, hooks)
    from worker-writable files; a nested `.git` brings its own config and
    filters into the reconciler's git calls.
    """
    root = Path(repo).resolve()
    reasons = []
    config = root / ".git" / "config"
    if config.is_file() and re.search(r"^\s*\[\s*include(if)?\b", config.read_text(errors="replace"),
                                      re.IGNORECASE | re.MULTILINE):
        reasons.append("config_include")
    for current, dirs, files in os.walk(root, followlinks=False):
        here = Path(current)
        if here == root:
            dirs[:] = [d for d in dirs if d != ".git"]
            continue
        if ".git" in dirs or ".git" in files:
            reasons.append("nested_git:" + str((here / ".git").relative_to(root)))
            dirs[:] = [d for d in dirs if d != ".git"]
    return reasons


def _tree_snapshot(repo: Path) -> dict[str, str]:
    """Hash every working-tree entry outside .git, including ignored files."""
    snapshot: dict[str, str] = {}
    for current, dirs, files in os.walk(repo, followlinks=False):
        here = Path(current)
        if here == repo:
            dirs[:] = [d for d in dirs if d != ".git"]
        for name in [*files, *[d for d in dirs if (here / d).is_symlink()]]:
            item = here / name
            snapshot[str(item.relative_to(repo))] = _entry_digest(item)
    return snapshot


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
    control_tampered = after.get("control_tampered") is True
    tests_modified_repository = False
    independent_tests = []
    if control_tampered:
        # Do not execute anything in a repository whose git control files the
        # worker changed (hooks, fsmonitor, filters, excludes).
        independent_tests = []
    elif repo_path is not None:
        independent_tests = run_acceptance_tests(
            repo_path, job.get("acceptance_tests", []),
            timeout_seconds=int(job.get("max_runtime_seconds", 60)),
        )
        # Acceptance tests run worker-written code after the repository was
        # observed; they must not change it, or the attested final state is stale.
        if "tree" in after and _tree_snapshot(Path(repo_path).resolve()) != after["tree"]:
            tests_modified_repository = True
        # Never run git here: the acceptance tests may have planted executable
        # configuration after the initial control snapshot.
        if _control_snapshot(Path(repo_path).resolve()) != after.get("control"):
            control_tampered = True
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
    forbidden_changes = sorted(
        path for path in changed if is_forbidden_path(path, list(job.get("forbidden_paths", [])))
    )
    if control_tampered:
        errors.append("repository_control_tampered")
    if forbidden_changes:
        errors.append("forbidden_path_changed")
    if tests_modified_repository:
        errors.append("acceptance_tests_modified_repository")
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
        "forbidden_changes": forbidden_changes,
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


def run_acceptance_tests(
    repo_path: str | Path,
    commands: Any,
    *,
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]:
    """Run signed acceptance tests with best-effort process-group cleanup.

    NOT an external sandbox. Detached descendants can hold output pipes open
    beyond the timeout and mutate files after return. See the containment design.

    The commands execute worker-written code, so each runs in its own session
    with a minimal environment (no caller secrets, trusted PATH, no bytecode
    writes), within the signed runtime limit; its whole process group is
    killed when it finishes or times out. A timeout is a failed test, not an
    exception. Output is hashed as bytes.
    """
    results = []
    for command in commands:
        argv = _canonical_command(command)
        start = time.time()
        timed_out = False
        with execution_environment() as env:
            proc = subprocess.Popen(
                argv,
                cwd=Path(repo_path),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=max(1, int(timeout_seconds)))
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_group(proc.pid)
                stdout, stderr = proc.communicate()
            _kill_process_group(proc.pid)
        results.append(
            {
                "command": argv,
                "returncode": None if timed_out else proc.returncode,
                "timed_out": timed_out,
                "stdout_sha256": _sha256_bytes(stdout or b""),
                "stderr_sha256": _sha256_bytes(stderr or b""),
                "duration_ms": int((time.time() - start) * 1000),
            }
        )
    return results


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


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
        [_git_executable(), *_HARDENED_GIT, "rev-parse", "HEAD"],
        cwd=Path(repo_path),
        env=_git_env(),
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


def _preflight_descendant_containment() -> None:
    # Trusted installed helper, same interpreter and clean environment as the
    # actual dispatcher. Never probe by executing caller-provided job code.
    probe = Path(__file__).resolve().parents[2] / "proofrail" / "runtime_capability.py"
    try:
        with execution_environment() as env:
            result = subprocess.run(
                [sys.executable, "-I", str(probe)], env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        raise RepositoryAuthorityError("descendant_containment_unavailable") from None
    if result.returncode != 0:
        raise RepositoryAuthorityError("descendant_containment_unavailable")


def _run_dispatcher(
    dispatcher_path: Path,
    *,
    job_file: Path,
    repo_path: Path,
    output_dir: Path,
    consumption_file: Path,
    timeout: int,
) -> dict[str, Any]:
    worker = load_worker_registry_executor("xzenia-coder")
    with execution_environment(worker.get("environment", [])) as env:
        completed = subprocess.run(
            [
                sys.executable, "-I", str(dispatcher_path),
                "--job-file",
                str(job_file),
                "--repo-path",
                str(repo_path),
                "--output-dir",
                str(output_dir),
                "--proofrail-consumption-file",
                str(consumption_file),
            ],
            env=env,
            capture_output=True,
            text=True,
            # The dispatcher supervises the worker for up to `timeout` seconds and
            # then kills its process group; allow it time to finish doing so.
            timeout=timeout + DISPATCH_SUPERVISION_GRACE_SECONDS,
            check=False,
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        parsed = {}
    if completed.returncode != 0:
        # The authority is already spent; surface the refusal instead of
        # polling for a worker that was never started.
        reason = (completed.stderr.strip().splitlines() or ["unknown"])[-1]
        raise RepositoryAuthorityError(f"dispatcher_failed:{reason}")
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
        [_git_executable(), *_HARDENED_GIT, *args],
        cwd=repo_path,
        env=_git_env(),
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
    return _sha256_file(path)


def _sha256_json(value: Any) -> str:
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Hash a file in fixed-size chunks so large files cannot exhaust memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_ms() -> str:
    return str(int(time.time() * 1000))

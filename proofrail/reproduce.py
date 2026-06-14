from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .anchor import decode_public_key, verify_anchor
from .checkpoint import verify_checkpoint, verify_ledger
from .core import ProofRailError
from .crypto import verify_signature
from .permit import PermitError, verify_permit
from .trust import replay_claim_exists, verify_trust_checkpoint


def reproduce_artifact(
    artifact_dir: str | Path,
    *,
    schemas_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Independently verify one portable ProofRail reproduction bundle."""
    artifact = Path(artifact_dir)
    if artifact.is_symlink() or not artifact.is_dir():
        raise ProofRailError("Reproduction artifact must be a real directory")
    unsafe_entries = sorted(
        path.name
        for path in artifact.iterdir()
        if path.is_symlink() or not path.is_file()
    )
    if unsafe_entries:
        raise ProofRailError(
            "Reproduction artifact contains unsafe entries: " + ",".join(unsafe_entries)
        )
    schema_root = Path(schemas_dir) if schemas_dir else Path(__file__).resolve().parents[1] / "schemas"
    checks: list[dict[str, Any]] = []

    manifest = _read_json(artifact / "reproduction-manifest.json")
    manifest_key = decode_public_key(
        (artifact / "manifest-public-key.txt").read_text(encoding="utf-8")
    )
    checks.append(_signature_check("manifest_signature", manifest, manifest_key))
    checks.extend(_inventory_checks(artifact, manifest))
    checks.append(_undeclared_files_check(artifact, manifest))

    schemas = _load_schemas(schema_root)
    checks.append(
        _check(
            "schemas_valid",
            True,
            f"{len(schemas)} Draft 2020-12 schemas validated",
        )
    )
    checks.append(
        _schema_check(
            "manifest_schema",
            manifest,
            schemas["reproduction_manifest.schema.json"],
        )
    )

    trust_checkpoint = _read_json(artifact / "trust-checkpoint.json")
    permit_trust_checkpoint = _read_json(artifact / "permit-trust-checkpoint.json")
    trust_key = decode_public_key(
        (artifact / "trust-checkpoint-public-key.txt").read_text(encoding="utf-8")
    )
    checks.append(_signature_check("trust_checkpoint_signature", trust_checkpoint, trust_key))
    checks.append(
        _signature_check(
            "permit_trust_checkpoint_signature",
            permit_trust_checkpoint,
            trust_key,
        )
    )
    checks.append(
        _schema_check(
            "trust_checkpoint_schema",
            trust_checkpoint,
            schemas["trust_checkpoint.schema.json"],
        )
    )
    checks.append(
        _schema_check(
            "permit_trust_checkpoint_schema",
            permit_trust_checkpoint,
            schemas["trust_checkpoint.schema.json"],
        )
    )

    ledger_path = artifact / "proofrail-ledger.jsonl"
    ledger = verify_ledger(ledger_path)
    checks.append(_check("ledger_verifies", ledger["valid"], ",".join(ledger["errors"])))

    checkpoint = _read_json(artifact / "proofrail-checkpoint.json")
    checkpoint_key = decode_public_key(
        (artifact / "checkpoint-public-key.txt").read_text(encoding="utf-8")
    )
    checkpoint_result = verify_checkpoint(checkpoint, ledger_path, public_key=checkpoint_key)
    checks.append(
        _check(
            "checkpoint_verifies",
            checkpoint_result["valid"],
            ",".join(checkpoint_result["errors"]),
        )
    )
    trust_result = verify_trust_checkpoint(
        trust_checkpoint,
        registry_path=artifact / "replay-registry.sqlite3",
        public_key=trust_key,
    )
    trust_roots = trust_checkpoint.get("roots")
    ledger_checkpoint_bound = (
        isinstance(trust_roots, Mapping)
        and trust_roots.get("ledger_checkpoint") == checkpoint.get("record_hash")
    )
    checks.append(
        _check(
            "trust_checkpoint_verifies",
            trust_result["valid"] and ledger_checkpoint_bound,
            ",".join(trust_result["errors"])
            if trust_result["errors"]
            else f"ledger_checkpoint_bound={ledger_checkpoint_bound}",
        )
    )
    chain_valid = (
        trust_checkpoint.get("previous_checkpoint_hash")
        == permit_trust_checkpoint.get("record_hash")
    )
    checks.append(
        _check(
            "trust_checkpoint_chain",
            chain_valid,
            str(trust_checkpoint.get("previous_checkpoint_hash")),
        )
    )

    anchor = _read_json(artifact / "anchor.json")
    anchor_key = decode_public_key(
        (artifact / "anchor-public-key.txt").read_text(encoding="utf-8")
    )
    anchor_result = verify_anchor(
        anchor,
        ledger_path,
        public_key=anchor_key,
        expected_trust_checkpoint_hash=str(trust_checkpoint.get("record_hash")),
    )
    checks.append(
        _check("anchor_verifies", anchor_result["valid"], ",".join(anchor_result["errors"]))
    )
    checks.append(_schema_check("anchor_schema", anchor, schemas["external_anchor.schema.json"]))

    context = _read_json(artifact / "permit-context.json")
    verifier_key = decode_public_key(
        (artifact / "verifier-public-key.txt").read_text(encoding="utf-8")
    )
    valid_permit = _read_json(artifact / "valid-permit.json")
    checks.append(_schema_check("valid_permit_schema", valid_permit, schemas["permit.schema.json"]))
    checks.append(
        _permit_check(
            "valid_permit_verifies",
            valid_permit,
            context=context,
            public_key=verifier_key,
            expected_valid=True,
        )
    )
    invalid_permit = _read_json(artifact / "invalid-permit.json")
    checks.append(
        _permit_check(
            "invalid_permit_denied",
            invalid_permit,
            context=context,
            public_key=verifier_key,
            expected_valid=False,
        )
    )
    consumption_receipt = _read_json(artifact / "consumption-receipt.json")
    checks.append(
        _schema_check(
            "consumption_receipt_schema",
            consumption_receipt,
            schemas["consumption_receipt.schema.json"],
        )
    )
    executor_key = decode_public_key(
        (artifact / "executor-public-key.txt").read_text(encoding="utf-8")
    )
    receipt_signature = _signature_check(
        "consumption_receipt_signature",
        consumption_receipt,
        executor_key,
    )
    checks.append(receipt_signature)
    receipt_matches = (
        receipt_signature["passed"]
        and consumption_receipt.get("state") == "CONSUMED"
        and consumption_receipt.get("permit_hash") == valid_permit.get("record_hash")
        and consumption_receipt.get("nonce") == valid_permit.get("nonce")
        and consumption_receipt.get("trust_checkpoint_before")
        == permit_trust_checkpoint.get("record_hash")
        and consumption_receipt.get("trust_checkpoint_after")
        == trust_checkpoint.get("record_hash")
        and consumption_receipt.get("next_replay_root")
        == trust_checkpoint.get("roots", {}).get("replay")
        and replay_claim_exists(
            artifact / "replay-registry.sqlite3",
            str(valid_permit.get("record_hash")),
        )
    )
    checks.append(
        _check(
            "consumed_permit_verifies",
            receipt_matches,
            str(consumption_receipt.get("permit_hash")),
        )
    )

    tampered = verify_anchor(
        anchor,
        artifact / "tampered-ledger.jsonl",
        public_key=anchor_key,
        expected_trust_checkpoint_hash=str(trust_checkpoint.get("record_hash")),
    )
    checks.append(
        _check("tampered_artifact_fails", not tampered["valid"], ",".join(tampered["errors"]))
    )

    expected_validation_hash = manifest.get("validation_report_sha256")
    observed_validation_hash = _sha256(artifact / "VALIDATION_REPORT.md")
    checks.append(
        _check(
            "validation_report_hash_matches",
            expected_validation_hash == observed_validation_hash,
            observed_validation_hash,
        )
    )
    expected_checks = manifest.get("expected_checks")
    passed_names = {check["name"] for check in checks if check["passed"]}
    expected_covered = isinstance(expected_checks, list) and set(expected_checks).issubset(
        passed_names
    )
    checks.append(
        _check(
            "expected_check_coverage",
            expected_covered,
            ",".join(sorted(set(expected_checks or []) - passed_names)),
        )
    )
    return {
        "valid": all(check["passed"] for check in checks),
        "artifact": str(artifact),
        "checks": checks,
    }


def _inventory_checks(artifact: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        return [_check("manifest_inventory", False, "manifest files mapping missing")]
    checks = []
    for name, expected in sorted(files.items()):
        path = artifact / str(name)
        safe = not Path(str(name)).is_absolute() and ".." not in Path(str(name)).parts
        observed = _sha256(path) if safe and path.is_file() and not path.is_symlink() else None
        checks.append(
            _check(
                f"file_hash:{name}",
                safe and observed == expected,
                str(observed),
            )
        )
    return checks


def _undeclared_files_check(artifact: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        return _check("no_undeclared_files", False, "manifest files mapping missing")
    allowed = set(str(name) for name in files) | {"reproduction-manifest.json"}
    actual = {path.name for path in artifact.iterdir() if path.is_file()}
    undeclared = sorted(actual - allowed)
    return _check("no_undeclared_files", not undeclared, ",".join(undeclared))


def _load_schemas(path: Path) -> dict[str, dict[str, Any]]:
    schemas = {}
    for schema_path in sorted(path.glob("*.json")):
        schema = _read_json(schema_path)
        Draft202012Validator.check_schema(schema)
        schemas[schema_path.name] = schema
    required = {
        "permit.schema.json",
        "trust_checkpoint.schema.json",
        "external_anchor.schema.json",
        "reproduction_manifest.schema.json",
        "consumption_receipt.schema.json",
    }
    if not required.issubset(schemas):
        raise ProofRailError("Required authority schemas are missing")
    return schemas


def _schema_check(name: str, value: Any, schema: Mapping[str, Any]) -> dict[str, Any]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.path),
    )
    return _check(name, not errors, "; ".join(error.message for error in errors))


def _signature_check(name: str, value: Mapping[str, Any], public_key: Any) -> dict[str, Any]:
    try:
        verify_signature(value, public_key)
        return _check(name, True, "valid")
    except ProofRailError as exc:
        return _check(name, False, str(exc))


def _permit_check(
    name: str,
    permit: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    public_key: Any,
    expected_valid: bool,
) -> dict[str, Any]:
    roots = context["roots"]
    effect = context["effect"]
    trust = context["trust"]
    try:
        verify_permit(
            permit,
            public_key=public_key,
            expected_identity_root=roots["identity"],
            expected_evidence_root=roots["evidence"],
            expected_policy_root=roots["policy"],
            expected_state_root=roots["state"],
            expected_approval_digest=context["approval_digest"],
            repository=effect["repository"],
            pull_number=effect["pull_number"],
            expected_head_sha=effect["expected_head_sha"],
            merge_method=effect["merge_method"],
            now=datetime.fromisoformat(str(context["verification_time"]).replace("Z", "+00:00")),
            current_checkpoint_epoch=trust["checkpoint_epoch"],
            current_monotonic_counter=trust["monotonic_counter"],
            expected_replay_root=trust["replay_root"],
            expected_checkpoint_root=trust["checkpoint_root"],
            expected_observation_root=trust["observation_root"],
        )
        valid = True
        detail = "valid"
    except PermitError as exc:
        valid = False
        detail = exc.code
    return _check(name, valid is expected_valid, detail)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofRailError(f"Unable to read JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProofRailError(f"Expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}

"""Regression isolation for 15 verifier guards that survived the clean af6018e sweep.

Each assertion names the particular verifier check whose enforcement it
requires, rather than merely checking that SOME OTHER dimension already failed.
This is project-authored differential testing; it is not an external audit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conftest import PILOT
from evidence_export import export_case
from test_bundle import full_case, resum
from verify_bundle import Report, verify


@pytest.fixture
def bundle(env):
    problem_id = full_case(env)
    return export_case(
        env.w["buyer-a"], env.p, "tenant-a", problem_id, env.tmp / "isolated-bundle"
    )


def update_json(root: Path, relative: str, update, *, refresh_checksums=True):
    path = root / relative
    record = json.loads(path.read_text(encoding="utf-8"))
    update(record)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if refresh_checksums:
        resum(root)


def named_check(report: dict, dimension: str, name: str) -> dict:
    checks = [c for c in report["dimensions"][dimension]["checks"] if c["check"] == name]
    assert len(checks) == 1, (dimension, name, report)
    return checks[0]


def require_named_failure(bundle, dimension: str, name: str):
    report = verify(bundle)
    result = named_check(report, dimension, name)
    assert result["result"] == "FAIL", (name, result, report)
    assert report["verified"] is False


def recon_path(bundle):
    reference = json.loads((bundle / "records/authority_reference.json").read_text())
    for path in sorted((bundle / "records/observations").glob("*.json")):
        record = json.loads(path.read_text())
        if record["record_hash"] == reference["reconciliation_reference"]:
            return path
    raise AssertionError("reconciling observation not found in genuine fixture")


# 1-3: individual integrity checks must be observable even when another
# envelope/signature/presence check happens to reject the same bundle.
def test_checksum_content_mismatch_is_reported_by_its_own_check(bundle):
    path = bundle / "records/problem.json"
    path.write_bytes(path.read_bytes() + b"\n")
    require_named_failure(bundle, "integrity", "every file matches SHA256SUMS")


def test_manifest_digest_difference_is_reported_by_its_own_check(bundle):
    manifest_file = bundle / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["files"]["records/problem.json"] = "0" * 64
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    actual_hash = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    checksum = bundle / "SHA256SUMS"
    lines = checksum.read_text().splitlines()
    checksum.write_text("\n".join(
        f"{actual_hash}  manifest.json" if line.endswith("  manifest.json") else line
        for line in lines
    ) + "\n")
    require_named_failure(bundle, "integrity", "manifest lists the same digests")


def test_unrecognized_format_is_reported_by_its_own_check(bundle):
    update_json(bundle, "manifest.json", lambda m: m.update(format="unknown.case-bundle"))
    require_named_failure(bundle, "integrity", "bundle format recognised")


# 4: removing the issuer role means the verifier currently has no issuer key
# to pass downstream. Intercept at the specific guard before it reaches that
# later lookup, and assert the exact boolean the guard received.
def test_missing_admission_issuer_is_rejected_at_presence_guard(bundle, monkeypatch):
    update_json(
        bundle, "context/identity-at-admission.json",
        lambda s: [
            p["roles"].remove("authority_issuer")
            for p in s["principals"] if "authority_issuer" in p["roles"]
        ],
    )
    target = "issuer present in the admission-time identity snapshot"

    class GuardObserved(Exception):
        pass

    seen = []
    original = Report.check

    def capture_guard(self, dimension, name, ok, detail=""):
        if dimension == "authority" and name == target:
            seen.append(ok)
            raise GuardObserved()
        return original(self, dimension, name, ok, detail)

    monkeypatch.setattr(Report, "check", capture_guard)
    with pytest.raises(GuardObserved):
        verify(bundle)
    assert seen == [False], (target, seen)


# 5-9: conditions about admitted records and signed authority.
def test_state_input_consistency_has_its_own_failure(bundle):
    update_json(bundle, "context/state-inputs-at-admission.json",
                lambda s: s.update(work_state="CANCELLED"))
    require_named_failure(bundle, "authority", "state inputs describe these records at admission")


def test_approval_digest_recomputation_has_its_own_failure(bundle):
    update_json(bundle, "records/approval.json",
                lambda a: a.update(approved_maximum_cost=a["approved_maximum_cost"] + 1))
    require_named_failure(bundle, "authority", "plan and approval digests recompute")


def test_issuer_binding_has_its_own_failure(bundle):
    update_json(bundle, "records/envelope.json", lambda e: e["issuer"].update(role="governor"))
    require_named_failure(bundle, "authority", "issuer is the tenant authority issuer acting as verifier")


def test_success_predicate_binding_has_its_own_failure(bundle):
    update_json(bundle, "records/envelope.json",
                lambda e: e["observation_contract"].update(success_predicate_digest="0" * 64))
    require_named_failure(bundle, "authority", "success predicate binds the exact parameters")


def test_consumption_validity_window_has_its_own_failure(bundle):
    update_json(bundle, "records/consumption.json",
                lambda c: c["claim"].update(consumed_at="2099-01-01T00:00:00Z"))
    require_named_failure(bundle, "authority", "consumed within the envelope validity window")


# 10-13: provider observation must bind the exact operation, and every
# individual check must be enforced rather than relying on signature failure.
def test_missing_reconciliation_record_has_its_own_failure(bundle):
    update_json(bundle, "records/authority_reference.json",
                lambda r: r.update(reconciliation_reference="0" * 64))
    require_named_failure(bundle, "execution", "reconciling observation is included")


def test_observation_digest_has_its_own_failure(bundle):
    path = recon_path(bundle)
    update_json(bundle, str(path.relative_to(bundle)),
                lambda o: o.update(observation_digest="0" * 64))
    require_named_failure(bundle, "execution", "observation digest matches its findings")


def test_exact_provider_effect_has_its_own_failure(bundle):
    path = recon_path(bundle)
    def different_area(o):
        o["findings"]["work_order"]["orders"][0]["area_id"] = "WRONG-AREA"
    update_json(bundle, str(path.relative_to(bundle)), different_area)
    require_named_failure(bundle, "execution", "exactly one provider order matching every authorized parameter")


def test_provider_order_reference_binding_has_its_own_failure(bundle):
    update_json(bundle, "records/authority_reference.json",
                lambda r: r.update(provider_operation_reference="WO-OTHER"))
    require_named_failure(bundle, "execution", "the matching order is the one the reference names")


# 14-15: an outcome's own consistency and nonpayment requirements must be
# exercised, not hidden by earlier authenticity failures.
def test_outcome_reproduction_has_its_own_failure(bundle):
    # The *surviving* historical mutant is the exception-handler check at
    # verify_bundle.py:195 (constant False), not the successful comparison at
    # line 190. Force a PilotError in outcome reassessment by changing the
    # referenced authority state to EXECUTION_UNKNOWN. The verifier must
    # record that failure even though its execution dimension also fails.
    update_json(bundle, "records/authority_reference.json",
                lambda r: r.update(authority_state="EXECUTION_UNKNOWN"))
    require_named_failure(bundle, "outcome", "verdict reproduces from the included observations")


def test_no_money_moved_has_its_own_failure(bundle):
    path = sorted((bundle / "records/settlements").glob("*.json"))[0]
    update_json(bundle, str(path.relative_to(bundle)), lambda s: s.update(money_moved=True))
    require_named_failure(bundle, "outcome", "settlement is simulated (no money moved)")

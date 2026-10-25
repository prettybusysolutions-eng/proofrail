"""Prove each of the 15 verifier checks surviving sweep-af6018e is test-sensitive.

Run after the normal pilot suite:
    python review_tools/check_previous_survivors.py

This executes the real AST check-removal mutants against the specific new
negative tests. It does NOT replace a full classified sweep of all checks,
and it does not make any claim for #45/#46's additional verifier checks.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from mutate_checks import PILOT, make_copy, mutants, pytest

TESTS = {
    "every file matches SHA256SUMS": "test_checksum_content_mismatch_is_reported_by_its_own_check",
    "manifest lists the same digests": "test_manifest_digest_difference_is_reported_by_its_own_check",
    "bundle format recognised": "test_unrecognized_format_is_reported_by_its_own_check",
    "issuer present in the admission-time identity snapshot": "test_missing_admission_issuer_is_rejected_at_presence_guard",
    "state inputs describe these records at admission": "test_state_input_consistency_has_its_own_failure",
    "plan and approval digests recompute": "test_approval_digest_recomputation_has_its_own_failure",
    "issuer is the tenant authority issuer acting as verifier": "test_issuer_binding_has_its_own_failure",
    "success predicate binds the exact parameters": "test_success_predicate_binding_has_its_own_failure",
    "consumed within the envelope validity window": "test_consumption_validity_window_has_its_own_failure",
    "reconciling observation is included": "test_missing_reconciliation_record_has_its_own_failure",
    "observation digest matches its findings": "test_observation_digest_has_its_own_failure",
    "exactly one provider order matching every authorized parameter": "test_exact_provider_effect_has_its_own_failure",
    "the matching order is the one the reference names": "test_provider_order_reference_binding_has_its_own_failure",
    "verdict reproduces from the included observations": "test_outcome_reproduction_has_its_own_failure",
    "settlement is simulated (no money moved)": "test_no_money_moved_has_its_own_failure",
}


def main():
    # Historical source line numbers shift when new verifier guards are
    # inserted. Preserve the original published target *labels* and distinguish
    # the duplicated outcome name by requiring its PilotError-handler branch.
    historical = json.loads(
        (PILOT / "review_tools/results/sweep-af6018e.json").read_text()
    )
    historical_survivors = {
        r["check"][6:].strip("'\\\"")
        for r in historical["results"]
        if r["outcome"] == "survived" and r["file"] == "verify_bundle.py"
    }
    if historical_survivors != set(TESTS) or historical["commit"] != "af6018e199cd75519500526d60199bf702709511":
        raise RuntimeError("historical evidence no longer matches the 15 semantic targets")

    original_lines = (PILOT / "verify_bundle.py").read_text().splitlines()
    selected = {}
    for name, line, label, source in mutants():
        if name != "verify_bundle.py" or not label.startswith("check "):
            continue
        human_name = label[6:].strip("'\\\"")
        if human_name not in historical_survivors:
            continue
        if human_name == "verdict reproduces from the included observations":
            # At the old sweep's :195 the guard belonged to the exception path,
            # not the successful direct-comparison path with the same label.
            nearby = "\\n".join(original_lines[max(0, line - 3): line + 2])
            if "except PilotError" not in nearby:
                continue
        if human_name in selected:
            raise RuntimeError(f"duplicate semantic guard: {human_name}")
        selected[human_name] = (name, line, label, source)
    if set(selected) != set(TESTS):
        raise RuntimeError(f"expected 15 unique mutants; missing={set(TESTS) - set(selected)}; extra={set(selected) - set(TESTS)}")

    results = []
    with tempfile.TemporaryDirectory(prefix="proofrail-survivor-check-") as staging:
        base = make_copy(Path(staging) / "baseline")
        code, failed, errors, tail = pytest(base, "tests/test_verifier_check_isolation.py")
        if code != 0:
            raise RuntimeError(f"unmutated 15-test baseline failed: code={code}, failures={failed}, errors={errors}, tail={tail}")
        for i, (human_name, test_name) in enumerate(TESTS.items()):
            name, line, label, mutant = selected[human_name]
            compile(mutant, name, "exec")
            directory = Path(staging) / f"mutant-{i:02d}"
            copy = make_copy(directory, name, mutant)
            expected_node = f"tests/test_verifier_check_isolation.py::{test_name}"
            exit_code, failed, errors, tail = pytest(copy, "-x", expected_node)
            caught = (
                exit_code == 1 and not errors and
                any(f["test"] == expected_node for f in failed)
            )
            results.append({
                "check": human_name, "file": name, "line": line,
                "target_test": expected_node, "caught": caught,
                "exit_code": exit_code, "failures": failed, "errors": errors,
            })
            print(f"{'CAUGHT' if caught else 'NOT CAUGHT'} {name}:{line} {human_name}", flush=True)
            if not caught:
                print(f"Details: {tail}", file=sys.stderr)
    print(json.dumps({"total": len(results), "caught": sum(x["caught"] for x in results),
                      "not_caught": [x["check"] for x in results if not x["caught"]]}, sort_keys=True))
    return 0 if all(x["caught"] for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Exact per-guard mutation gate for five remaining portable-verifier checks.

Run from pilots/facility_outcomes:
    python review_tools/check_new_verifier_boundaries.py

Baseline tests must pass. Each run removes only the intended guard in a
temporary copy and confirms its named test fails. This does not assert that
all security properties or all integration mutants are covered.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
TARGET_FILE = "verify_bundle.py"
TEST_FILE = "tests/test_new_verifier_boundaries.py"

# Map the exact semantic rule, not its potentially repeated report text, to
# the test which must fail when that rule is removed.
CASES = (
    ("registered_gateway_role", "admission-time gateway identity is registered",
     "test_admission_gateway_must_have_registered_gateway_role", 1),
    ("consumption_binding", "unsigned registry-export snapshot reports one consumption by the named executor",
     "test_consumption_snapshot_has_exact_spent_executor_and_nonce", 1),
    ("unknown_gateway", "consumption_gateway_unknown",
     "test_unknown_historical_gateway_has_specific_refusal_reason", 1),
    ("mismatched_gateway_key", "consumption_gateway_key_mismatch",
     "test_gateway_receipt_mismatched_key_id_has_specific_refusal_reason", 1),
    ("unique_principals", "identity snapshot has unique principal IDs",
     "test_principal_ids_must_be_unique_in_each_snapshot", 2),
)


def location(text, node, *, end=False):
    """Convert AST byte-column offsets into Python string offsets."""
    lines = text.splitlines(keepends=True)
    row = node.end_lineno if end else node.lineno
    col = node.end_col_offset if end else node.col_offset
    return sum(len(line) for line in lines[:row - 1]) + len(lines[row - 1].encode()[:col].decode())


def candidates(source):
    result = {}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "check":
            if len(node.args) < 3:
                continue
            name = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
            label_source = ast.unparse(node.args[1])
            if name in {
                "admission-time gateway identity is registered",
                "unsigned registry-export snapshot reports one consumption by the named executor",
            }:
                key = "registered_gateway_role" if name.startswith("admission-") else "consumption_binding"
                start, stop = location(source, node.args[2]), location(source, node.args[2], end=True)
                result.setdefault(key, []).append((start, stop, "True"))
            if "identity snapshot has unique principal IDs" in label_source:
                start, stop = location(source, node.args[2]), location(source, node.args[2], end=True)
                result.setdefault("unique_principals", []).append((start, stop, "True"))
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            call = node.exc
            if not (isinstance(call.func, ast.Name) and call.func.id == "PilotError"
                    and call.args and isinstance(call.args[0], ast.Constant)):
                continue
            reason = call.args[0].value
            mapping = {"consumption_gateway_unknown": "unknown_gateway",
                       "consumption_gateway_key_mismatch": "mismatched_gateway_key"}
            if reason in mapping:
                result.setdefault(mapping[reason], []).append((
                    location(source, node), location(source, node, end=True), "pass"
                ))
    for key, targets in result.items():
        if len(targets) != 1:
            raise RuntimeError(f"ambiguous guard {key}: {len(targets)}")
    return result


def run_pytest(copy, node):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-rfE", "--tb=short", node],
        cwd=copy, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "300"},
    )
    return proc.returncode, proc.stdout + proc.stderr


def main():
    source = (PILOT / TARGET_FILE).read_text(encoding="utf-8")
    spans = candidates(source)
    names = {row[0] for row in CASES}
    if set(spans) != names:
        raise RuntimeError(f"expected five guards; missing={names - set(spans)}; extra={set(spans) - names}")

    with tempfile.TemporaryDirectory(prefix="proofrail-five-verifier-mutants-") as d:
        staging = Path(d)
        baseline = staging / "baseline"
        shutil.copytree(PILOT, baseline,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "review_tools"))
        rc, out = run_pytest(baseline, TEST_FILE)
        if rc != 0:
            raise RuntimeError(f"Unmutated baseline failed (exit {rc}): {out[-3000:]}")

        for key, reason, function, count in CASES:
            start, stop, replacement = spans[key][0]
            mutant = source[:start] + replacement + source[stop:]
            compile(mutant, TARGET_FILE, "exec")
            work = staging / key
            shutil.copytree(baseline, work)
            (work / TARGET_FILE).write_text(mutant, encoding="utf-8")
            node = f"{TEST_FILE}::{function}"
            exit_code, result = run_pytest(work, node)
            failed_lines = [line for line in result.splitlines()
                            if line.startswith("FAILED " + node)]
            if exit_code != 1 or len(failed_lines) != count or "ERROR " in result:
                raise RuntimeError(
                    f"Guard not demonstrably caught: {key}; rc={exit_code}; "
                    f"expected_failures={count}; actual_failures={len(failed_lines)}; "
                    f"out={result[-2600:]}"
                )
            print(f"CAUGHT {key}: {count} targeted test(s) fail after removal", flush=True)

    print(json.dumps({"guards_caught": len(CASES),
                      "targeted_tests_fail_on_mutant": sum(c[3] for c in CASES),
                      "unmodified_baseline": "passed",
                      "independent_review": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

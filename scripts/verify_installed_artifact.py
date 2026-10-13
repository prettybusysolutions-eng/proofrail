"""Verify the installed distribution, never importing from the checkout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def run(arguments: list[str], cwd: Path, expected: int = 0) -> str:
    result = subprocess.run(
        [sys.executable, "-I", "-m", "proofrail.cli", *arguments],
        cwd=cwd, text=True, capture_output=True, timeout=60,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"{arguments}: expected exit {expected}, got {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def verify(artifact: Path) -> dict:
    with TemporaryDirectory(prefix="proofrail-installed-") as directory:
        root = Path(directory)
        clean = root / "clean"
        shutil.copytree(artifact, clean)
        accepted = json.loads(run(["reproduce", str(clean)], root))
        if accepted.get("valid") is not True or not accepted.get("checks"):
            raise RuntimeError("Authentic artifact did not pass meaningful checks")
        if not all(check.get("passed") is True for check in accepted["checks"]):
            raise RuntimeError("Authentic artifact contains a failed check")
        damaged = root / "tampered"
        shutil.copytree(clean, damaged)
        with (damaged / "TRANSCRIPT.md").open("a", encoding="utf-8") as stream:
            stream.write("\ninstalled-package tamper probe\n")
        rejected = json.loads(run(["reproduce", str(damaged)], root, expected=4))
        if rejected.get("valid") is not False or not any(
            check.get("passed") is False for check in rejected.get("checks", [])
        ):
            raise RuntimeError("Tampered artifact did not produce a failed verification")
        demo = root / "demo"
        run(["demo", "github-merge-authority", "--out-dir", str(demo)], root)
        run(["ledger", "verify", str(demo / "proofrail-ledger.jsonl")], root)
        run(["ledger", "verify", str(demo / "tampered-ledger.jsonl")], root, expected=4)
        audit_source = artifact.parent / 'audit-review' / 'events.jsonl'
        events = root / 'audit-events.jsonl'
        shutil.copyfile(audit_source, events)
        original = events.read_bytes()
        review = json.loads(run(['audit-review', '--events', str(events), '--tenant', 'tenant-a'], root, expected=4))
        expected_codes = {'contradictory_execution', 'unresolved_execution', 'conflicting_success_claims'}
        if {f['code'] for f in review['findings']} != expected_codes:
            raise RuntimeError('Installed audit review did not identify the expected contradictions')
        if review['authenticity'] != 'NOT_CHECKED' or review['provider_effect_proven']:
            raise RuntimeError('Installed audit review overstated its verification boundary')
        run(['audit-review', '--events', str(events), '--tenant', 'tenant-a', '--output', str(events)], root, expected=2)
        if events.read_bytes() != original:
            raise RuntimeError('Audit review modified its input')
        records = [json.loads(line) for line in original.splitlines()]
        records[1]['metadata']['adapter_status'] = 'success'
        events.write_text(''.join(json.dumps(row) + '\n' for row in records))
        clean = json.loads(run(['audit-review', '--events', str(events), '--tenant', 'tenant-a'], root))
        if clean['status'] != 'NO_FINDINGS_IN_SUPPLIED_EVENTS':
            raise RuntimeError('Installed audit review rejected consistent claims')
        run(['audit-review', '--events', str(events), '--tenant', 'wrong-tenant'], root, expected=4)
    return {"valid": True, "checks": [
        "installed_artifact_accepted", "modified_artifact_rejected_exit_4",
        "offline_authority_demo", "valid_ledger_accepted", "tampered_ledger_rejected_exit_4",
        "installed_audit_findings", "audit_boundary_preserved", "audit_input_preserved",
        "consistent_audit_claims", "audit_tenant_mismatch",
    ], "boundary": "Offline installed-package verification; not production certification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact.resolve()), indent=2))

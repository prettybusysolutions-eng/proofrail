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
    return {"valid": True, "checks": [
        "installed_artifact_accepted", "modified_artifact_rejected_exit_4",
        "offline_authority_demo", "valid_ledger_accepted", "tampered_ledger_rejected_exit_4",
    ], "boundary": "Offline installed-package verification; not production certification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact.resolve()), indent=2))

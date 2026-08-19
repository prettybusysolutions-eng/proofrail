#!/usr/bin/env python3
"""Local replay entry point for governed xzenia-coder invariants."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_governed_coder_repository_change.py",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "status": "PASS" if completed.returncode == 0 else "FAILED",
        "suite": "governed_coder_repository_change",
        "returncode": completed.returncode,
        "stdout_sha256": __import__("hashlib").sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": __import__("hashlib").sha256(completed.stderr.encode()).hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

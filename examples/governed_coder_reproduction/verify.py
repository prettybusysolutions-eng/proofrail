#!/usr/bin/env python3
"""Offline verifier for the governed xzenia-coder reproduction bundle."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": ["python", *command[1:]],
        "returncode": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }


def main() -> int:
    commands = [
        [sys.executable, "-m", "pytest", "tests/test_governed_coder_repository_change.py", "-q"],
        [sys.executable, "adversarial/governed_coder_suite.py"],
    ]
    results = [run(command) for command in commands]
    status = "PASS" if all(item["returncode"] == 0 for item in results) else "FAILED"
    print(json.dumps({"status": status, "results": results}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

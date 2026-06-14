from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from proofrail.core import digest_ledger_entry


def result(
    *,
    attack_id: str,
    suite: str,
    threat: str,
    trust_assumption: str,
    attack: str,
    expected: str,
    actual: str,
    passed: bool,
    evidence: list[str],
    residual_risk: str,
) -> dict[str, Any]:
    return {
        "attack_id": attack_id,
        "suite": suite,
        "threat": threat,
        "trust_assumption": trust_assumption,
        "attack": attack,
        "expected": expected,
        "actual": actual,
        "verdict": "PASS" if passed else "FAIL",
        "evidence": evidence,
        "residual_risk": residual_risk,
    }


def captured_error(call: Callable[[], Any]) -> str | None:
    try:
        call()
    except Exception as exc:
        return str(exc)
    return None


def write_ledger(path: Path, count: int = 3) -> None:
    previous_hash = "GENESIS"
    records = []
    for sequence in range(1, count + 1):
        record = {
            "kind": "proofrail.validation-event.v0.5",
            "sequence": sequence,
            "recorded_at": f"2026-06-11T23:00:0{sequence}Z",
            "result": f"event-{sequence}",
            "previous_hash": previous_hash,
        }
        record["entry_hash"] = digest_ledger_entry(record)
        previous_hash = record["entry_hash"]
        records.append(record)
    path.write_text(
        "\n".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )

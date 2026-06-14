from __future__ import annotations

import json
from typing import Any


def to_ecs_event(audit: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    ledger = audit.get("ledger", {})
    status = audit.get("status", "unknown")
    return {
        "ecs.version": "8.11.0",
        "event.kind": "event",
        "event.category": ["configuration"],
        "event.type": ["access"],
        "event.outcome": "success" if status == "success" else "failure",
        "event.action": "proofrail_action",
        "event.id": audit.get("action_digest"),
        "organization.id": tenant_id,
        "user.id": audit.get("action_id"),
        "proofrail.status": status,
        "proofrail.ledger_valid": bool(ledger.get("valid")),
        "proofrail.ledger_entries": int(ledger.get("entries", 0)),
        "proofrail.ledger_errors": ledger.get("errors", []),
        "proofrail.result": audit.get("result"),
    }


def to_cef(audit: dict[str, Any], *, tenant_id: str) -> str:
    status = str(audit.get("status", "unknown"))
    severity = 3 if status == "success" else 8
    extension = {
        "externalId": audit.get("action_digest", ""),
        "act": "proofrail_action",
        "outcome": status,
        "tenant": tenant_id,
        "ledgerValid": str(bool(audit.get("ledger", {}).get("valid"))).lower(),
    }
    encoded = " ".join(f"{key}={_escape(str(value))}" for key, value in extension.items())
    return f"CEF:0|Xzenia|ProofRail|0.1|action|Governed AI action|{severity}|{encoded}"


def json_line(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("=", "\\=").replace("|", "\\|")

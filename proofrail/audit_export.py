from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .crypto import canonical_json

PERMIT_STATES = (
    "PROPOSED",
    "EVALUATED",
    "PERMITTED",
    "EXECUTING",
    "CONSUMED",
    "RECONCILED",
    "DENIED",
    "EXPIRED",
    "INVALIDATED",
    "EXECUTION_FAILED",
    "RECONCILIATION_FAILED",
)
TERMINAL_STATES = {
    "RECONCILED",
    "DENIED",
    "EXPIRED",
    "INVALIDATED",
    "EXECUTION_FAILED",
    "RECONCILIATION_FAILED",
}


def jsonl_audit_export(events: Iterable[Mapping[str, Any]]) -> str:
    """Return canonical JSON Lines suitable for archival or ingestion."""
    lines = [
        canonical_json(dict(event)).decode("utf-8")
        for event in events
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def ecs_security_events(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert ProofRail audit events to ECS-compatible security events."""
    return [_to_ecs(event) for event in events]


def reason_code_summary(
    events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    total = 0
    for event in events:
        total += 1
        outcomes[str(event.get("outcome", "unknown"))] += 1
        reason_codes = event.get("reason_codes", [])
        if isinstance(reason_codes, list):
            counts.update(
                code for code in reason_codes
                if isinstance(code, str) and code
            )
    return {
        "kind": "proofrail.reason-code-summary.v0.4",
        "event_count": total,
        "reason_codes": dict(sorted(counts.items())),
        "outcomes": dict(sorted(outcomes.items())),
    }


def permit_lifecycle_report(
    events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        permit_hash = event.get("permit_hash")
        if isinstance(permit_hash, str) and permit_hash:
            grouped[permit_hash].append(event)

    reports = []
    for permit_hash, permit_events in sorted(grouped.items()):
        ordered = sorted(
            permit_events,
            key=lambda event: (
                str(event.get("observed_at", "")),
                int(event.get("sequence", 0)),
            ),
        )
        states = [
            str(event["state"])
            for event in ordered
            if event.get("state") in PERMIT_STATES
        ]
        reports.append(
            {
                "permit_hash": permit_hash,
                "states": states,
                "terminal_state": next(
                    (state for state in reversed(states) if state in TERMINAL_STATES),
                    None,
                ),
                "first_observed_at": ordered[0].get("observed_at") if ordered else None,
                "last_observed_at": ordered[-1].get("observed_at") if ordered else None,
                "event_count": len(ordered),
                "replayed": any(
                    "permit_replayed" in event.get("reason_codes", [])
                    for event in ordered
                    if isinstance(event.get("reason_codes"), list)
                ),
            }
        )
    return {
        "kind": "proofrail.permit-lifecycle-report.v0.4",
        "permit_count": len(reports),
        "permits": reports,
    }


def _to_ecs(event: Mapping[str, Any]) -> dict[str, Any]:
    outcome = str(event.get("outcome", "unknown"))
    ecs_outcome = (
        "success"
        if outcome in {"success", "permitted", "reconciled"}
        else "failure"
        if outcome in {"failure", "denied", "invalidated"}
        else "unknown"
    )
    return {
        "@timestamp": event.get("observed_at"),
        "ecs.version": "8.11.0",
        "event.kind": "event",
        "event.category": ["configuration"],
        "event.type": ["access"],
        "event.action": event.get("action"),
        "event.outcome": ecs_outcome,
        "event.id": event.get("event_id"),
        "event.reason": ",".join(event.get("reason_codes", [])),
        "organization.id": event.get("tenant_id"),
        "user.id": event.get("principal_id"),
        "user.roles": [event.get("role")] if event.get("role") else [],
        "proofrail.object.type": event.get("object_type"),
        "proofrail.object.id": event.get("object_id"),
        "proofrail.permit_hash": event.get("permit_hash"),
        "proofrail.state": event.get("state"),
        "proofrail.outcome": outcome,
        "proofrail.metadata": event.get("metadata", {}),
    }

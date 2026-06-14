from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


class ProofRailError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ProofRailError(f"Invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ProofRailError("Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(document: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    return json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def digest_document(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def digest_ledger_entry(entry: dict[str, Any]) -> str:
    unhashed = {key: value for key, value in entry.items() if key != "entry_hash"}
    return hashlib.sha256(canonical_bytes(unhashed)).hexdigest()


def sign_document(document: dict[str, Any], secret: bytes, key_id: str) -> dict[str, Any]:
    if not secret:
        raise ProofRailError("Signing secret cannot be empty")
    signed = dict(document)
    signed["signature"] = {
        "algorithm": "hmac-sha256",
        "key_id": key_id,
        "value": hmac.new(secret, canonical_bytes(signed), hashlib.sha256).hexdigest(),
    }
    return signed


def verify_document(document: dict[str, Any], secret: bytes) -> bool:
    signature = document.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "hmac-sha256":
        return False
    expected = hmac.new(secret, canonical_bytes(document), hashlib.sha256).hexdigest()
    value = signature.get("value")
    return isinstance(value, str) and hmac.compare_digest(value, expected)


@dataclass(frozen=True)
class GateDecision:
    decision: str
    action_digest: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    approval_required: bool

    @property
    def allowed(self) -> bool:
        return self.decision == "permit"

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "action_digest": self.action_digest,
            "reasons": list(self.reasons),
            "evidence_ids": list(self.evidence_ids),
            "approval_required": self.approval_required,
        }


def evaluate_action(
    action: dict[str, Any],
    evidence: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    evidence_secret: bytes,
    approval: dict[str, Any] | None = None,
    approval_secret: bytes | None = None,
    now: datetime | None = None,
) -> GateDecision:
    now = now or utc_now()
    _require_fields(action, "action_id", "action_type", "target", "risk", "reversible", "claim_ids")
    if action["risk"] not in {"low", "medium", "high", "critical"}:
        raise ProofRailError(f"Unsupported risk: {action['risk']!r}")
    if not isinstance(action["claim_ids"], list) or not action["claim_ids"]:
        raise ProofRailError("Action must reference at least one claim")

    reasons: list[str] = []
    allowed_types = policy.get("allowed_action_types", [])
    if allowed_types and action["action_type"] not in allowed_types:
        reasons.append("action_type_not_allowed")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        _require_fields(item, "claim_id", "claim", "epistemic_status", "observed_at", "evidence")
        if not verify_document(item, evidence_secret):
            reasons.append(f"invalid_evidence_signature:{item.get('claim_id', 'unknown')}")
            continue
        evidence_by_id[item["claim_id"]] = item

    max_age = int(policy.get("max_evidence_age_seconds", 86400))
    require_observed = action["risk"] in set(policy.get("require_observed_for_risks", ["high", "critical"]))
    minimum_refs = int(policy.get("minimum_evidence_refs", {}).get(action["risk"], 1))
    accepted_ids: list[str] = []

    for claim_id in action["claim_ids"]:
        item = evidence_by_id.get(claim_id)
        if item is None:
            reasons.append(f"missing_signed_claim:{claim_id}")
            continue
        if require_observed and item["epistemic_status"] != "observed":
            reasons.append(f"claim_not_observed:{claim_id}")
        observed_at = parse_time(item["observed_at"])
        age = (now - observed_at).total_seconds()
        if age < -60:
            reasons.append(f"claim_from_future:{claim_id}")
        elif age > max_age:
            reasons.append(f"stale_claim:{claim_id}")
        expires_at = item.get("expires_at")
        if expires_at and now >= parse_time(expires_at):
            reasons.append(f"expired_claim:{claim_id}")
        refs = item["evidence"]
        if not isinstance(refs, list) or len(refs) < minimum_refs:
            reasons.append(f"insufficient_evidence_refs:{claim_id}")
        elif not all(isinstance(ref, dict) and ref.get("uri") for ref in refs):
            reasons.append(f"invalid_evidence_ref:{claim_id}")
        else:
            accepted_ids.append(claim_id)

    approval_required = action["risk"] in set(
        policy.get("approval_required_for_risks", ["medium", "high", "critical"])
    )
    action_digest = digest_document(action)
    if approval_required:
        if approval is None or approval_secret is None:
            reasons.append("approval_required")
        else:
            reasons.extend(_verify_approval(action_digest, approval, approval_secret, now))

    if action["risk"] == "critical" and action.get("reversible") is not True:
        reasons.append("irreversible_critical_action")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return GateDecision(
        decision="deny" if unique_reasons else "permit",
        action_digest=action_digest,
        reasons=unique_reasons,
        evidence_ids=tuple(dict.fromkeys(accepted_ids)),
        approval_required=approval_required,
    )


def approve_action(
    action: dict[str, Any],
    *,
    approved_by: str,
    scope: str,
    expires_at: str,
    secret: bytes,
    key_id: str,
) -> dict[str, Any]:
    approval = {
        "kind": "proofrail.approval.v1",
        "action_digest": digest_document(action),
        "approved_by": approved_by,
        "scope": scope,
        "approved_at": utc_now().isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at,
    }
    return sign_document(approval, secret, key_id)


def _verify_approval(
    action_digest: str,
    approval: dict[str, Any],
    secret: bytes,
    now: datetime,
) -> list[str]:
    reasons: list[str] = []
    if not verify_document(approval, secret):
        reasons.append("invalid_approval_signature")
    if approval.get("action_digest") != action_digest:
        reasons.append("approval_action_mismatch")
    try:
        if now >= parse_time(approval["expires_at"]):
            reasons.append("approval_expired")
    except (KeyError, ProofRailError):
        reasons.append("invalid_approval_expiry")
    if not approval.get("approved_by") or not approval.get("scope"):
        reasons.append("approval_identity_or_scope_missing")
    return reasons


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        action: dict[str, Any],
        decision: GateDecision,
        outcome: str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not decision.allowed:
            raise ProofRailError("Denied action cannot receive an execution receipt")
        if decision.action_digest != digest_document(action):
            raise ProofRailError("Decision is not bound to the supplied action")
        with self.path.open("a+", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            entries = [json.loads(line) for line in handle if line.strip()]
            previous_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
            entry = {
                "kind": "proofrail.receipt.v1",
                "sequence": len(entries) + 1,
                "recorded_at": utc_now().isoformat().replace("+00:00", "Z"),
                "actor": actor,
                "action_id": action["action_id"],
                "action_digest": decision.action_digest,
                "evidence_ids": list(decision.evidence_ids),
                "outcome": outcome,
                "details": details or {},
                "previous_hash": previous_hash,
            }
            entry["entry_hash"] = digest_ledger_entry(entry)
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return entry

    def verify(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"valid": True, "entries": 0, "errors": []}
        errors: list[str] = []
        previous_hash = "GENESIS"
        entries = 0
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                entries += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"line_{line_number}:invalid_json")
                    continue
                if entry.get("previous_hash") != previous_hash:
                    errors.append(f"line_{line_number}:broken_previous_hash")
                claimed_hash = entry.get("entry_hash")
                actual_hash = digest_ledger_entry(entry)
                if claimed_hash != actual_hash:
                    errors.append(f"line_{line_number}:invalid_entry_hash")
                previous_hash = claimed_hash or previous_hash
        return {"valid": not errors, "entries": entries, "errors": errors}


def atomic_write_json(path: str | Path, document: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _require_fields(document: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if field not in document]
    if missing:
        raise ProofRailError(f"Missing required fields: {', '.join(missing)}")

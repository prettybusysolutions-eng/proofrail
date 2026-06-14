from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit_export import (
    ecs_security_events,
    jsonl_audit_export,
    permit_lifecycle_report,
    reason_code_summary,
)
from .checkpoint import create_checkpoint, read_ledger, verify_ledger
from .control_plane import ControlPlane
from .core import ProofRailError, digest_ledger_entry, utc_now
from .crypto import hash_record
from .permit import PermitError, execute_github_merge, mint_permit
from .rbac import AuthorizationError, Principal
from .trust import (
    EMPTY_ROOT,
    create_trust_checkpoint,
    next_trust_checkpoint,
    read_trust_checkpoint,
    replay_registry_root,
    verify_trust_checkpoint,
    write_trust_checkpoint,
)

MAX_REQUEST_BYTES = 1_048_576


class ObjectNotFound(ProofRailError):
    pass


class PilotControlPlane:
    """Tenant-scoped pilot API over ProofRail authority primitives."""

    def __init__(
        self,
        *,
        database: str | Path,
        ledger_dir: str | Path,
        verifier_private_key: Ed25519PrivateKey,
        checkpoint_private_key: Ed25519PrivateKey,
        github_adapter: Any | None = None,
        verifier_key_id: str = "proofrail-verifier",
        checkpoint_key_id: str = "proofrail-checkpoint",
        require_observation_quorum: bool = True,
    ) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.control = ControlPlane(self.database)
        self.verifier_private_key = verifier_private_key
        self.verifier_public_key = verifier_private_key.public_key()
        self.checkpoint_private_key = checkpoint_private_key
        self.checkpoint_public_key = checkpoint_private_key.public_key()
        self.github_adapter = github_adapter
        self.verifier_key_id = verifier_key_id
        self.checkpoint_key_id = checkpoint_key_id
        self.require_observation_quorum = require_observation_quorum
        self._ledger_lock = threading.Lock()
        self._trust_lock = threading.Lock()
        self._initialize()
        self._ensure_trust_checkpoint()

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> tuple[int, Any, str]:
        try:
            return self._dispatch(
                method.upper(),
                path,
                headers=headers or {},
                body=dict(body or {}),
            )
        except AuthorizationError as exc:
            self._audit_request_failure(
                headers or {},
                method,
                path,
                body or {},
                reason_code="authorization_denied",
            )
            return 403, {"ok": False, "error": str(exc), "code": "forbidden"}, "application/json"
        except PermitError as exc:
            self._audit_request_failure(
                headers or {},
                method,
                path,
                body or {},
                reason_code=exc.code,
            )
            return 400, {"ok": False, "error": str(exc), "code": "invalid_request"}, "application/json"
        except ObjectNotFound as exc:
            return 404, {"ok": False, "error": str(exc), "code": "not_found"}, "application/json"
        except (ProofRailError, ValueError, TypeError) as exc:
            return 400, {"ok": False, "error": str(exc), "code": "invalid_request"}, "application/json"
        except Exception:
            return 500, {
                "ok": False,
                "error": "Internal control-plane failure",
                "code": "internal_error",
            }, "application/json"

    def _dispatch(
        self,
        method: str,
        raw_path: str,
        *,
        headers: Mapping[str, str],
        body: dict[str, Any],
    ) -> tuple[int, Any, str]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        principal = self._principal(headers)

        if method == "POST" and path == "/intents":
            return 201, self._create_intent(principal, body), "application/json"
        if method == "POST" and path == "/evidence":
            return 201, self._create_evidence(principal, body), "application/json"
        if method == "POST" and path == "/evaluate":
            return 200, self._evaluate(principal, body), "application/json"
        if method == "POST" and path == "/permits":
            return 201, self._mint_permit(principal, body), "application/json"
        if method == "POST" and path == "/execute/github-merge":
            return 200, self._execute_github_merge(principal, body), "application/json"
        if method == "POST" and path == "/reconcile/github-merge":
            return 200, self._reconcile_github_merge(principal, body), "application/json"
        if method == "GET" and path == "/ledger":
            return 200, self._get_ledger(principal), "application/json"
        if method == "GET" and path == "/checkpoint":
            return 200, self._get_checkpoint(principal, query), "application/json"
        if method == "GET" and path == "/audit/events":
            return self._get_audit_events(principal, query)
        raise ObjectNotFound(f"Unknown endpoint: {method} {path}")

    def _create_intent(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("intent:create")
        action_type = _required_text(body, "action_type")
        if action_type != "github_merge":
            raise ProofRailError("Pilot supports only github_merge intents")
        effect = body.get("effect")
        if not isinstance(effect, dict):
            raise ProofRailError("effect must be an object")
        _validate_github_effect(effect)
        intent_id = str(uuid.uuid4())
        record = {
            "kind": "proofrail.intent.v0.4",
            "intent_id": intent_id,
            "tenant_id": principal.tenant_id,
            "created_by": principal.principal_id,
            "created_at": _timestamp(),
            "action_type": action_type,
            "target": _required_text(body, "target"),
            "risk": body.get("risk", "high"),
            "effect": effect,
        }
        record["record_hash"] = hash_record(record)
        self._put_object(principal, "intent", intent_id, record)
        self._audit(
            principal,
            action="intent.create",
            outcome="success",
            object_type="intent",
            object_id=intent_id,
            metadata={"record_hash": record["record_hash"]},
            state="PROPOSED",
        )
        return record

    def _create_evidence(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("evidence:create")
        intent_id = _required_text(body, "intent_id")
        self._get_object(principal.tenant_id, "intent", intent_id)
        claims = body.get("claims")
        if not isinstance(claims, list) or not claims:
            raise ProofRailError("claims must be a non-empty list")
        evidence_id = str(uuid.uuid4())
        record = {
            "kind": "proofrail.evidence-envelope.v0.4",
            "evidence_id": evidence_id,
            "intent_id": intent_id,
            "tenant_id": principal.tenant_id,
            "created_by": principal.principal_id,
            "created_at": _timestamp(),
            "claims": claims,
        }
        record["record_hash"] = hash_record(record)
        self._put_object(principal, "evidence", evidence_id, record)
        self._audit(
            principal,
            action="evidence.create",
            outcome="success",
            object_type="evidence",
            object_id=evidence_id,
            metadata={"intent_id": intent_id, "record_hash": record["record_hash"]},
        )
        return record

    def _evaluate(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("evaluation:create")
        intent = self._get_object(
            principal.tenant_id,
            "intent",
            _required_text(body, "intent_id"),
        )
        evidence_ids = body.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ProofRailError("evidence_ids must be a non-empty list")
        evidence = [
            self._get_object(principal.tenant_id, "evidence", str(evidence_id))
            for evidence_id in evidence_ids
        ]
        reason_codes = []
        for item in evidence:
            if item.get("intent_id") != intent["intent_id"]:
                reason_codes.append("evidence_intent_mismatch")

        policy_name = _required_text(body, "policy_name")
        active_policy = self.control.get_active_policy(
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
            policy_name=policy_name,
        )
        roots = {
            "identity": self.control.identity_root(principal.tenant_id),
            "evidence": hash_record(
                {"evidence_hashes": sorted(item["record_hash"] for item in evidence)}
            ),
            "policy": active_policy.digest,
            "state": _required_digest(body, "state_root"),
        }
        approval_digest = _required_digest(body, "approval_digest")
        decision = "deny" if reason_codes else "permit"
        evaluation_id = str(uuid.uuid4())
        record = {
            "kind": "proofrail.evaluation.v0.4",
            "evaluation_id": evaluation_id,
            "intent_id": intent["intent_id"],
            "tenant_id": principal.tenant_id,
            "evaluated_by": principal.principal_id,
            "evaluated_at": _timestamp(),
            "decision": decision,
            "reason_codes": reason_codes or ["authority_requirements_satisfied"],
            "roots": roots,
            "approval_digest": approval_digest,
            "policy_name": policy_name,
            "policy_version": active_policy.version,
        }
        record["record_hash"] = hash_record(record)
        self._put_object(principal, "evaluation", evaluation_id, record)
        self._audit(
            principal,
            action="authority.evaluate",
            outcome="permitted" if decision == "permit" else "denied",
            object_type="evaluation",
            object_id=evaluation_id,
            reason_codes=record["reason_codes"],
            metadata={"intent_id": intent["intent_id"]},
            state="EVALUATED" if decision == "permit" else "DENIED",
        )
        return record

    def _mint_permit(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("permit:mint")
        evaluation = self._get_object(
            principal.tenant_id,
            "evaluation",
            _required_text(body, "evaluation_id"),
        )
        if evaluation.get("decision") != "permit":
            raise ProofRailError("Denied evaluation cannot mint a permit")
        intent = self._get_object(
            principal.tenant_id,
            "intent",
            evaluation["intent_id"],
        )
        effect = intent["effect"]
        expiry_seconds = int(body.get("expiry_seconds", 300))
        if not 1 <= expiry_seconds <= 3600:
            raise ProofRailError("expiry_seconds must be between 1 and 3600")
        now = utc_now()
        trust_checkpoint = read_trust_checkpoint(self._trust_checkpoint_path())
        trust_roots = trust_checkpoint["roots"]
        permit = mint_permit(
            identity_root=evaluation["roots"]["identity"],
            evidence_root=evaluation["roots"]["evidence"],
            policy_root=evaluation["roots"]["policy"],
            state_root=evaluation["roots"]["state"],
            approval_digest=evaluation["approval_digest"],
            repository=effect["repository"],
            pull_number=effect["pull_number"],
            expected_head_sha=effect["expected_head_sha"],
            merge_method=effect["merge_method"],
            nonce=str(body.get("nonce") or uuid.uuid4().hex),
            expires_at=now + timedelta(seconds=expiry_seconds),
            issuer_principal_id=principal.principal_id,
            issuer_role=principal.role,
            private_key=self.verifier_private_key,
            key_id=self.verifier_key_id,
            now=now,
            constraints={"evaluation_id": evaluation["evaluation_id"]},
            trust={
                "replay_root": trust_roots["replay"],
                "checkpoint_root": trust_checkpoint["record_hash"],
                "observation_root": trust_roots["observation"],
                "minimum_checkpoint_epoch": trust_checkpoint["epoch"],
                "monotonic_counter": trust_checkpoint["monotonic_counter"],
            },
        )
        self._put_object(principal, "permit", permit["permit_id"], permit)
        self._audit(
            principal,
            action="permit.mint",
            outcome="permitted",
            object_type="permit",
            object_id=permit["permit_id"],
            permit_hash=permit["record_hash"],
            state="PERMITTED",
            reason_codes=["single_use_permit_minted"],
            metadata={"evaluation_id": evaluation["evaluation_id"]},
        )
        return permit

    def _execute_github_merge(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("action:execute")
        if self.github_adapter is None:
            raise ProofRailError("GitHub adapter is not configured")
        permit = self._get_object(
            principal.tenant_id,
            "permit",
            _required_text(body, "permit_id"),
        )
        constraints = permit.get("constraints")
        if not isinstance(constraints, dict):
            raise ProofRailError("Permit constraints are missing")
        evaluation = self._get_object(
            principal.tenant_id,
            "evaluation",
            _required_text(constraints, "evaluation_id"),
        )
        active_policy = self.control.get_active_policy(
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
            policy_name=evaluation["policy_name"],
        )
        current_identity_root = self.control.identity_root(principal.tenant_id)
        with self._trust_lock:
            trust_checkpoint = read_trust_checkpoint(self._trust_checkpoint_path())
            result = execute_github_merge(
                permit,
                adapter=self.github_adapter,
                registry_path=self._permit_registry_path(),
                public_key=self.verifier_public_key,
                expected_identity_root=current_identity_root,
                expected_evidence_root=evaluation["roots"]["evidence"],
                expected_policy_root=active_policy.digest,
                expected_state_root=evaluation["roots"]["state"],
                expected_approval_digest=evaluation["approval_digest"],
                executor_id=principal.principal_id,
                trust_checkpoint=trust_checkpoint,
                checkpoint_public_key=self.checkpoint_public_key,
            )
            write_trust_checkpoint(
                self._trust_checkpoint_path(),
                next_trust_checkpoint(
                    trust_checkpoint,
                    registry_path=self._permit_registry_path(),
                    private_key=self.checkpoint_private_key,
                    key_id=self.checkpoint_key_id,
                ),
            )
        execution_id = str(uuid.uuid4())
        record = {
            "kind": "proofrail.execution.v0.4",
            "execution_id": execution_id,
            "permit_id": permit["permit_id"],
            "permit_hash": permit["record_hash"],
            "tenant_id": principal.tenant_id,
            "executed_by": principal.principal_id,
            "executed_at": _timestamp(),
            "state": "CONSUMED",
            "adapter_result": result["adapter_receipt"],
            "preliminary_state": result["authority_state"],
        }
        record["record_hash"] = hash_record(record)
        self._put_object(principal, "execution", execution_id, record)
        self._audit(
            principal,
            action="github_merge.execute",
            outcome="success"
            if result["adapter_receipt"].get("status") == "success"
            else "failure",
            object_type="execution",
            object_id=execution_id,
            permit_hash=permit["record_hash"],
            state="CONSUMED",
            reason_codes=[result["authority_state"].lower()],
            metadata={"adapter_status": result["adapter_receipt"].get("status")},
        )
        return record

    def _reconcile_github_merge(
        self,
        principal: Principal,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        principal.require("outcome:reconcile")
        execution = self._get_object(
            principal.tenant_id,
            "execution",
            _required_text(body, "execution_id"),
        )
        if self.github_adapter is None or not hasattr(self.github_adapter, "observe"):
            raise ProofRailError("GitHub observation adapter is not configured")
        permit = self._get_object(
            principal.tenant_id,
            "permit",
            execution["permit_id"],
        )
        effect = permit["effect"]
        owner, repo = effect["repository"].split("/", 1)
        observation = self.github_adapter.observe(
            {
                "action_type": "github_merge",
                "execution": {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": effect["pull_number"],
                    "expected_head_sha": effect["expected_head_sha"],
                    "merge_method": effect["merge_method"],
                },
            }
        )
        if self.require_observation_quorum and observation.get("quorum_met") is not True:
            observation = {
                **observation,
                "merged": False,
                "merge_commit_sha": None,
                "reason": "observation_quorum_not_met",
            }
        adapter_result = execution["adapter_result"]
        observed_merged = observation.get("merged") is True
        observed_merge_sha = observation.get("merge_commit_sha")
        claimed_sha = adapter_result.get("remote_operation_id")
        confirmed = (
            observed_merged
            and adapter_result.get("side_effect_confirmed") is True
            and isinstance(observed_merge_sha, str)
            and observed_merge_sha == claimed_sha
        )
        state = "RECONCILED" if confirmed else "RECONCILIATION_FAILED"
        reconciliation_id = str(uuid.uuid4())
        record = {
            "kind": "proofrail.reconciliation.v0.4",
            "reconciliation_id": reconciliation_id,
            "execution_id": execution["execution_id"],
            "permit_hash": execution["permit_hash"],
            "tenant_id": principal.tenant_id,
            "reconciled_by": principal.principal_id,
            "reconciled_at": _timestamp(),
            "state": state,
            "observed_merged": observed_merged,
            "observed_merge_sha": observed_merge_sha,
            "executor_claim_sha": claimed_sha,
            "provider_observation": observation,
        }
        record["record_hash"] = hash_record(record)
        self._put_object(principal, "reconciliation", reconciliation_id, record)
        self._audit(
            principal,
            action="github_merge.reconcile",
            outcome="reconciled" if confirmed else "failure",
            object_type="reconciliation",
            object_id=reconciliation_id,
            permit_hash=execution["permit_hash"],
            state=state,
            reason_codes=[
                "provider_outcome_confirmed"
                if confirmed
                else "provider_outcome_not_confirmed"
            ],
            metadata={"execution_id": execution["execution_id"]},
        )
        if observation.get("quorum_met") is True:
            with self._trust_lock:
                checkpoint = read_trust_checkpoint(self._trust_checkpoint_path())
                write_trust_checkpoint(
                    self._trust_checkpoint_path(),
                    next_trust_checkpoint(
                        checkpoint,
                        registry_path=self._permit_registry_path(),
                        private_key=self.checkpoint_private_key,
                        key_id=self.checkpoint_key_id,
                        observation_root=observation["observation_root"],
                    ),
                )
        return record

    def _get_ledger(self, principal: Principal) -> dict[str, Any]:
        principal.require("ledger:read")
        path = self._tenant_ledger(principal.tenant_id)
        return {
            "tenant_id": principal.tenant_id,
            "verification": verify_ledger(path),
            "events": read_ledger(path) if path.exists() else [],
        }

    def _get_checkpoint(
        self,
        principal: Principal,
        query: Mapping[str, list[str]],
    ) -> dict[str, Any]:
        principal.require("checkpoint:read")
        if query.get("scope", ["ledger"])[0] == "trust":
            checkpoint = read_trust_checkpoint(self._trust_checkpoint_path())
            return {
                "checkpoint": checkpoint,
                "verification": verify_trust_checkpoint(
                    checkpoint,
                    registry_path=self._permit_registry_path(),
                    public_key=self.checkpoint_public_key,
                ),
            }
        path = self._tenant_ledger(principal.tenant_id)
        if not path.exists():
            raise ObjectNotFound("Tenant ledger does not exist")
        return create_checkpoint(
            path,
            private_key=self.checkpoint_private_key,
            key_id=self.checkpoint_key_id,
        )

    def _get_audit_events(
        self,
        principal: Principal,
        query: Mapping[str, list[str]],
    ) -> tuple[int, Any, str]:
        principal.require("audit:read")
        events = self._audit_events(principal.tenant_id)
        export_format = query.get("format", ["json"])[0]
        if export_format == "json":
            return 200, {"events": events}, "application/json"
        principal.require("audit:export")
        if export_format == "jsonl":
            return 200, jsonl_audit_export(events), "application/x-ndjson"
        if export_format == "ecs":
            return 200, {"events": ecs_security_events(events)}, "application/json"
        if export_format == "reason-codes":
            return 200, reason_code_summary(events), "application/json"
        if export_format == "permit-lifecycle":
            return 200, permit_lifecycle_report(events), "application/json"
        raise ProofRailError(f"Unsupported audit format: {export_format}")

    def _principal(self, headers: Mapping[str, str]) -> Principal:
        normalized = {key.lower(): value for key, value in headers.items()}
        tenant_id = normalized.get("x-proofrail-tenant", "").strip()
        principal_id = normalized.get("x-proofrail-principal", "").strip()
        if not tenant_id or not principal_id:
            raise AuthorizationError(
                tenant_id=tenant_id or "missing",
                principal_id=principal_id or "missing",
                role=None,
                permission="authenticate",
            )
        return Principal(
            tenant_id=tenant_id,
            principal_id=principal_id,
            role=self.control.principal_role(tenant_id, principal_id) or "unknown",
        )

    def _put_object(
        self,
        principal: Principal,
        object_type: str,
        object_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pilot_objects(
                    tenant_id, object_type, object_id, created_by,
                    created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    principal.tenant_id,
                    object_type,
                    object_id,
                    principal.principal_id,
                    _timestamp(),
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )

    def _get_object(
        self,
        tenant_id: str,
        object_type: str,
        object_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM pilot_objects
                WHERE tenant_id = ? AND object_type = ? AND object_id = ?
                """,
                (tenant_id, object_type, object_id),
            ).fetchone()
        if row is None:
            raise ObjectNotFound(f"Unknown {object_type}: {object_id}")
        return json.loads(row[0])

    def _audit(
        self,
        principal: Principal,
        *,
        action: str,
        outcome: str,
        object_type: str,
        object_id: str,
        reason_codes: list[str] | None = None,
        permit_hash: str | None = None,
        state: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "kind": "proofrail.audit-event.v0.4",
            "event_id": str(uuid.uuid4()),
            "observed_at": _timestamp(),
            "tenant_id": principal.tenant_id,
            "principal_id": principal.principal_id,
            "role": principal.role,
            "action": action,
            "outcome": outcome,
            "reason_codes": reason_codes or [],
            "object_type": object_type,
            "object_id": object_id,
            "permit_hash": permit_hash,
            "state": state,
            "metadata": dict(metadata or {}),
        }
        with self._ledger_lock:
            path = self._tenant_ledger(principal.tenant_id)
            records = read_ledger(path) if path.exists() else []
            event["sequence"] = len(records) + 1
            event["previous_hash"] = (
                records[-1]["entry_hash"] if records else "GENESIS"
            )
            event["entry_hash"] = digest_ledger_entry(event)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pilot_audit_events(
                    tenant_id, event_id, sequence, observed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    principal.tenant_id,
                    event["event_id"],
                    event["sequence"],
                    event["observed_at"],
                    json.dumps(event, sort_keys=True, separators=(",", ":")),
                ),
            )
        return event

    def _audit_events(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM pilot_audit_events
                WHERE tenant_id = ? ORDER BY sequence
                """,
                (tenant_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _audit_request_failure(
        self,
        headers: Mapping[str, str],
        method: str,
        path: str,
        body: Mapping[str, Any],
        *,
        reason_code: str,
    ) -> None:
        normalized = {key.lower(): value for key, value in headers.items()}
        tenant_id = normalized.get("x-proofrail-tenant", "").strip()
        principal_id = normalized.get("x-proofrail-principal", "").strip()
        role = self.control.principal_role(tenant_id, principal_id)
        if not tenant_id or not principal_id or role is None:
            return
        permit_hash = None
        permit_id = body.get("permit_id")
        if isinstance(permit_id, str):
            try:
                permit = self._get_object(tenant_id, "permit", permit_id)
                permit_hash = permit.get("record_hash")
            except ObjectNotFound:
                pass
        try:
            self._audit(
                Principal(tenant_id, principal_id, role),
                action="request.denied",
                outcome="denied",
                object_type="endpoint",
                object_id=f"{method.upper()} {urlparse(path).path}",
                permit_hash=permit_hash,
                reason_codes=[reason_code],
                metadata={},
            )
        except Exception:
            return

    def _tenant_ledger(self, tenant_id: str) -> Path:
        safe = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in tenant_id
        )
        return self.ledger_dir / f"{safe}.jsonl"

    def _permit_registry_path(self) -> Path:
        return self.database.with_suffix(".permits.sqlite3")

    def _trust_checkpoint_path(self) -> Path:
        return self.database.with_suffix(".trust-checkpoint.json")

    def _ensure_trust_checkpoint(self) -> None:
        path = self._trust_checkpoint_path()
        if path.exists():
            return
        checkpoint = create_trust_checkpoint(
            replay_root=replay_registry_root(self._permit_registry_path()),
            ledger_checkpoint_root=EMPTY_ROOT,
            observation_root=EMPTY_ROOT,
            epoch=1,
            monotonic_counter=0,
            private_key=self.checkpoint_private_key,
            key_id=self.checkpoint_key_id,
        )
        write_trust_checkpoint(path, checkpoint)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pilot_objects (
                    tenant_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, object_type, object_id)
                );
                CREATE TABLE IF NOT EXISTS pilot_audit_events (
                    tenant_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, event_id),
                    UNIQUE(tenant_id, sequence)
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=30)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class ProofRailHTTPRequestHandler(BaseHTTPRequestHandler):
    application: PilotControlPlane

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        body: dict[str, Any] = {}
        if self.command == "POST":
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_REQUEST_BYTES:
                self.send_error(413)
                return
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._respond(
                    400,
                    {"ok": False, "error": "Invalid JSON", "code": "invalid_json"},
                    "application/json",
                )
                return
            if not isinstance(parsed, dict):
                self._respond(
                    400,
                    {"ok": False, "error": "Body must be an object", "code": "invalid_json"},
                    "application/json",
                )
                return
            body = parsed
        status, payload, content_type = self.application.request(
            self.command,
            self.path,
            headers=dict(self.headers.items()),
            body=body,
        )
        self._respond(status, payload, content_type)

    def _respond(self, status: int, payload: Any, content_type: str) -> None:
        if isinstance(payload, str):
            encoded = payload.encode("utf-8")
        else:
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def make_server(
    host: str,
    port: int,
    application: PilotControlPlane,
) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredProofRailHandler",
        (ProofRailHTTPRequestHandler,),
        {"application": application},
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m proofrail.server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--database", default="proofrail-pilot.sqlite3")
    parser.add_argument("--ledger-dir", default="proofrail-ledgers")
    args = parser.parse_args()

    verifier_key = Ed25519PrivateKey.from_private_bytes(
        _read_key_env("PROOFRAIL_VERIFIER_PRIVATE_KEY")
    )
    checkpoint_key = Ed25519PrivateKey.from_private_bytes(
        _read_key_env("PROOFRAIL_CHECKPOINT_PRIVATE_KEY")
    )
    github_adapter = None
    token = os.getenv("GITHUB_TOKEN")
    if token:
        try:
            from integrations.openclaw.github_adapter import (
                GitHubMergeAdapter,
                GitHubTransport,
            )

            github_adapter = GitHubMergeAdapter(GitHubTransport(token))
        except ImportError as exc:
            raise ProofRailError(
                "GitHub integration package is not installed"
            ) from exc
    application = PilotControlPlane(
        database=args.database,
        ledger_dir=args.ledger_dir,
        verifier_private_key=verifier_key,
        checkpoint_private_key=checkpoint_key,
        github_adapter=github_adapter,
    )
    server = make_server(args.host, args.port, application)
    print(f"ProofRail pilot listening on http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _required_text(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProofRailError(f"{field} is required")
    return value.strip()


def _required_digest(document: Mapping[str, Any], field: str) -> str:
    value = _required_text(document, field)
    if len(value) != 64:
        raise ProofRailError(f"{field} must be a 64-character hexadecimal digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProofRailError(f"{field} must be hexadecimal") from exc
    return value


def _validate_github_effect(effect: Mapping[str, Any]) -> None:
    repository = _required_text(effect, "repository")
    if repository.count("/") != 1:
        raise ProofRailError("repository must use owner/name form")
    pull_number = effect.get("pull_number")
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise ProofRailError("pull_number must be a positive integer")
    _required_text(effect, "expected_head_sha")
    if effect.get("merge_method") not in {"merge", "squash", "rebase"}:
        raise ProofRailError("merge_method must be merge, squash, or rebase")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_key_env(name: str) -> bytes:
    value = os.getenv(name)
    if not value:
        raise ProofRailError(f"Missing key environment variable: {name}")
    compact = value.strip()
    try:
        raw = (
            bytes.fromhex(compact)
            if len(compact) == 64
            else base64.urlsafe_b64decode(compact + "=" * (-len(compact) % 4))
        )
    except ValueError as exc:
        raise ProofRailError(f"Invalid Ed25519 key in {name}") from exc
    if len(raw) != 32:
        raise ProofRailError(f"Ed25519 key in {name} must decode to 32 bytes")
    return raw


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request

from proofrail.core import ProofRailError


class GitHubTransportProtocol(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        ...


@dataclass
class GitHubTransport:
    token: str
    api_base: str = "https://api.github.com"
    timeout_seconds: int = 30
    api_version: str = "2022-11-28"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        payload = json.dumps(body).encode() if body is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": self.api_version,
            "User-Agent": "ProofRail-GitHub-Adapter/0.1",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["X-ProofRail-Idempotency-Key"] = idempotency_key
        call = request.Request(
            f"{self.api_base.rstrip('/')}{path}",
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(call, timeout=self.timeout_seconds) as response:
                raw = response.read()
                return (
                    response.status,
                    dict(response.headers.items()),
                    json.loads(raw) if raw else {},
                )
        except error.HTTPError as exc:
            raw = exc.read()
            parsed = json.loads(raw) if raw else {"message": str(exc)}
            return exc.code, dict(exc.headers.items()), parsed


class GitHubMergeAdapter:
    """Merges an exact PR head and reconciles ambiguous network outcomes."""

    def __init__(self, transport: GitHubTransportProtocol):
        self.transport = transport

    def execute(self, action: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        execution = action.get("execution")
        if not isinstance(execution, dict):
            raise ProofRailError("GitHub merge action requires execution details")
        owner = _required_text(execution, "owner")
        repo = _required_text(execution, "repo")
        pull_number = execution.get("pull_number")
        expected_head_sha = _required_text(execution, "expected_head_sha")
        merge_method = execution.get("merge_method", "squash")
        if not isinstance(pull_number, int) or pull_number <= 0:
            raise ProofRailError("pull_number must be a positive integer")
        if merge_method not in {"merge", "squash", "rebase"}:
            raise ProofRailError("Unsupported GitHub merge method")

        path = f"/repos/{owner}/{repo}/pulls/{pull_number}"
        status, _, before = self.transport.request("GET", path)
        if status != 200:
            return self._receipt(
                idempotency_key=idempotency_key,
                status="failed",
                confirmed=False,
                retry_safe=status in {404},
                evidence={"phase": "preflight", "http_status": status, "response": before},
            )

        if before.get("merged") is True:
            merge_sha = before.get("merge_commit_sha")
            return self._receipt(
                idempotency_key=idempotency_key,
                status="success",
                confirmed=True,
                retry_safe=True,
                remote_operation_id=merge_sha,
                evidence={"phase": "preflight", "already_merged": True, "pull": _pull_evidence(before)},
            )

        actual_head_sha = ((before.get("head") or {}).get("sha"))
        if actual_head_sha != expected_head_sha:
            return self._receipt(
                idempotency_key=idempotency_key,
                status="failed",
                confirmed=False,
                retry_safe=False,
                evidence={
                    "phase": "preflight",
                    "reason": "head_sha_mismatch",
                    "expected_head_sha": expected_head_sha,
                    "actual_head_sha": actual_head_sha,
                },
            )
        if before.get("mergeable") is False:
            return self._receipt(
                idempotency_key=idempotency_key,
                status="failed",
                confirmed=False,
                retry_safe=False,
                evidence={"phase": "preflight", "reason": "pull_request_not_mergeable"},
            )

        merge_body = {
            "sha": expected_head_sha,
            "merge_method": merge_method,
        }
        if execution.get("commit_title"):
            merge_body["commit_title"] = execution["commit_title"]
        if execution.get("commit_message"):
            merge_body["commit_message"] = execution["commit_message"]

        try:
            merge_status, _, merged = self.transport.request(
                "PUT",
                f"{path}/merge",
                body=merge_body,
                idempotency_key=idempotency_key,
            )
        except (TimeoutError, socket.timeout, error.URLError, ConnectionError) as exc:
            return self._reconcile(
                path,
                idempotency_key,
                expected_head_sha,
                {"transport_error": type(exc).__name__, "message": str(exc)},
            )

        if merge_status == 200 and merged.get("merged") is True:
            return self._reconcile(
                path,
                idempotency_key,
                expected_head_sha,
                {
                    "merge_http_status": merge_status,
                    "executor_claim": "success",
                    "claimed_merge_sha": merged.get("sha"),
                    "response_sha256": _digest(merged),
                    "message": merged.get("message"),
                },
            )
        if merge_status in {409, 422, 502, 503, 504}:
            return self._reconcile(
                path,
                idempotency_key,
                expected_head_sha,
                {"merge_http_status": merge_status, "response": merged},
            )
        return self._receipt(
            idempotency_key=idempotency_key,
            status="failed",
            confirmed=False,
            retry_safe=merge_status in {401, 403, 404},
            evidence={"phase": "merge", "http_status": merge_status, "response": merged},
        )

    def observe(self, action: dict[str, Any]) -> dict[str, Any]:
        """Read GitHub state without trusting an executor or reconciler claim."""
        execution = action.get("execution")
        if not isinstance(execution, dict):
            raise ProofRailError("GitHub observation requires execution details")
        owner = _required_text(execution, "owner")
        repo = _required_text(execution, "repo")
        pull_number = execution.get("pull_number")
        if not isinstance(pull_number, int) or pull_number <= 0:
            raise ProofRailError("pull_number must be a positive integer")

        status, _, current = self.transport.request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pull_number}",
        )
        return {
            "provider": "github",
            "http_status": status,
            "merged": status == 200 and current.get("merged") is True,
            "merge_commit_sha": (
                current.get("merge_commit_sha") if status == 200 else None
            ),
            "pull": _pull_evidence(current) if status == 200 else current,
        }

    def _reconcile(
        self,
        path: str,
        idempotency_key: str,
        expected_head_sha: str,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            status, _, current = self.transport.request("GET", path)
        except (TimeoutError, socket.timeout, error.URLError, ConnectionError) as exc:
            return self._receipt(
                idempotency_key=idempotency_key,
                status="unknown",
                confirmed=False,
                retry_safe=False,
                evidence={
                    "phase": "reconciliation",
                    "trigger": trigger,
                    "reconciliation_error": type(exc).__name__,
                },
            )
        if status == 200 and current.get("merged") is True and current.get("merge_commit_sha"):
            return self._receipt(
                idempotency_key=idempotency_key,
                status="success",
                confirmed=True,
                retry_safe=True,
                remote_operation_id=current["merge_commit_sha"],
                evidence={
                    "phase": "reconciliation",
                    "trigger": trigger,
                    "expected_head_sha": expected_head_sha,
                    "pull": _pull_evidence(current),
                },
            )
        return self._receipt(
            idempotency_key=idempotency_key,
            status="unknown",
            confirmed=False,
            retry_safe=False,
            evidence={
                "phase": "reconciliation",
                "trigger": trigger,
                "http_status": status,
                "pull": _pull_evidence(current) if status == 200 else current,
            },
        )

    @staticmethod
    def _receipt(
        *,
        idempotency_key: str,
        status: str,
        confirmed: bool,
        retry_safe: bool,
        evidence: dict[str, Any],
        remote_operation_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": remote_operation_id,
            "status": status,
            "side_effect_confirmed": confirmed,
            "retry_safe": retry_safe,
            "receipt_evidence": evidence,
        }


def _required_text(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProofRailError(f"{field} is required")
    return value.strip()


def _digest(document: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _pull_evidence(pull: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pull.get("number"),
        "state": pull.get("state"),
        "merged": pull.get("merged"),
        "merge_commit_sha": pull.get("merge_commit_sha"),
        "head_sha": ((pull.get("head") or {}).get("sha")),
        "base_sha": ((pull.get("base") or {}).get("sha")),
        "html_url": pull.get("html_url"),
    }

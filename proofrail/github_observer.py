"""Read-only GitHub provider observer for the draft ProofRail Reliance Gate.

Only GET /repos/{owner}/{repo}/pulls/{number} is permitted. It signs a
normalized observation after checking a buyer-pinned authorization and
GitHub's returned repository, PR number, head, merge status and merge time.
An observation records what GitHub API reported; it is not an independent
witness or an execution blocker. No GET response is enough to check merge
method, opaque policy constraints, or the completeness of a GitHub audit log.
"""
from __future__ import annotations

import http.client
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .core import ProofRailError
from .crypto import sign_record, verify_signature
from .reliance import AUTH_FIELDS, AUTH_KIND, OBS_KIND, _has_unknown_fields, _time


_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_SEGMENT = re.compile(r"[a-zA-Z0-9_.-]+\Z")
_EFFECT_FIELDS = frozenset((
    "action_type", "repository", "pull_number", "expected_head_sha",
    "expected_base_ref",
))
_MAX_RESPONSE_BYTES = 262144


class ReadOnlyPullTransport(Protocol):
    def get_pull(self, repository: str, number: int) -> Mapping[str, Any]:
        ...


class GitHubReadOnlyPullTransport:
    """Hard-coded GitHub API origin; no redirects, mutation methods or body.

    Token is passed directly by the operator (prefer a fine-grained read-only
    GitHub App or PAT). It is never included in exceptions or signed output.
    """
    def __init__(self, token: str, *, timeout: float = 10.0):
        if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
            raise ValueError("nonempty GitHub token required")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("timeout must be >0 and <=60 seconds")
        self._token = token
        self._timeout = float(timeout)

    def get_pull(self, repository: str, number: int) -> Mapping[str, Any]:
        repo = _repository(repository)
        if type(number) is not int or number <= 0:
            raise ValueError("positive PR number required")
        path = f"/repos/{repo}/pulls/{number}"
        conn = http.client.HTTPSConnection("api.github.com", timeout=self._timeout)
        try:
            conn.request("GET", path, headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "ProofRail-ReadOnly-Observer/0",
                "X-GitHub-Api-Version": "2026-03-10",
            })
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"GitHub pull request GET returned HTTP {response.status}")
            data = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(data) > _MAX_RESPONSE_BYTES:
                raise ValueError("GitHub pull request response exceeded size limit")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("GitHub response must be a JSON object")
            return result
        finally:
            conn.close()


def _repository(value: Any) -> str:
    if not isinstance(value, str) or value.count("/") != 1:
        raise ValueError("repository must be owner/repo")
    owner, repo = value.split("/")
    if not all(_SEGMENT.fullmatch(part) and part not in (".", "..") for part in (owner, repo)):
        raise ValueError("invalid repository components")
    return value


def _utc_now(value: datetime | None) -> datetime:
    current = datetime.now(timezone.utc) if value is None else value
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("observer requires timezone-aware current time")
    return current.astimezone(timezone.utc)


def _result(reason: str, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "recorded": observation is not None,
        "reason": reason,
        "observation": observation,
    }


def observe_github_merge(
    authorization: Mapping[str, Any],
    *,
    authority_key: Ed25519PublicKey | bytes,
    authority_principal: str,
    authority_key_id: str,
    expected_effect: Mapping[str, Any],
    observer_key: Ed25519PrivateKey | bytes,
    observer_principal: str,
    observer_key_id: str,
    transport: ReadOnlyPullTransport,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a signed normalized provider claim, or an unsigned refusal.

    A signed 'failed' means the GitHub response did not match the claimed
    authorized effect, *not* that GitHub itself failed to merge something.
    Consumer must separately verify via assess_reliance() with trusted keys
    and use an atomic acceptance ledger for single-use reliance.
    """
    if not isinstance(authorization, Mapping) or not isinstance(expected_effect, Mapping):
        return _result("invalid_authorization_or_effect")
    if authorization.get("kind") != AUTH_KIND or _has_unknown_fields(authorization, AUTH_FIELDS):
        return _result("unrecognized_authorization")
    if authorization.get("decision") != "allow":
        return _result("authorization_not_allowed")
    if not isinstance(authority_principal, str) or not authority_principal or not isinstance(authority_key_id, str) or not authority_key_id:
        return _result("invalid_authority_context")
    if not isinstance(observer_principal, str) or not observer_principal or not isinstance(observer_key_id, str) or not observer_key_id:
        return _result("invalid_observer_context")
    if authority_principal == observer_principal:
        return _result("separate_signers_required")
    signer = authorization.get("signer")
    signature = authorization.get("signature")
    if not isinstance(signer, Mapping) or signer.get("principal_id") != authority_principal:
        return _result("wrong_authority_principal")
    if not isinstance(signature, Mapping) or signature.get("key_id") != authority_key_id:
        return _result("wrong_authority_key_id")
    try:
        verify_signature(authorization, authority_key)
    except (ProofRailError, TypeError, ValueError):
        return _result("invalid_authority_signature")
    effect = authorization.get("effect")
    if (
        not isinstance(effect, Mapping)
        or set(effect) != _EFFECT_FIELDS
        or dict(effect) != dict(expected_effect)
        or effect.get("action_type") != "github_merge"
    ):
        # Opaque fields such as request_digest and merge_method cannot be
        # checked by the GET pull-request API and are rejected, not ignored.
        return _result("unsupported_or_mismatched_effect")
    try:
        repository = _repository(effect["repository"])
        number = effect["pull_number"]
        head = effect["expected_head_sha"]
        base_ref = effect["expected_base_ref"]
        if type(number) is not int or number <= 0 or not isinstance(head, str) or not _SHA.fullmatch(head):
            raise ValueError("invalid PR identifier or expected SHA")
        if not isinstance(base_ref, str) or not base_ref or len(base_ref) > 240 or any(c in base_ref for c in "\\r\\n"):
            raise ValueError("invalid expected base branch")
        observed = _utc_now(now)
        issued = _time(authorization.get("issued_at"))
        expires = _time(authorization.get("expires_at"))
        if issued > observed or expires <= observed or expires <= issued:
            return _result("authorization_not_current")
    except (ValueError, TypeError, OverflowError):
        return _result("invalid_authorization_parameters")

    try:
        pull = transport.get_pull(repository, number)
    except (OSError, ValueError, TypeError, TimeoutError, ConnectionError, json.JSONDecodeError):
        return _result("github_observation_unavailable")
    if not isinstance(pull, Mapping):
        return _result("malformed_github_response")
    base = pull.get("base")
    base_repo = base.get("repo") if isinstance(base, Mapping) else None
    returned_name = base_repo.get("full_name") if isinstance(base_repo, Mapping) else None
    if not isinstance(returned_name, str) or returned_name.casefold() != repository.casefold():
        return _result("unexpected_repository_or_rename")
    if type(pull.get("number")) is not int or pull["number"] != number:
        return _result("unexpected_pr_number")
    if base.get("ref") != base_ref:
        return _result("unexpected_base_branch")
    github_head = pull.get("head")
    actual_head = github_head.get("sha") if isinstance(github_head, Mapping) else None
    if not isinstance(actual_head, str) or not _SHA.fullmatch(actual_head):
        return _result("missing_github_head_sha")
    merged = pull.get("merged")
    if type(merged) is not bool or pull.get("state") not in ("open", "closed"):
        return _result("malformed_github_merge_state")

    outcome = "unknown"
    event_id = f"github:{repository.lower()}#{number}:unmerged"
    if merged is True:
        merged_at_text = pull.get("merged_at")
        merge_sha = pull.get("merge_commit_sha")
        if pull.get("state") != "closed" or not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha):
            return _result("missing_confirmed_merge_identifiers")
        try:
            merged_at = _time(merged_at_text)
        except (ValueError, TypeError, OverflowError):
            return _result("invalid_merge_timestamp")
        if merged_at > observed:
            return _result("merge_timestamp_in_future")
        event_id = f"github:{repository.lower()}#{number}:{merge_sha.lower()}"
        # A genuine merge at the wrong head or before authorization happened
        # is NOT a valid application of this signed authorization.
        outcome = "applied" if actual_head.lower() == head.lower() and merged_at >= issued else "failed"
    elif pull["state"] == "closed":
        outcome = "failed"

    record = {
        "kind": OBS_KIND,
        "authorization_hash": authorization["record_hash"],
        "observed_at": observed.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "signer": {"principal_id": observer_principal},
        "provider": "github",
        "provider_event_id": event_id,
        "effect": dict(expected_effect),
        "outcome": outcome,
    }
    try:
        signed = sign_record(record, observer_key, key_id=observer_key_id)
    except (ProofRailError, TypeError, ValueError):
        return _result("observer_signing_unavailable")
    return _result("signed_github_observation", signed)

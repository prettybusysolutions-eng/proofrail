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
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .core import ProofRailError
from .crypto import sign_record, verify_signature
from .reliance import AUTH_FIELDS, AUTH_KIND, OBS_KIND, _has_unknown_fields, _time


_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_SEGMENT = re.compile(r"[a-zA-Z0-9_.-]+\Z")
_REQUIRED_EFFECT_FIELDS = frozenset((
    "action_type", "repository", "repository_id", "pull_number",
    "expected_head_sha", "expected_base_ref",
))
_EFFECT_FIELDS = _REQUIRED_EFFECT_FIELDS | {"pre_merge_anchor"}
_ANCHOR_FIELDS = frozenset(("type", "context", "creator_id"))
_MAX_RESPONSE_BYTES = 262144
_MAX_STATUS_PAGES = 10
# Fixed tolerance for issuer clock ahead of GitHub's status timestamp.
# Do not make this buyer-selected; it weakens chronological assurance.
_MAX_ANCHOR_CLOCK_SKEW = timedelta(seconds=5)
_SUPPORTED_API_VERSIONS = frozenset(("2022-11-28", "2026-03-10"))


class ReadOnlyPullTransport(Protocol):
    def get_pull(self, repository: str, number: int) -> Mapping[str, Any]:
        ...

    def get_statuses(self, repository: str, sha: str, page: int) -> list[Mapping[str, Any]]:
        ...


class GitHubReadOnlyPullTransport:
    """Hard-coded GitHub API origin; no redirects, mutation methods or body.

    Token is passed directly by the operator (prefer a fine-grained read-only
    GitHub App or PAT). It is never included in exceptions or signed output.
    """
    def __init__(self, token: str, *, timeout: float = 10.0, api_version: str = "2022-11-28"):
        if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
            raise ValueError("nonempty GitHub token required")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("timeout must be >0 and <=60 seconds")
        if api_version not in _SUPPORTED_API_VERSIONS:
            raise ValueError("unsupported GitHub REST API version")
        self._token = token
        self._timeout = float(timeout)
        self._api_version = api_version

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
                "X-GitHub-Api-Version": self._api_version,
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

    def get_statuses(self, repository: str, sha: str, page: int) -> list[Mapping[str, Any]]:
        repo = _repository(repository)
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ValueError("invalid commit SHA")
        if type(page) is not int or not 1 <= page <= _MAX_STATUS_PAGES:
            raise ValueError("status page outside bounded range")
        path = f"/repos/{repo}/commits/{sha}/statuses?per_page=100&page={page}"
        conn = http.client.HTTPSConnection("api.github.com", timeout=self._timeout)
        try:
            conn.request("GET", path, headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "ProofRail-ReadOnly-Observer/0",
                "X-GitHub-Api-Version": self._api_version,
            })
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"GitHub status GET returned HTTP {response.status}")
            data = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(data) > _MAX_RESPONSE_BYTES:
                raise ValueError("GitHub statuses response exceeded size limit")
            value = json.loads(data)
            if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
                raise ValueError("GitHub statuses must be a JSON array of objects")
            return value
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


def _anchor_result(
    transport: ReadOnlyPullTransport,
    repository: str,
    head: str,
    merged_at: datetime,
    issued: datetime,
    authorization_hash: str,
    anchor: Mapping[str, Any],
) -> str:
    """Return 'verified', 'failed' or 'unavailable'; never assume page completeness.

    The newest same-context status recorded before merge must be a matching
    success from the buyer-pinned creator, carrying the precise authorization
    hash. Allow at most five seconds of bounded issuer-clock lead over
    GitHub's status created_at, but still require a status strictly before
    the merge. Ambiguous second-resolution chronology fails closed.
    """
    candidates: list[tuple[datetime, Mapping[str, Any]]] = []
    # Use the exact signed status context; case folding could accept a
    # different context than the repository's native required status.
    context = anchor["context"]
    try:
        for page in range(1, _MAX_STATUS_PAGES + 1):
            statuses = transport.get_statuses(repository, head, page)
            if not isinstance(statuses, list) or len(statuses) > 100:
                return "unavailable"
            for status in statuses:
                if not isinstance(status, Mapping):
                    return "unavailable"
                supplied_context = status.get("context")
                if not isinstance(supplied_context, str):
                    return "unavailable"
                if supplied_context != context:
                    continue
                timestamp = _time(status.get("created_at"))
                # GitHub exposes status times only to the second. An anchor
                # posted at the same second as the merge cannot prove order.
                if timestamp == merged_at:
                    return "failed"
                if timestamp < merged_at:
                    candidates.append((timestamp, status))
            if len(statuses) < 100:
                break
        else:
            return "unavailable"
    except (OSError, ValueError, TypeError, TimeoutError, ConnectionError,
            json.JSONDecodeError, AttributeError):
        return "unavailable"
    if not candidates:
        return "failed"
    latest_time = max(t for t, _ in candidates)
    latest = [status for t, status in candidates if t == latest_time]
    if len(latest) != 1 or latest_time < issued - _MAX_ANCHOR_CLOCK_SKEW:
        return "failed"
    status = latest[0]
    creator = status.get("creator")
    if not isinstance(creator, Mapping) or type(creator.get("id")) is not int:
        return "failed"
    expected_description = "proofrail-auth-sha256:" + authorization_hash
    if (status.get("state") != "success"
            or status.get("description") != expected_description
            or creator["id"] != anchor["creator_id"]):
        return "failed"
    return "verified"


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
        or not _REQUIRED_EFFECT_FIELDS <= set(effect) <= _EFFECT_FIELDS
        or dict(effect) != dict(expected_effect)
        or effect.get("action_type") != "github_merge"
    ):
        # Opaque fields such as request_digest and merge_method cannot be
        # checked by the GET pull-request API and are rejected, not ignored.
        return _result("unsupported_or_mismatched_effect")
    try:
        repository = _repository(effect["repository"])
        number = effect["pull_number"]
        repository_id = effect["repository_id"]
        head = effect["expected_head_sha"]
        base_ref = effect["expected_base_ref"]
        if type(repository_id) is not int or repository_id <= 0:
            raise ValueError("invalid repository ID")
        if type(number) is not int or number <= 0 or not isinstance(head, str) or not _SHA.fullmatch(head):
            raise ValueError("invalid PR identifier or expected SHA")
        if not isinstance(base_ref, str) or not base_ref or len(base_ref) > 240 or any(ord(c) < 32 for c in base_ref):
            raise ValueError("invalid expected base branch")
        anchor = effect.get("pre_merge_anchor")
        if anchor is not None and (
            not isinstance(anchor, Mapping)
            or set(anchor) != _ANCHOR_FIELDS
            or anchor.get("type") != "github_commit_status"
            or not isinstance(anchor.get("context"), str)
            or not 0 < len(anchor["context"]) <= 100
            or any(ord(c) < 33 or ord(c) > 126 for c in anchor["context"])
            or type(anchor.get("creator_id")) is not int
            or anchor["creator_id"] <= 0
        ):
            return _result("unsupported_pre_merge_anchor")
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
    if type(base_repo.get("id")) is not int or base_repo["id"] != repository_id:
        return _result("unexpected_repository_id")
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
    event_id = f"github:repo:{repository_id}:pr:{number}:unmerged"
    if merged is True:
        merged_at_text = pull.get("merged_at")
        merge_sha = pull.get("merge_commit_sha")
        if pull.get("state") != "closed" or (merge_sha is not None and (
            not isinstance(merge_sha, str) or not _SHA.fullmatch(merge_sha)
        )):
            return _result("missing_confirmed_merge_identifiers")
        try:
            merged_at = _time(merged_at_text)
        except (ValueError, TypeError, OverflowError):
            return _result("invalid_merge_timestamp")
        if merged_at > observed:
            return _result("merge_timestamp_in_future")
        event_id = f"github:repo:{repository_id}:pr:{number}:merged"
        # A real merge at the wrong head or before the signed grant is not
        # proof of use of this particular authorization.
        outcome = "applied" if actual_head.lower() == head.lower() and merged_at >= issued else "failed"
        if outcome == "applied" and anchor is not None:
            anchor_result = _anchor_result(
                transport, repository, head, merged_at, issued,
                authorization["record_hash"], anchor,
            )
            if anchor_result == "unavailable":
                return _result("github_anchor_observation_unavailable")
            if anchor_result != "verified":
                outcome = "failed"
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

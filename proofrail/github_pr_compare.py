"""Buyer-operated, read-only comparison of expected PR facts with GitHub.

No permits, signatures, GitHub writes, or historical approval assertions.
Results only attest to what GitHub's API returned during this local check.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_COLUMNS = ("pull_number", "expected_head_sha", "expected_base_ref")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}\Z")
_MAX_ROWS = 100
_MAX_INPUT_BYTES = 256_000
_MAX_RESPONSE_BYTES = 256_000


class ComparisonInputError(ValueError):
    """Bad input, not a failed provider comparison."""


class ProviderUnavailable(Exception):
    """Provider data is unavailable or not safely interpretable."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: a bearer token must never leave api.github.com."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_expectations(path: str | Path) -> list[dict[str, Any]]:
    """Accept only a small, exact-schema CSV; reject ambiguous rows."""
    raw = Path(path).read_bytes()
    if len(raw) > _MAX_INPUT_BYTES:
        raise ComparisonInputError("CSV exceeds 256000 bytes")
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ComparisonInputError("CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(data, newline=""))
    if reader.fieldnames is None or set(reader.fieldnames) != set(_COLUMNS) or len(reader.fieldnames) != len(_COLUMNS):
        raise ComparisonInputError("CSV headers must be pull_number,expected_head_sha,expected_base_ref")
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in reader:
        if len(rows) >= _MAX_ROWS:
            raise ComparisonInputError("CSV exceeds 100 PRs")
        if None in row or any(not isinstance(row.get(k), str) for k in _COLUMNS):
            raise ComparisonInputError("Malformed CSV record")
        number_text = row["pull_number"]
        sha = row["expected_head_sha"]
        base = row["expected_base_ref"]
        if not number_text.isascii() or not number_text.isdecimal() or number_text.startswith("0"):
            raise ComparisonInputError("PR number must be a positive decimal integer")
        number = int(number_text)
        if number < 1 or number > 2_147_483_647 or number in seen:
            raise ComparisonInputError("Invalid or duplicate PR number")
        if not _SHA.fullmatch(sha):
            raise ComparisonInputError("expected_head_sha must be a 40-digit hexadecimal SHA")
        if not base or len(base) > 240 or any(ord(ch) < 33 or ord(ch) == 127 for ch in base):
            raise ComparisonInputError("Invalid expected_base_ref")
        seen.add(number)
        rows.append({"pull_number": number, "expected_head_sha": sha.lower(), "expected_base_ref": base})
    if not rows:
        raise ComparisonInputError("CSV must have at least one PR row")
    return rows


def _repository(value: str) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise ComparisonInputError("repository must be owner/name")
    owner, name = value.split("/", 1)
    if name in (".", "..") or name.endswith(".") or ".." in name:
        raise ComparisonInputError("invalid repository name")
    return value


def get_pull(repository: str, number: int, *, token: str = "", opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One GET to GitHub per PR; never sends local expectations to the API."""
    repository = _repository(repository)
    url = f"https://api.github.com/repos/{repository}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ProofRail-Buyer-PR-Comparison/0.1",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        # urllib's default opener follows redirects. Use a strict opener so
        # even a compromised/misconfigured API response cannot redirect tokens.
        fn = opener or urllib.request.build_opener(_NoRedirect()).open
        with fn(req, timeout=15) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ProviderUnavailable("provider response too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ProviderUnavailable("malformed provider response")
        return data
    except urllib.error.HTTPError as exc:
        raise ProviderUnavailable(f"GitHub HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProviderUnavailable(f"GitHub read unavailable ({type(exc).__name__})") from None


def _iso_time(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProviderUnavailable("missing or invalid GitHub merge time")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderUnavailable("missing or invalid GitHub merge time") from None
    if dt.utcoffset() is None:
        raise ProviderUnavailable("missing or invalid GitHub merge time")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def compare_prs(
    repository: str,
    rows: list[dict[str, Any]],
    *,
    repository_id: int | None = None,
    fetch: Callable[[str, int], dict[str, Any]],
) -> dict[str, Any]:
    """Compare exact buyer-declared expectations against current GitHub REST data."""
    repository = _repository(repository)
    if repository_id is not None and (type(repository_id) is not int or repository_id <= 0):
        raise ComparisonInputError("repository_id must be a positive integer")
    results: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {
            **row, "comparison": "unavailable", "differences": [],
            "authorization_proven": False,
        }
        try:
            pull = fetch(repository, row["pull_number"])
            if not isinstance(pull, dict):
                raise ProviderUnavailable("malformed provider response")
            base = pull.get("base")
            head = pull.get("head")
            base_repo = base.get("repo") if isinstance(base, dict) else None
            name = base_repo.get("full_name") if isinstance(base_repo, dict) else None
            repo_id = base_repo.get("id") if isinstance(base_repo, dict) else None
            number = pull.get("number")
            sha = head.get("sha") if isinstance(head, dict) else None
            branch = base.get("ref") if isinstance(base, dict) else None
            merged = pull.get("merged")
            state = pull.get("state")
            if (not isinstance(name, str) or type(repo_id) is not int or repo_id <= 0
                    or type(number) is not int or number <= 0
                    or not isinstance(sha, str) or not _SHA.fullmatch(sha)
                    or not isinstance(branch, str) or not branch
                    or type(merged) is not bool or state not in ("open", "closed")):
                raise ProviderUnavailable("incomplete or malformed GitHub PR data")
            merged_at = _iso_time(pull.get("merged_at")) if merged else None
            if (merged and state != "closed") or (not merged and pull.get("merged_at") is not None):
                raise ProviderUnavailable("contradictory GitHub PR merge state")
            if merged_at is not None:
                if datetime.fromisoformat(merged_at.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                    raise ProviderUnavailable("GitHub merge time is in the future")
            entry["github"] = {
                "repository": name,
                "repository_id": repo_id,
                "pull_number": number,
                "head_sha": sha.lower(),
                "base_ref": branch,
                "merged": merged,
                "merged_at": merged_at,
            }
            differences = []
            if name.casefold() != repository.casefold():
                differences.append("repository_name_mismatch")
            if repository_id is not None and repo_id != repository_id:
                differences.append("repository_id_mismatch")
            if number != row["pull_number"]:
                differences.append("pr_number_mismatch")
            if sha.lower() != row["expected_head_sha"]:
                differences.append("head_sha_mismatch")
            if branch != row["expected_base_ref"]:
                differences.append("base_ref_mismatch")
            if not merged:
                differences.append("not_merged")
            entry["differences"] = differences
            entry["comparison"] = "match" if not differences else "mismatch"
        except ProviderUnavailable as exc:
            entry["error"] = str(exc)
        results.append(entry)
    summary = {
        "total": len(results),
        "match": sum(x["comparison"] == "match" for x in results),
        "mismatch": sum(x["comparison"] == "mismatch" for x in results),
        "unavailable": sum(x["comparison"] == "unavailable" for x in results),
    }
    return {
        "kind": "proofrail.github_pr_fact_comparison.v1",
        "repository": repository,
        "pinned_repository_id": repository_id,
        "source": "GitHub REST API GET /pulls/{number}; unsigned provider response",
        "expected_values_source": "buyer-supplied CSV; not authenticated by ProofRail",
        "authorization_proven": False,
        "no_github_writes": True,
        "summary": summary,
        "results": results,
        "limitations": [
            "Matching expected PR metadata does not prove that approval was issued, authentic, timely or enforced.",
            "GitHub API response and merge timestamps are not independently attested.",
            "A present PR head is not a historical record of approval-time head; a merge method or deployment is not established.",
            "No signed ProofRail authorization, pre-merge status anchor, or branch enforcement is verified.",
        ],
    }


def save_json_atomic(path: str | Path, report: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=target.parent, prefix=".proofrail-", suffix=".tmp", encoding="utf-8", delete=False) as f:
            tmp = f.name
            json.dump(report, f, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp, target)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)


def run_comparison(args: Any) -> int:
    try:
        repository = _repository(args.repository)
        if Path(args.input).resolve() == Path(args.output).resolve():
            raise ComparisonInputError("input CSV and output JSON must be different files")
        rows = read_expectations(args.input)
        if args.repository_id is not None and args.repository_id <= 0:
            raise ComparisonInputError("repository_id must be positive")
        token = os.environ.get("GITHUB_TOKEN", "")
        result = compare_prs(
            repository, rows, repository_id=args.repository_id,
            fetch=lambda repo, number: get_pull(repo, number, token=token),
        )
        save_json_atomic(args.output, result)
    except (ComparisonInputError, OSError) as exc:
        import sys
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "summary": result["summary"], "authorization_proven": False}, sort_keys=True))
    if result["summary"]["unavailable"]:
        return 2
    return 1 if result["summary"]["mismatch"] else 0

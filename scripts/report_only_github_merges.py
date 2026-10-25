#!/usr/bin/env python3
"""Observe current GitHub PRs through read-only GET, never merge or spend permits.

This is a REPORT-ONLY pilot. Without an independently obtained permit and
trusted roots, every PR is marked REFUSED. Even when a permit verifies, the
result is conditional, never a real approval or completed operation.

The signed checkpoint authenticates this run's ledger to the supplied key;
it does NOT prove historical continuity unless retained/pinned externally.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.checkpoint import create_checkpoint, verify_checkpoint, verify_ledger
from proofrail.core import ProofRailError, digest_ledger_entry
from proofrail.permit import PermitError, verify_permit

REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}\Z")
SENSITIVE = ("authorization", "token", "cookie")


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_read_only(repo: str, path: str):
    """The only network path: GET against fixed api.github.com origin."""
    if not path.startswith(f"/repos/{repo}/") or "?" in path.split("/repos/", 1)[0]:
        raise ValueError("non-repository API path")
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "ProofRail-report-only-observer/0.1"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request("https://api.github.com" + path, headers=headers, method="GET")
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read())


def safe_pull_fields(pull: dict) -> dict:
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    result = {
        "number": pull.get("number"),
        "head_sha": head.get("sha"),
        "head_ref": head.get("ref"),
        "base_sha": base.get("sha"),
        "base_ref": base.get("ref"),
        "draft": pull.get("draft"),
        "state": pull.get("state"),
        "merged": pull.get("merged"),
        "mergeable": pull.get("mergeable"),
        "updated_at": pull.get("updated_at"),
        "url": pull.get("html_url"),
    }
    if not isinstance(result["number"], int) or not isinstance(result["head_sha"], str):
        raise ValueError("malformed GitHub PR response")
    return result


def read_key(value: Path):
    raw = value.read_text(encoding="utf-8").strip()
    if len(raw) == 64:
        try:
            key = bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError("key is not hex") from exc
    else:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) != 32:
        raise ValueError("Ed25519 key must contain 32 bytes")
    return key


def analyze_one(repo, pull, *, permits_dir=None, public_key=None, trust_policy=None,
                reread=None, now=None):
    observed = safe_pull_fields(pull)
    reasons = []
    if observed["state"] != "open" or observed["merged"] is True:
        reasons.append("pr_not_open")
    if observed["draft"] is not False:
        reasons.append("draft_or_unknown")
    if observed["mergeable"] is not True:
        reasons.append("mergeable_not_confirmed")
    if observed["base_ref"] != "main":
        reasons.append("not_targeting_main")

    if reread is not None:
        last = safe_pull_fields(reread)
        if any(last[field] != observed[field] for field in (
            "head_sha", "head_ref", "base_sha", "base_ref",
            "draft", "state", "merged", "mergeable"
        )):
            reasons.append("state_changed_between_reads")
        observed["last_read_head_sha"] = last["head_sha"]
        observed["last_read_base_sha"] = last["base_sha"]

    permit_result = "missing"
    if permits_dir is None or public_key is None or trust_policy is None:
        reasons.append("independent_authority_not_configured")
    else:
        path = permits_dir / f"pr-{observed['number']}.json"
        if not path.is_file():
            reasons.append("signed_permit_missing")
        else:
            permit = json.loads(path.read_text(encoding="utf-8"))
            roots = trust_policy.get("roots")
            approval = trust_policy.get("approval_digest")
            if not isinstance(roots, dict) or not isinstance(approval, str):
                reasons.append("trusted_roots_or_approval_missing")
            else:
                try:
                    verify_permit(
                        permit, public_key=public_key,
                        expected_identity_root=roots["identity"],
                        expected_evidence_root=roots["evidence"],
                        expected_policy_root=roots["policy"],
                        expected_state_root=roots["state"],
                        expected_approval_digest=approval,
                        repository=repo, pull_number=observed["number"],
                        expected_head_sha=observed["head_sha"],
                        merge_method="squash", now=now,
                    )
                    permit_result = "valid_under_supplied_roots"
                except (PermitError, KeyError, TypeError, ValueError) as exc:
                    permit_result = "refused"
                    reasons.append(getattr(exc, "code", "invalid_permit_or_trust_policy"))

    # This script does NOT fetch/establish review approvals, GitHub rules,
    # monotonic replay state, independent anchors or required CI contexts.
    reasons.append("live_merge_enforcement_not_verified")
    return {
        "pr": observed,
        "permit_verification": permit_result,
        "result": "REPORT_ONLY_REFUSED",
        "refusal_reasons": sorted(set(reasons)),
        "github_methods_used": ["GET"],
        "provider_write_attempts": 0,
        "permit_consumptions": 0,
    }


def make_ledger(records: list[dict], destination: Path):
    previous = "GENESIS"
    with destination.open("x", encoding="utf-8") as file:
        for index, record in enumerate(records, start=1):
            entry = {"kind": "proofrail.report-only-pr-observation.v1",
                     "sequence": index, "recorded_at": utcnow(),
                     "previous_hash": previous, "observation": record,
                     "outcome": "REPORT_ONLY_NO_EXECUTION"}
            entry["entry_hash"] = digest_ledger_entry(entry)
            previous = entry["entry_hash"]
            file.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
    result = verify_ledger(destination)
    if not result["valid"] or result["entries"] != len(records):
        raise ProofRailError("report-only ledger verification failed")
    return result


def main(argv=None, *, api=fetch_read_only):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="prettybusysolutions-eng/proofrail")
    parser.add_argument("--pulls", required=True,
                        help="comma-separated numbered PRs to inspect; no merges")
    parser.add_argument("--output", required=True, type=Path,
                        help="new, empty destination (never overwritten)")
    parser.add_argument("--permits-dir", type=Path)
    parser.add_argument("--trusted-issuer-public-key", type=Path)
    parser.add_argument("--trusted-roots-file", type=Path)
    parser.add_argument("--checkpoint-private-key-file", type=Path,
                        help="operator-owned key kept outside output directory")
    args = parser.parse_args(argv)
    if not REPO_PATTERN.fullmatch(args.repository):
        parser.error("repository must be owner/name")
    try:
        numbers = [int(x) for x in args.pulls.split(",")]
    except ValueError:
        parser.error("--pulls must be comma-separated positive integers")
    if not numbers or len(numbers) > 100 or len(set(numbers)) != len(numbers) or any(n <= 0 for n in numbers):
        parser.error("--pulls needs 1-100 distinct positive PR numbers")
    trust_supplied = [args.permits_dir, args.trusted_issuer_public_key, args.trusted_roots_file]
    if any(trust_supplied) and not all(trust_supplied):
        parser.error("all independent permit, issuer key and trusted-roots paths are required together")
    output = args.output.resolve()
    external_paths = [p.resolve() for p in trust_supplied if p]
    if args.checkpoint_private_key_file:
        external_paths.append(args.checkpoint_private_key_file.resolve())
    if any(p == output or output in p.parents for p in external_paths):
        parser.error("trusted keys and policy files must live outside output directory")
    output.mkdir(parents=True, exist_ok=False)

    pubkey = read_key(args.trusted_issuer_public_key) if args.trusted_issuer_public_key else None
    trust_policy = json.loads(args.trusted_roots_file.read_text()) if args.trusted_roots_file else None
    start = utcnow()
    observations = []
    for number in numbers:
        path = f"/repos/{args.repository}/pulls/{number}"
        initial = api(args.repository, path)
        reread = api(args.repository, path)
        observations.append(analyze_one(args.repository, initial,
                            permits_dir=args.permits_dir, public_key=pubkey,
                            trust_policy=trust_policy, reread=reread))
    ledger = output / "report-only-ledger.jsonl"
    commitment = make_ledger(observations, ledger)
    signing = "unsigned_report"
    if args.checkpoint_private_key_file:
        secret = read_key(args.checkpoint_private_key_file)
        key = Ed25519PrivateKey.from_private_bytes(secret)
        signed = create_checkpoint(ledger, private_key=key,
                                   key_id="external-operator-review-checkpoint")
        (output / "signed-checkpoint.json").write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n")
        public = key.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
        (output / "checkpoint-public-key.txt").write_text(public.hex() + "\n")
        if not verify_checkpoint(signed, ledger, public_key=public)["valid"]:
            raise ProofRailError("signed checkpoint fails local verification")
        signing = "operator_supplied_key_self_verified"
    result = {
        "kind": "proofrail.report-only-merge-observation.v1",
        "repository": args.repository, "observed_at_start": start, "completed_at": utcnow(),
        "num_prs": len(observations), "num_authorized_merges": 0,
        "write_requests": 0, "permit_consumptions": 0,
        "checkpoint_signing": signing, "independent_retention_proven": False,
        "ledger_verification": commitment, "records": observations,
        "claims": ["live GitHub GET observations only", "no GitHub merge action executed",
                   "no independent PR approval or checkpoint custody asserted"],
    }
    (output / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "prs": len(observations), "merges": 0,
                      "checkpoint_signing": signing, "ledger_valid": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, HTTPError, URLError, ProofRailError, ValueError, KeyError) as exc:
        print(f"REPORT-ONLY FAILED CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(4)

#!/usr/bin/env python3
"""Read-only live GitHub observer trial; synthetic, retrospective authority.

This run tests an observer against REAL GitHub PR data but does not establish
that a historical human authorized the real merge. No remote writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.acceptance_ledger import SQLiteAcceptanceLedger
from proofrail.crypto import sign_record
from proofrail.github_observer import GitHubReadOnlyPullTransport, observe_github_merge
from proofrail.reliance import AUTH_KIND, assess_reliance

AUTHORITY = ("test-ephemeral-issuer", "issuer-test-key-1")
OBSERVER = ("test-ephemeral-observer", "observer-test-key-1")
EXPECTED_VERDICTS = {
    "A_exact_merge_RETROSPECTIVE": ("applied", "ACCEPT_RECORDED_OUTCOME"),
    "B_wrong_head": ("failed", "INSUFFICIENT_EVIDENCE"),
    "C_authorized_after_merge": ("failed", "INSUFFICIENT_EVIDENCE"),
    "D_wrong_base": (None, "INSUFFICIENT_EVIDENCE"),
    "E_open_PR": ("unknown", "INSUFFICIENT_EVIDENCE"),
}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True,
        timeout=45,
    ).stdout.strip()


def pr_head_from_git(pr: int) -> tuple[str, datetime]:
    if pr < 1:
        raise ValueError("PR must be positive")
    # Fetch full HEAD; commit-time comes from git history, not REST API under test.
    git("fetch", "--no-tags", "--depth=1", "origin", f"refs/pull/{pr}/head")
    sha = git("rev-parse", "FETCH_HEAD")
    when = datetime.fromtimestamp(
        int(git("log", "-1", "--format=%ct", "FETCH_HEAD")),
        timezone.utc,
    )
    return sha, when


def branch_tip_from_git(branch: str) -> str:
    git("fetch", "--no-tags", "--depth=1", "origin", f"refs/heads/{branch}")
    return git("rev-parse", "FETCH_HEAD")


def z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def run(args: argparse.Namespace, transport=None) -> tuple[dict, int]:
    if args.merged_pr <= 0 or (args.open_pr is not None and args.open_pr <= 0):
        raise ValueError("PR numbers must be positive")
    if args.open_pr is not None and not args.open_base_ref:
        raise ValueError("--open-base-ref required when --open-pr is set")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    auth_key, observer_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    if transport is None:
        transport = GitHubReadOnlyPullTransport(os.environ.get("GITHUB_TOKEN", ""))
    merged_head, head_time = pr_head_from_git(args.merged_pr)
    base_tip = branch_tip_from_git(args.base_ref)
    if merged_head == base_tip:
        raise ValueError("base tip equals historical PR head; wrong-head case not meaningful")

    def effect(pr, head, base):
        return {
            "action_type": "github_merge",
            "repository": args.repository,
            "pull_number": pr,
            "expected_head_sha": head,
            "expected_base_ref": base,
        }

    scenarios = [
        ("A_exact_merge_RETROSPECTIVE", effect(args.merged_pr, merged_head, args.base_ref), head_time - timedelta(minutes=1)),
        ("B_wrong_head", effect(args.merged_pr, base_tip, args.base_ref), head_time - timedelta(minutes=1)),
        ("C_authorized_after_merge", effect(args.merged_pr, merged_head, args.base_ref), now - timedelta(seconds=30)),
        ("D_wrong_base", effect(args.merged_pr, merged_head, "nonexistent-proofrail-test-target"), head_time - timedelta(minutes=1)),
    ]
    if args.open_pr is not None:
        open_head, _ = pr_head_from_git(args.open_pr)
        scenarios.append(("E_open_PR", effect(args.open_pr, open_head, args.open_base_ref), now - timedelta(minutes=1)))

    results = []
    failures = 0
    with tempfile.TemporaryDirectory(prefix="proofrail-live-") as tmp:
        ledger = SQLiteAcceptanceLedger(Path(tmp) / "acceptances.sqlite3")
        guard = ledger.replay_guard(relying_party="synthetic-trial-receiver", provider="github")
        expiry = now + timedelta(minutes=15)
        for name, eff, issued in scenarios:
            authorization = sign_record({
                "kind": AUTH_KIND,
                "decision": "allow",
                "issued_at": z(issued),
                "expires_at": z(expiry),
                "signer": {"principal_id": AUTHORITY[0]},
                "effect": eff,
            }, auth_key, key_id=AUTHORITY[1])
            observation_result = observe_github_merge(
                authorization,
                authority_key=auth_key.public_key(),
                authority_principal=AUTHORITY[0], authority_key_id=AUTHORITY[1],
                expected_effect=eff,
                observer_key=observer_key,
                observer_principal=OBSERVER[0], observer_key_id=OBSERVER[1],
                transport=transport,
                now=now,
            )
            observation = observation_result["observation"]
            verdict = assess_reliance(
                authorization, observation,
                authority_key=auth_key.public_key(), observer_key=observer_key.public_key(),
                authority_principal=AUTHORITY[0], authority_key_id=AUTHORITY[1],
                observer_principal=OBSERVER[0], observer_key_id=OBSERVER[1],
                expected_effect=eff, expected_provider="github", now=now,
                already_accepted=guard,
            )
            outcome = observation.get("outcome") if observation else None
            want_outcome, want_verdict = EXPECTED_VERDICTS[name]
            passed = outcome == want_outcome and verdict["verdict"] == want_verdict
            entry = {
                "scenario": name,
                "authorization": authorization,
                "observation": observation,
                "observer_reason": observation_result["reason"],
                "observed_outcome": outcome,
                "verdict": verdict["verdict"],
                "verdict_reasons": verdict.get("reasons", []),
                "expected": {"outcome": want_outcome, "verdict": want_verdict},
                "passed": passed,
            }
            if name == "A_exact_merge_RETROSPECTIVE" and verdict.get("accepted"):
                again = assess_reliance(
                    authorization, observation,
                    authority_key=auth_key.public_key(), observer_key=observer_key.public_key(),
                    authority_principal=AUTHORITY[0], authority_key_id=AUTHORITY[1],
                    observer_principal=OBSERVER[0], observer_key_id=OBSERVER[1],
                    expected_effect=eff, expected_provider="github", now=now,
                    already_accepted=guard,
                )
                entry["replay_verdict"] = again["verdict"]
                entry["replay_reasons"] = again["reasons"]
                entry["passed"] = (
                    passed and again["reasons"] == ["evidence_already_relied_on"]
                )
            failures += int(not entry["passed"])
            results.append(entry)
            print(
                f"{'PASS' if entry['passed'] else 'FAIL'} {name}: "
                f"observation={observation_result['reason']} "
                f"outcome={outcome} verdict={verdict['verdict']}"
            )

    package = {
        "kind": "proofrail.live-github-observer-check.v0",
        "repository": args.repository,
        "evaluated_at": z(now),
        "read_only": True,
        "evidence_type": "live GitHub GET + SYNTHETIC signed retrospective authorizations",
        "git_sources": {
            "merged_pr": args.merged_pr,
            "merged_pr_head": merged_head,
            "merged_pr_head_committed_at": z(head_time),
            "base_ref": args.base_ref,
            "base_tip": base_tip,
            "open_pr": args.open_pr,
            "open_base_ref": args.open_base_ref,
        },
        "trust_anchors": {
            "authority": {
                "principal": AUTHORITY[0], "key_id": AUTHORITY[1],
                "public_key_hex": public_hex(auth_key),
            },
            "observer": {
                "principal": OBSERVER[0], "key_id": OBSERVER[1],
                "public_key_hex": public_hex(observer_key),
            },
        },
        "limitations": [
            "No historical human approval is asserted; authorizations are fabricated solely for a synthetic retrospective test.",
            "The observer reflects live GitHub REST data; git refs are a separate interface to the same GitHub operator, not independent trust.",
            "This is read-only and does not prove enforcement of real GitHub merges, CI, branch rules or independent signing custody.",
            "Offline re-verification cannot independently verify provider reality from these signed records.",
        ],
        "results": results,
        "summary": {"scenarios": len(results), "failed": failures},
    }
    return package, failures


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repository", required=True)
    p.add_argument("--merged-pr", type=int, required=True)
    p.add_argument("--base-ref", required=True)
    p.add_argument("--open-pr", type=int)
    p.add_argument("--open-base-ref")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    package, failures = run(args)
    out = Path(args.out)
    out.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"authority public key (ephemeral test only): {package['trust_anchors']['authority']['public_key_hex']}")
    print(f"observer public key  (ephemeral test only): {package['trust_anchors']['observer']['public_key_hex']}")
    print(f"evidence sha256: {digest}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

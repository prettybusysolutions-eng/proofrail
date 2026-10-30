#!/usr/bin/env python3
"""Offline check of a synthetic live-GitHub observer evidence artifact.

Requires public keys and reference identity/head provided through a separate
reviewer-controlled channel. This validates the signed records, NOT provider
truth, independent custody, or real historical approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from proofrail.crypto import verify_signature
from proofrail.reliance import assess_reliance

EXPECTED = {
    "A_exact_merge_RETROSPECTIVE": ("applied", "ACCEPT_RECORDED_OUTCOME"),
    "B_wrong_head": ("failed", "INSUFFICIENT_EVIDENCE"),
    "C_authorized_after_merge": ("failed", "INSUFFICIENT_EVIDENCE"),
    "D_wrong_base": (None, "INSUFFICIENT_EVIDENCE"),
    "E_open_PR": ("unknown", "INSUFFICIENT_EVIDENCE"),
}


def verify(package: dict, *, authority_hex: str, observer_hex: str,
           repository: str, merged_pr: int, merged_head: str,
           base_ref: str, open_pr: int | None = None,
           open_base_ref: str | None = None) -> tuple[bool, list[str]]:
    failures = []
    if package.get("kind") != "proofrail.live-github-observer-check.v0":
        failures.append("wrong_evidence_kind")
    src = package.get("git_sources", {})
    if not isinstance(src, dict):
        return False, ["invalid_source_metadata"]
    if package.get("repository") != repository:
        failures.append("wrong_repository")
    for key, value in (
        ("merged_pr", merged_pr),
        ("merged_pr_head", merged_head),
        ("base_ref", base_ref),
        ("open_pr", open_pr),
        ("open_base_ref", open_base_ref),
    ):
        if src.get(key) != value:
            failures.append("unexpected_git_source_" + key)
    trust = package.get("trust_anchors", {})
    if not isinstance(trust, dict):
        return False, failures + ["invalid_trust_metadata"]
    try:
        pinned_auth = bytes.fromhex(authority_hex)
        pinned_obs = bytes.fromhex(observer_hex)
        if len(pinned_auth) != 32 or len(pinned_obs) != 32 or pinned_auth == pinned_obs:
            raise ValueError("invalid pinned key length or separation")
        authority = trust["authority"]
        observer = trust["observer"]
        if (
            authority["public_key_hex"] != authority_hex.lower()
            or observer["public_key_hex"] != observer_hex.lower()
        ):
            raise ValueError("embedded keys are not the separately pinned keys")
        eval_time = datetime.fromisoformat(
            package["evaluated_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        if not package["evaluated_at"].endswith("Z"):
            raise ValueError("invalid evaluation timezone")
    except (ValueError, TypeError, KeyError, AttributeError):
        return False, failures + ["missing_or_unpinned_keys_or_invalid_time"]
    rows = package.get("results", ())
    if not isinstance(rows, list):
        return False, failures + ["invalid_results"]
    seen = set()
    for row in rows:
        try:
            name = row["scenario"]
            if name not in EXPECTED or name in seen:
                failures.append("unexpected_or_duplicate_scenario")
                continue
            seen.add(name)
            auth = row["authorization"]
            obs = row["observation"]
            eff = auth["effect"]
            want_outcome, want_verdict = EXPECTED[name]
            if row.get("expected") != {"outcome": want_outcome, "verdict": want_verdict}:
                failures.append(name + ":scenario_expectation_changed")
            if eff.get("repository") != repository:
                failures.append(name + ":wrong_effect_repository")
            if name != "E_open_PR" and eff.get("pull_number") != merged_pr:
                failures.append(name + ":wrong_effect_pr")
            if name == "A_exact_merge_RETROSPECTIVE":
                if eff.get("expected_head_sha") != merged_head or eff.get("expected_base_ref") != base_ref:
                    failures.append(name + ":changed_trusted_effect")
            if name == "E_open_PR" and (
                eff.get("pull_number") != open_pr or eff.get("expected_base_ref") != open_base_ref
            ):
                failures.append(name + ":wrong_open_pr_target")
            verdict = assess_reliance(
                auth, obs,
                authority_key=pinned_auth,
                observer_key=pinned_obs,
                authority_principal=authority["principal"],
                authority_key_id=authority["key_id"],
                observer_principal=observer["principal"],
                observer_key_id=observer["key_id"],
                expected_effect=eff,
                expected_provider="github",
                now=eval_time,
            )
            result_outcome = obs.get("outcome") if obs else None
            if result_outcome != row.get("observed_outcome"):
                failures.append(name + ":reported_outcome_mismatch")
            if result_outcome != want_outcome or verdict["verdict"] != want_verdict:
                failures.append(name + ":unexpected_observed_result")
            if verdict["verdict"] != row.get("verdict"):
                failures.append(name + ":recorded_verdict_mismatch")
            if row.get("verdict_reasons") != verdict.get("reasons"):
                failures.append(name + ":recorded_reason_mismatch")
            if row.get("passed") is not True:
                failures.append(name + ":original_test_failed")
            if name == "A_exact_merge_RETROSPECTIVE":
                if row.get("replay_verdict") != "REFUSE" or row.get("replay_reasons") != ["evidence_already_relied_on"]:
                    failures.append(name + ":missing_reported_replay_refusal")
        except (TypeError, ValueError, KeyError, AttributeError):
            failures.append("malformed_scenario")
    expected_scenarios = set(EXPECTED) if open_pr is not None else set(EXPECTED) - {"E_open_PR"}
    if seen != expected_scenarios:
        failures.append("missing_scenarios")
    summary = package.get("summary", {})
    if summary != {"scenarios": len(expected_scenarios), "failed": 0}:
        failures.append("nonpassing_summary")
    return not failures, failures


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("evidence")
    p.add_argument("--authority-key", required=True)
    p.add_argument("--observer-key", required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--merged-pr", type=int, required=True)
    p.add_argument("--merged-head", required=True, help="40-character head SHA obtained from git independently of evidence JSON")
    p.add_argument("--base-ref", required=True)
    p.add_argument("--open-pr", type=int)
    p.add_argument("--open-base-ref")
    p.add_argument("--expected-sha256", help="file hash pinned out of band, e.g. job log")
    args = p.parse_args()
    data = Path(args.evidence).read_bytes()
    if args.expected_sha256 and hashlib.sha256(data).hexdigest() != args.expected_sha256.lower():
        print("REFUSE: evidence SHA-256 differs from the out-of-band pinned digest")
        return 2
    try:
        pkg = json.loads(data)
        ok, errors = verify(
            pkg,
            authority_hex=args.authority_key,
            observer_hex=args.observer_key,
            repository=args.repository,
            merged_pr=args.merged_pr, merged_head=args.merged_head,
            base_ref=args.base_ref,
            open_pr=args.open_pr, open_base_ref=args.open_base_ref,
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"REFUSE: malformed evidence package: {type(exc).__name__}")
        return 2
    print("OFFLINE CHECK PASS (synthetic claims only)" if ok else "OFFLINE CHECK FAILED")
    for reason in errors:
        print("REFUSE:", reason)
    print("This does not establish independent provider truth, real prior authorization, or a verified payment.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

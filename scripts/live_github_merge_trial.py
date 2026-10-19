#!/usr/bin/env python3
"""Live GitHub trial of ProofRail's merge authority (opt-in, writes to GitHub).

Runs the real GitHubMergeAdapter, GitHubTransport and permit code against the
real GitHub API in four scenarios: happy path, head moved after the permit,
a foreign-head race (another actor merges a different head mid-attempt), and
replay of a consumed permit.

Safety: every PR targets a freshly pushed throwaway base branch
(trial/live-*-base-<run>) created from origin/main. main is never a merge
target. The script creates branches and PRs and merges them into those
throwaway bases; it does not delete them.

Usage (from a checkout with push access):
    PROOFRAIL_LIVE_TRIAL=1 PROOFRAIL_LIVE_REPO=owner/name GH_TOKEN=... \\
        python scripts/live_github_merge_trial.py > results.json

Recorded results: evidence/live-github-2026-10-19/results.json
"""
import json, os, subprocess, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.environ.get("PROOFRAIL_LIVE_TRIAL") != "1":
    sys.exit("Refusing to run: set PROOFRAIL_LIVE_TRIAL=1 (this writes to GitHub).")
REPO = os.environ.get("PROOFRAIL_LIVE_REPO", "")
if REPO.count("/") != 1:
    sys.exit("Set PROOFRAIL_LIVE_REPO=owner/name.")

REPO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_DIR))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from integrations.openclaw.github_adapter import GitHubMergeAdapter, GitHubTransport
from proofrail.permit import PermitError, execute_github_merge, mint_permit
RUN = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
ROOTS = {"identity": "1" * 64, "evidence": "2" * 64, "policy": "3" * 64, "state": "4" * 64}
APPROVAL = "5" * 64
KEY = Ed25519PrivateKey.generate()
TOKEN = os.environ.get("GH_TOKEN") or os.environ["GITHUB_TOKEN"]
api = GitHubTransport(TOKEN)
results = {"run": RUN, "repo": REPO, "scenarios": {}}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO_DIR), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def gh(method, path, body=None):
    status, _, data = api.request(method, path, body=body)
    return status, data


WORK = Path(tempfile.mkdtemp()) / "wt"
git("worktree", "add", "-q", "--detach", str(WORK), "origin/main")
_tips = {}


def wgit(*args):
    return subprocess.run(["git", "-C", str(WORK), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def make_branches(tag):
    """Push base + head branches built from origin/main; return (base, head, head_sha)."""
    base, head = f"trial/live-{tag}-base-{RUN}", f"trial/live-{tag}-head-{RUN}"
    main_sha = git("rev-parse", "origin/main")
    wgit("push", "-q", "origin", f"{main_sha}:refs/heads/{base}")
    _tips[head] = main_sha
    sha = commit_file(head, f"live trial {tag} {RUN} commit 1")
    return base, head, sha


def commit_file(branch, message):
    """Add one commit on top of `branch`'s tip and push it; return the new head SHA."""
    wgit("checkout", "-q", "--detach", _tips[branch])
    path = WORK / "trial-live" / f"{branch.replace('/', '_')}.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text(message + "\n")
    wgit("add", "-A")
    wgit("-c", "user.name=ProofRail live trial", "-c", "user.email=noreply@anthropic.com",
         "commit", "-q", "-m", message)
    sha = wgit("rev-parse", "HEAD")
    wgit("push", "-q", "origin", f"{sha}:refs/heads/{branch}")
    _tips[branch] = sha
    return sha


def open_pr(base, head, tag):
    if not base.startswith("trial/live-") or base in ("main", "master"):
        raise SystemExit(f"Refusing to target non-throwaway base {base!r}")
    s, d = gh("POST", f"/repos/{REPO}/pulls", {
        "title": f"[live trial {RUN}] scenario {tag} (throwaway base, not main)",
        "head": head, "base": base,
        "body": "Automated ProofRail live trial. Targets a throwaway base branch; never main."})
    assert s == 201, (s, d)
    return d["number"]


def wait_head(number, sha, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        s, d = gh("GET", f"/repos/{REPO}/pulls/{number}")
        if s == 200 and d["head"]["sha"] == sha and d.get("mergeable") is not None:
            return d
        time.sleep(2)
    raise TimeoutError(f"PR {number} head never became {sha}")


def permit_for(number, sha, nonce):
    return mint_permit(**{f"{k}_root": v for k, v in ROOTS.items()}, approval_digest=APPROVAL,
                       repository=REPO, pull_number=number, expected_head_sha=sha,
                       merge_method="squash", nonce=nonce,
                       expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                       issuer_principal_id="live-trial-verifier", issuer_role="verifier",
                       private_key=KEY, key_id="live-trial")


def run(permit, adapter, registry):
    return execute_github_merge(permit, adapter=adapter, registry_path=registry,
                                public_key=KEY.public_key(),
                                expected_identity_root=ROOTS["identity"],
                                expected_evidence_root=ROOTS["evidence"],
                                expected_policy_root=ROOTS["policy"],
                                expected_state_root=ROOTS["state"],
                                expected_approval_digest=APPROVAL,
                                executor_id="live-trial-executor")


class CountingTransport:
    """Pass-through transport that records every call (and optionally races)."""
    def __init__(self, inner, on_after_preflight=None):
        self.inner, self.calls, self.hook = inner, [], on_after_preflight

    def request(self, method, path, **kw):
        out = self.inner.request(method, path, **kw)
        self.calls.append((method, path.split("/repos/")[-1], out[0]))
        if self.hook and method == "GET" and len(self.calls) == 1:
            self.hook()
        return out


registry = Path(tempfile.mkdtemp()) / "replay.sqlite3"

# ---- A: happy path ------------------------------------------------------
base, head, sha = make_branches("a")
pr = open_pr(base, head, "A"); wait_head(pr, sha)
permit_a = permit_for(pr, sha, f"live-a-{RUN}-nonce")
t = CountingTransport(api)
res = run(permit_a, GitHubMergeAdapter(t), registry)
s, after = gh("GET", f"/repos/{REPO}/pulls/{pr}")
results["scenarios"]["A_happy_path"] = {
    "pr": pr, "approved_head": sha, "authority_state": res["authority_state"],
    "receipt_status": res["adapter_receipt"]["status"],
    "github_merged": after["merged"], "github_head_after_merge": after["head"]["sha"],
    "github_merge_commit": after["merge_commit_sha"],
    "remote_operation_id": res["adapter_receipt"]["remote_operation_id"],
    "calls": t.calls}

# ---- D: replay the consumed permit -------------------------------------
t = CountingTransport(api)
try:
    run(permit_a, GitHubMergeAdapter(t), registry); outcome = "EXECUTED (BAD)"
except PermitError as exc:
    outcome = exc.code
results["scenarios"]["D_replay"] = {"pr": pr, "outcome": outcome, "github_calls": len(t.calls)}

# ---- B: head moved after the permit was issued -------------------------
base, head, sha1 = make_branches("b")
pr = open_pr(base, head, "B"); wait_head(pr, sha1)
permit_b = permit_for(pr, sha1, f"live-b-{RUN}-nonce")
sha2 = commit_file(head, f"live trial b {RUN} commit 2 (unapproved)"); wait_head(pr, sha2)
t = CountingTransport(api)
res = run(permit_b, GitHubMergeAdapter(t), registry)
s, after = gh("GET", f"/repos/{REPO}/pulls/{pr}")
results["scenarios"]["B_moved_head"] = {
    "pr": pr, "approved_head": sha1, "actual_head": sha2,
    "authority_state": res["authority_state"], "receipt_status": res["adapter_receipt"]["status"],
    "reason": res["adapter_receipt"]["receipt_evidence"].get("reason"),
    "github_merged": after["merged"], "calls": t.calls}

# ---- C: foreign-head race (the #31 fix) --------------------------------
base, head, sha1 = make_branches("c")
pr = open_pr(base, head, "C"); wait_head(pr, sha1)
permit_c = permit_for(pr, sha1, f"live-c-{RUN}-nonce")
race = {}


def other_actor():
    # After our preflight saw the approved head: another actor pushes a new
    # head and merges it for real, before our exact-SHA merge request lands.
    race["foreign_head"] = commit_file(head, f"live trial c {RUN} foreign commit")
    wait_head(pr, race["foreign_head"])
    s, d = gh("PUT", f"/repos/{REPO}/pulls/{pr}/merge",
              {"sha": race["foreign_head"], "merge_method": "squash"})
    race["foreign_merge_status"], race["foreign_merge_sha"] = s, d.get("sha")


t = CountingTransport(api, on_after_preflight=other_actor)
res = run(permit_c, GitHubMergeAdapter(t), registry)
s, after = gh("GET", f"/repos/{REPO}/pulls/{pr}")
results["scenarios"]["C_foreign_head_race"] = {
    "pr": pr, "approved_head": sha1, **race,
    "authority_state": res["authority_state"], "receipt_status": res["adapter_receipt"]["status"],
    "side_effect_confirmed": res["adapter_receipt"]["side_effect_confirmed"],
    "reason": res["adapter_receipt"]["receipt_evidence"].get("reason"),
    "github_merged": after["merged"], "github_head_after_merge": after["head"]["sha"],
    "calls": t.calls}

print(json.dumps(results, indent=2))

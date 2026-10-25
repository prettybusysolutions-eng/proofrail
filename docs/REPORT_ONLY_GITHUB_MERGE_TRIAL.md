# GitHub merge-authority: report-only observation

This pilot observes **live** GitHub pull requests without merging them, using
`GET /repos/{owner}/{repo}/pulls/{number}` twice per request.

It reuses ProofRail's signature and exact-head **`verify_permit`** logic
when a reviewer supplies an independently issued permit, pinned issuer public
key and trusted policy roots. It does **not** call `execute_github_merge`,
`consume_permit`, `GitHubMergeAdapter.execute`, GitHub's merge API or a
write-capable transport.

The report-only result is always `REPORT_ONLY_REFUSED` even when a permit
validates. Required GitHub rules, reviewer independence, replay/monotonic
state, durable checkpoint custody and in-flight race closure are **not**
verified. A validated permit is not an actual authorization to merge.

## Run on your own computer

From a checkout of ProofRail with Python 3.11+:

```sh
python -m pip install -e .
# Read-only GitHub token is optional for public PRs. Never give the observer
# a write-scoped token; use fine-grained repository metadata/PR read access.
python scripts/report_only_github_merges.py \
  --repository prettybusysolutions-eng/proofrail \
  --pulls 41,44,45,46,47,48,49,50,51,54,57,58,59,60 \
  --output /path/outside-repo/proofrail-report-2026-10-25
```

The output directory must not already exist. It contains `report.json` and
a hash-chained `report-only-ledger.jsonl`. Without independently supplied
trust inputs, every PR is refused for missing independent authority and
that is **expected**, not a failed operational merge.

### Optional external permit validation

An authorized human reviewer or authority service may independently provide
`pr-N.json` signed permits, an issuer public key and a separately trusted
JSON file with `roots` (identity/evidence/policy/state) and
`approval_digest`. Supply **all** three; these values must be obtained
outside the same PR's untrusted artifacts:

```sh
python scripts/report_only_github_merges.py \
  --repository prettybusysolutions-eng/proofrail \
  --pulls 60 --output /path/outside-repo/run-002 \
  --permits-dir /external/reviewer-permits \
  --trusted-issuer-public-key /external/issuer-public-key.txt \
  --trusted-roots-file /external/pinned-roots.json
```

The script does **not** independently recompute supplied policy or state roots
from GitHub. Conditional signature verification must not be described as a
complete ProofRail merge-authorization decision.

### Optional signed checkpoint

Use an operator-owned 32-byte Ed25519 private key, encoded as 64 hex digits
or URL-safe base64, stored in a read-restricted file **outside** the output
directory. Never commit or upload that file:

```sh
python scripts/report_only_github_merges.py \
  --pulls 41,60 --output /path/outside-repo/run-003 \
  --checkpoint-private-key-file /external/operator-only-ed25519-key
```

This produces `signed-checkpoint.json` and
`checkpoint-public-key.txt` plus the ledger. ProofRail's own
`verify_checkpoint` is used to check the signature and commitment.
The included public key is only **self-asserted identity**. To detect later
joint replacement or truncation, retain the checkpoint and independently
pin its public key **outside** the agent's and repository's control.
A signed local copy beside a local ledger is not an independent checkpoint.

## Security and evidence boundaries

- PR data is read twice; another head change may still happen afterward.
- This tool never consumes permits or produces an executed-merge receipt.
- This tool does not assert GitHub CI/review/ruleset compliance or mergeability
  when GitHub returns `null` or unavailable data.
- All output is author-observed trial evidence. It is **not** independent
  validation or production-ready non-bypassable enforcement.
- No GitHub rule changes, approvals, merges, pull-request comments or
  external provider writes occur from this script.
- The signature certifies only the signer who held the supplied key, not the
  truth of GitHub's response, the completeness of a history, or secure custody.

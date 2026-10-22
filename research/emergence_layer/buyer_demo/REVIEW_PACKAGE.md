# Independent review package: buyer demonstration

Status: OPEN. No reviewer has been assigned and no review has been returned. The
author's test runs, CI results and verifier output are not independent review.

This package covers the claims in [README.md](README.md) at one exact commit. It is a
subset of the dispatcher review requested in issue #30 and
[../INDEPENDENT_DISPATCH_REVIEW.md](../INDEPENDENT_DISPATCH_REVIEW.md). It does not
close that issue: the live GitHub transport, credential custody and the
response-loss fault at a real proxy stay under #30 and go-live gate 3.

## Build the package (author or reviewer)

```sh
python buyer_demo/package_review.py --output /tmp/proofrail-review --commit <SHA>
```

The command produces:

- `proofrail-<sha12>.tar`: `git archive` of the commit;
- `docs/`: the four relevant documents at that commit;
- `evidence/`: a fresh demo run from the extracted archive;
- `verifier-report.json`;
- `demo-output.txt`;
- `environment.json`, which includes `pip freeze` and confirms `proofrail` was
  imported from the archive;
- `SHA256SUMS`.

The status line reads `PACKAGE_READY_REVIEW_OPEN`. Building the package does not
mean anything has been reviewed.

A reviewer should rebuild the package in their own clean environment rather than
trust the author's copy. They should then compare the archive's SHA-256 with one
they make themselves using `git archive --format=tar --prefix=proofrail/ <SHA>`.

## Invariants to test (report PASS or FAIL for each, with evidence)

1. **Exact bytes.** No content other than the approved text reaches the branch under
   that approval. This includes whitespace, encoding and trailing-newline changes,
   and any content change the agent signs with its own key.
2. **Exact place.** The repository, branch, path, parent commit and base tree are
   fixed by the service configuration and the approval. A request cannot change
   them, and a commit cannot touch any other path.
3. **Once.** An approval yields at most one branch update. This must hold across:
   - replay;
   - concurrent submission;
   - a process restart;
   - a lost response;
   - restoring an older registry while the journal is retained.
4. **No false success.** A lost or failed response is never reported as `MATCH`.
   `MATCH` is reported only after reading back the exact bytes at the immutable
   commit.
5. **Read-only recovery.** `recover` issues no writes on any path, including error
   paths.
6. **Evidence integrity.** Altering the signed handoff, the contract, the
   consumption record, the journal row, the approved text or a bundle makes
   `verify_evidence.py` fail, even when `SHA256SUMS` is regenerated. A verifier
   PASS implies that each bundle holds exactly one dispatcher commit per approval,
   with the approved bytes. The timing and environment fields in `summary.json`
   are self-reported and are not verified.
7. **No secret export.** The evidence directory contains no private key, token or
   service database.

## Counterexamples to attempt (report the attempt even when none is found)

- Substitute or reorder fields so that the canonical JSON changes but a lenient
  check might still pass. Try Unicode normalisation, duplicate keys, and large
  integers in `created_at` or `expires_at`.
- Approve one parent commit, then move the branch between the head read and the
  ref update. Against the local provider this must fail. Explain separately why
  GitHub's fast-forward-only update differs.
- Use an approval issued for a different repository, branch or path while the
  service configuration is unchanged.
- Kill the process between each pair of steps: reserve, consume, journal prepare,
  head read, tree, commit, ref update, readback. After each, `recover` must either
  confirm the exact bytes or refuse, and must never write.
- Edit `summary.json` to claim a refusal that did not happen, or remove a step,
  then check whether the verifier notices. Report any claim the verifier accepts
  without corroboration.
- Craft a repository bundle in which a second commit carries the dispatcher's
  commit message.

## Out of scope for this package (do not certify)

- GitHub transport, authentication, token scope, branch protection and rate limits.
- Key custody and the identity of approvers.
- Joint rollback of the registry and the journal.
- Administrator or compromised-service bypass.
- Checkpoint epoch and counter integration.
- Performance.

## Report template

```
Reviewer: <name, affiliation, contact>
Independence: <relationship to authors; conflicts; compensation, if any>
Reviewed commit: <40-char SHA>   Archive SHA-256: <digest>
Environment: <OS, Python, git, pip freeze attached>
Commands run: <exact commands and full output attached>
Invariants 1-7: <PASS/FAIL each, with evidence reference>
Counterexamples attempted: <each, with result and trace>
Findings: <ID, severity, description, reproduction trace, affected invariant>
Limits of this review: <what was not examined>
Signature: <signed report, or GitHub-authenticated comment on issue #30>
```

Do not approve on the strength of a green CI run or this author's verifier output
alone.

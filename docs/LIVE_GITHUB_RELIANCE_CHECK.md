# Live GitHub Reliance Trial — Read-Only, Synthetic Authorization

**This is test infrastructure stacked on draft PR #68. Not an operational
approval workflow, security certification or real retrospective permit.**

The trial exercises the real GitHub Pull Requests REST GET API, then the
signed observer in `proofrail/github_observer.py`, then `assess_reliance`,
then the local SQLite one-time acceptance reservation.

The authorization keys are **random ephemeral test keys generated during the
run**. A valid result does not demonstrate that the October 2026 historical
merge was actually approved by an authorized human. The test explicitly
labels its exact-match historical grant as `RETROSPECTIVE`. It is a
synthetic validation of observer implementation.

## How to execute before merging

GitHub requires a workflow file on the default branch to expose a new
`workflow_dispatch` manual Run button. To obtain a real read-only result
*without merging*, the workflow has a narrowly scoped `pull_request`
trigger and only runs for this same-repository branch:
`test/live-github-reliance-evidence-20261030`.

The job's `GITHUB_TOKEN` receives only `contents:read` and
`pull-requests:read`. It makes no authenticated write and uses an
allowlisted GitHub GET client. The run uses:
- historical already-merged PR #39; target branch `main`;
- its own still-open PR as the fifth case, with the *actual* base branch
  `feat/read-only-github-reliance-observer-20261030`.

The manual workflow remains available after a separately approved future
integration into default branch, with optional merged/open PR arguments.
**Do not merge this branch just to enable manual dispatch.**

## Evidence and review

The GitHub Actions job prints the two ephemeral test public keys and a
SHA-256 digest of `live-evidence.json`. It uploads the package as a
seven-day artifact. The built-in self-check is **not independent**:
it obtains the public keys from that same package and a git reference
from the same GitHub organization.

An external reviewer should acquire the public keys, artifact digest, known
repository, PR ID, target branch and head SHA through channels it controls
and use the offline command:

```bash
python scripts/reverify_live_evidence.py live-evidence.json \
  --authority-key <pinned-test-issuer-hex> \
  --observer-key <pinned-test-observer-hex> \
  --expected-sha256 <pinned-job-log-digest> \
  --repository prettybusysolutions-eng/proofrail \
  --merged-pr 39 --merged-head <independently-read-git-pr-head-sha> \
  --base-ref main \
  --open-pr <still-open-trial-PR-number> \
  --open-base-ref feat/read-only-github-reliance-observer-20261030
```

Successful offline verification shows the records have matching signatures
and the claimed test expectations are internally consistent. It does not
independently prove GitHub actually performed a past merge, a person signed
approval, no branch rules were bypassed, or the signer acted independently.
For true external evidence, compare with a separately acquired provider
event stream and a separately controlled signing key and trust policy.

## Scenario limitations

- A: historical correct merged head and destination base; synthetic grant
  backdated before the head commit and marked RETROSPECTIVE; acceptance
  followed by one-time local replay refusal.
- B: deliberately substituted authorized head; observer signs failed.
- C: signed grant issued *after* the historical merge; observer signs failed.
- D: intentionally wrong base branch; no signed observation.
- E: still-open PR using its own true target branch; observer signs unknown.

All are real GitHub reads but only synthetic authorizations. A GitHub head
ref read through `git fetch` comes from a different interface of the same
GitHub service, **not** an independent provider or witness.

## Release boundary

This remains an experimental testing branch. Independent semantic review,
non-retrospective real signed authority, durable external observation custody,
operator-controlled keys, a buyer-agreed GitHub-native baseline, and
well-scoped production admission remain outstanding.

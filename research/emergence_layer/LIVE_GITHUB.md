# Shared-registry integration and live GitHub evidence

## Completed trial

An exact artifact write was authorized, consumed, admitted once, executed via
the authenticated GitHub connector, and independently fetched from GitHub by
immutable commit SHA. This is real remote provider evidence, with the connector
operator explicitly inside the dispatch and observation trust boundary.

- Repository: prettybusysolutions-eng/proofrail
- Branch: trial/emergence-live-20261019
- Parent: 64db77e963eb6844a2d6282aa70fdc3563f1a252
- Result commit: 6446d19bb3c9a777af602e100a30a9ecc65924d1
- Execution: e5d92ee2-d4bc-4001-8f61-4d86f229bef5
- Path: evidence/emergence-live-artifact.json
- Artifact SHA-256: dea2c926fd2eb791e8f4030244da48457093d0ae6fe1d2bc57be4e2e70798663
- Verification: MATCH; branch head matched; repeat dispatch rejected.

[View the actual committed artifact](https://github.com/prettybusysolutions-eng/proofrail/blob/6446d19bb3c9a777af602e100a30a9ecc65924d1/evidence/emergence-live-artifact.json)

The Git data sequence used the exact prepared repository, path, bytes, base
tree and parent. The final branch update supplied the expected prior head.
Afterward, separate authenticated calls fetched the immutable file, commit
parents and branch ref. The verifier checked exact bytes, target, run ID,
consumption digest, expected artifact hash, parent and observed branch head.
Preparing the same execution for another dispatch then failed.

Evidence is in evidence/github-live-20261019:
- public-evidence.json: signed handoff, signed authority, signed consumption,
  public keys, prepared request, and replay-root observation.
- provider-readback.json: returned GitHub file bytes and commit/ref projection,
  capture timestamp and source URLs.
- result.json: actual verifier result and repeated-dispatch rejection.

The local private keys and registry database are not part of these artifacts.
Recorded evidence supports historical consistency checking. It does not make
an offline copy a fresh GitHub response or independently certify the observer.

## Shared replay registry

ExecutionLedger now inserts into the existing ProofRail permit_claims and
permit_events tables and its own emergence_executions table in one SQLite
transaction. Uniqueness of permit hash and nonce is shared across consumers.
ProofRail's existing replay_claim_exists and replay_registry_root read the claim.
Tests call the actual consume_permit API to verify both directions:

1. Emergence consumes a nonce; the existing GitHub-permit consumer rejects it.
2. The existing consumer consumes a nonce; Emergence rejects it.

Neither test calls a GitHub merge. Both are local registry compatibility tests.
The real provider effect in this report is a file commit on a trial branch.

Checkpoint-bearing authority is rejected rather than accepted without checkpoint
validation/advancement. Do not point this extension at a checkpoint-managed
deployed registry without a coordinated checkpoint integration. Earlier prototype
executions tables are not automatically migrated. Operator-selected separate
database files remain separate replay domains; global replay is not solved.

## Verification and remaining limits

The research suite reached 75 passing tests before adding archived-evidence
checks. Nine new GitHub tests use clearly marked synthetic responses and reject
wrong repo/path/ref/parent/branch/content/run ID/byte formatting. Three new shared
registry tests cover both replay directions and claim deletion.

live_github_trial.py prepares a new one-hour scoped trial and verifies captured
provider responses. It writes temporary private keys to a 0700 run directory
and a 0600 private.json file. Never publish that directory; only the three named
public evidence files are safe trial outputs. CI never performs live writes.

This remains operator-mediated, not server-enforced GitHub authorization.
GitHub credentials could bypass this local gate. A compromised trusted operator
or observer can fabricate inputs. The live trial did not inject a real network
timeout, test GitHub outages, achieve autonomous end-to-end credential custody,
or prove exactly-once behavior for arbitrary external services. Same-parent
branch updates and unique run metadata constrain this one trial; they are not
a general provider idempotency guarantee.

No production merge, release, registry migration or independent-review gate
was performed or closed. The next deployment gate is an authenticated dispatcher
that owns constrained provider credentials and enforces the prepared request,
plus checkpoint coordination and an independent review of that boundary.

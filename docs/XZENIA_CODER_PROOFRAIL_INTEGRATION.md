# Xzenia Coder ProofRail Integration

This integration gates `xzenia-coder` repository mutations with a signed,
single-use ProofRail `repository_change` authority.

## Flow

1. OpenClaw proposes a machine-readable worker job.
2. ProofRail canonicalizes the job as `proofrail.xzenia-job.v1` and derives the repository-change effect from that exact job file, repo path, base commit, allowed paths, allowed commands, acceptance tests, runtime, and model-call limits.
3. A verifier or governor mints a signed action authority envelope. The worker cannot mint this authority.
4. The OpenClaw repository adapter verifies the signature, roots, approval digest, expiry, target repo/base SHA, and exact effect parameters.
5. The adapter atomically consumes the authority in SQLite and emits a signed `proofrail.execution-consumption-grant.v1`.
6. `xzenia-coder-dispatch` verifies the signed consumption grant against the canonical job digest and live repo base before spawning the worker.
7. The worker receives only the authorized job scope.
8. The reconciler independently observes git state, changed files, patch, command log, worker ledger, artifact hashes, and final repository state root, then reruns the signed acceptance tests locally.
9. Replay, drift, split-job execution, forged consumption grants, scope expansion, false worker success, and failed tests produce explicit denial or reconciliation failure.

## Bound Fields

Changing any of these invalidates the authority: repository identity/path, base commit SHA, canonical job digest, allowed paths, forbidden paths, allowed commands, objective digest, acceptance-test digest, max runtime, max model calls, expected effect class, approval digest, trust roots, nonce, executor identity, and expiry.

## Terminal Truth

The worker final report and worker `tests.json` are evidence, not truth.
`RECONCILED` requires local observation that the signed acceptance tests pass,
artifacts exist and match recorded hashes, changed files are within the signed
scope across base-to-final history, index, worktree, and untracked files, and a
repository change actually occurred.

## Demonstrated Boundary

The included tests demonstrate single-use repository-change authority,
authority-before-worker-spawn, exact scope binding, canonical job digest
binding, forged consumption grant denial, split-job denial, replay denial, state
drift denial, independent local reconciliation, committed unauthorized change
detection, untracked unauthorized change detection, and a race where only one
consumer can consume the authority.

The included tests do not demonstrate arbitrary agent framework
interoperability, recursive agent delegation, an independent external
implementation, production key custody, distributed consensus, third-party
validation, or industry standard adoption.

## Reproduction

Run:

```bash
python -m pytest tests/test_governed_coder_repository_change.py -q
python adversarial/governed_coder_suite.py
python examples/governed_coder_reproduction/verify.py
```

These replay tests do not require a live model, local OpenClaw session, tmp
directory, local auth profile, or GitHub Copilot credentials. Live
`xzenia-coder` execution still requires a separately configured worker runtime.

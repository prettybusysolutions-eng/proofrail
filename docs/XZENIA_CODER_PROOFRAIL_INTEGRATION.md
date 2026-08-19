# Xzenia Coder ProofRail Integration

This integration gates `xzenia-coder` repository mutations with a signed,
single-use ProofRail `repository_change` authority.

## Flow

1. OpenClaw proposes a machine-readable worker job.
2. ProofRail deterministically derives the repository-change effect from the job, repo path, base commit, allowed paths, allowed commands, acceptance tests, runtime, and model-call limits.
3. A verifier or governor mints a signed action authority envelope. The worker cannot mint this authority.
4. The OpenClaw repository adapter verifies the signature, roots, approval digest, expiry, target repo/base SHA, and exact effect parameters.
5. The adapter atomically consumes the authority in SQLite before invoking `xzenia-coder-dispatch`.
6. The worker receives only the authorized job scope.
7. The reconciler independently observes git state, changed files, patch, command log, tests, worker ledger, and final repository state root.
8. Replay, drift, scope expansion, false worker success, and failed tests produce explicit denial or reconciliation failure.

## Bound Fields

Changing any of these invalidates the authority: repository identity/path, base commit SHA, allowed paths, forbidden paths, allowed commands, objective digest, acceptance-test digest, max runtime, max model calls, expected effect class, approval digest, trust roots, nonce, executor identity, and expiry.

## Terminal Truth

The worker final report is evidence, not truth. `RECONCILED` requires local observation that tests passed, artifacts exist, changed files are within the signed scope, and a repository change actually occurred.

## Demonstrated Boundary

The included tests demonstrate single-use repository-change authority,
authority-before-worker-spawn, exact scope binding, replay denial, state drift
denial, independent local reconciliation, and a race where only one consumer can
consume the authority.

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

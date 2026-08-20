# Xzenia Coder ProofRail Integration

This integration gates `xzenia-coder` repository mutations with a signed,
single-use ProofRail `repository_change` authority.

## Flow

1. OpenClaw proposes a machine-readable worker job.
2. ProofRail canonicalizes the job as `proofrail.xzenia-job.v1` and derives the repository-change effect from that exact job file, repo path, base commit, allowed paths, allowed commands, acceptance tests, runtime, and model-call limits.
3. A verifier or governor mints a signed action authority envelope. The worker cannot mint this authority.
4. The OpenClaw repository adapter verifies the signature, roots, approval digest, expiry, target repo/base SHA, and exact effect parameters.
5. The adapter atomically consumes the authority in SQLite and emits a signed `proofrail.execution-consumption-grant.v1` using a role-separated consumption signing key.
6. `xzenia-coder-dispatch` verifies the signed consumption grant against the canonical job digest, live repo base, and an explicit preconfigured consumption trust store before spawning the worker. It does not accept a caller-supplied public key or environment-selected trust store as the dispatch trust anchor.
7. The dispatcher writes a private verified canonical job snapshot and gives the worker that snapshot path, not the original caller-presented job file.
8. The reconciler independently observes git state, changed files, patch, command log, worker ledger, actual artifact bytes, and final repository state root, then reruns the signed acceptance tests locally.
9. Replay, drift, split-job execution, forged consumption grants, signer substitution, scope expansion, false worker success, and failed tests produce explicit denial or reconciliation failure.

## Bound Fields

Changing any of these invalidates the authority: repository identity/path, base commit SHA, canonical job digest, allowed paths, forbidden paths, allowed commands, objective digest, acceptance-test digest, max runtime, max model calls, expected effect class, approval digest, trust roots, nonce, executor identity, and expiry. The consumption grant additionally binds authority digest, authority nonce, canonical job digest, repository identity/path, base commit SHA, executor identity, issue time, expiry, and consumption signing key ID.

## Terminal Truth

The worker final report and worker `tests.json` are evidence, not truth.
`RECONCILED` requires local observation that the signed acceptance tests pass,
required worker artifacts exist, changed files are within the signed scope
across base-to-final history, index, worktree, and untracked files, and a
repository change actually occurred. Worker `hashes.json` is untrusted
evidence; the authoritative artifact root is derived from a reconciler-authored
`proofrail.reconciled-artifact-manifest.v1` over the actual bytes observed at
reconciliation time.

## Trust Anchor Boundary

The dispatcher resolves the consumption grant verification key from a local
trust store keyed by `signing_key_id`; the caller cannot pass an arbitrary
public key or select a replacement trust store through environment variables.
The adapter is initialized with a preconfigured trust-store path and does not
create or rewrite that trust root during job execution. This pilot assumes
integrity of the installed dispatcher, integrity and correct distribution of
the consumption trust store, and filesystem permissions that keep untrusted
jobs from replacing that trust store. It does not claim production key custody
or resistance to a same-OS-user compromise that can modify both the installed
dispatcher and its trusted configuration.

## Demonstrated Boundary

The included tests demonstrate single-use repository-change authority,
authority-before-worker-spawn, exact scope binding, canonical job digest
binding, forged consumption grant denial, split-job denial, replay denial, state
drift denial, independent local reconciliation, committed unauthorized change
detection, untracked unauthorized change detection, signer substitution denial,
unknown consumption-key denial, environment-selected trust-store denial,
trust-store fingerprint fail-closed behavior, verified worker-input snapshot
binding, reconciler-authored artifact manifest generation, and a race where
only one consumer can consume the authority.

The included tests do not demonstrate arbitrary agent framework
interoperability, recursive agent delegation, an independent external
implementation, production key custody, distributed consensus, third-party
validation, or industry standard adoption.

## Reproduction

Run:

```bash
python -m unittest tests.test_governed_coder_repository_change
python adversarial/governed_coder_suite.py
python examples/governed_coder_reproduction/verify.py
```

These replay tests do not require a live model, local OpenClaw session, tmp
directory, local auth profile, or GitHub Copilot credentials. Live
`xzenia-coder` execution still requires a separately configured worker runtime.

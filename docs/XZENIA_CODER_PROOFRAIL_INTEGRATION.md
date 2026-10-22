# Xzenia Coder ProofRail Integration

This integration gates `xzenia-coder` repository mutations with a signed,
single-use ProofRail `repository_change` authority.

## Flow

1. OpenClaw proposes a machine-readable worker job.
2. ProofRail canonicalizes the job as `proofrail.xzenia-job.v1` and derives the repository-change effect from that exact job file, repo path, base commit, allowed paths, allowed commands, acceptance tests, runtime, and model-call limits.
3. A verifier or governor mints a signed action authority envelope naming the installed worker's contract version and executable fingerprint (from the installation registry). The worker cannot mint this authority.
4. The OpenClaw repository adapter resolves the installed worker from the registry, then verifies the signature, roots, approval digest, expiry, target repo/base SHA, and exact effect parameters, including that worker binding. Authority minted for a different or unspecified worker is denied (`parameters_changed`).
5. The adapter atomically consumes the authority in SQLite and emits a signed `proofrail.execution-consumption-grant.v1` using a role-separated consumption signing key.
6. `xzenia-coder-dispatch` verifies the signed consumption grant against the canonical job digest, live repo base, and the installation-owned consumption trust store before resolving the worker. It does not accept a caller-supplied public key, CLI-selected trust store, environment-selected trust store, CLI-selected worker, or environment-selected worker.
7. The dispatcher resolves the worker from an installation-owned registry, verifies the installed executable fingerprint against the signed consumption grant, atomically records the grant in `config/proofrail-dispatch-claims.sqlite3` (a grant already recorded is refused: `consumption_grant_replayed`), and sends the verified canonical job bytes to the worker over stdin. The worker does not reopen a caller-writable verified-job path after verification.
8. The dispatcher supervises the worker: it waits up to the signed `max_runtime_seconds`, kills the worker's process group on timeout (exit 3, `worker_runtime_exceeded`), and after the worker exits kills its process group and, on Linux as a child subreaper, every remaining descendant (including ones that left the group), as best-effort cleanup; this does not establish an external containment boundary. A nonzero dispatcher exit fails the adapter immediately.
9. The reconciler first snapshots git's control files (`.git/config`, `hooks/`, `info/`, `modules/`) and the whole working tree from the filesystem, without running git. If any control file changed, reconciliation fails (`repository_control_tampered`) without running git or the acceptance tests in that repository, because hooks, `core.fsmonitor`, filters and excludes there are worker-chosen. Otherwise it runs git with system/global config disabled, fsmonitor and hooks off and no external diff or textconv, and combines git's view with the filesystem comparison, which still sees files hidden from git. It then reruns the signed acceptance tests locally.
10. Replay, drift, split-job execution, forged consumption grants, signer substitution, worker substitution, verified-input replacement, scope expansion, false worker success, and failed tests produce explicit denial or reconciliation failure.

## Bound Fields

Changing any of these invalidates the authority: repository identity/path, base commit SHA, canonical job digest, allowed paths, forbidden paths, allowed commands, objective digest, acceptance-test digest, max runtime, max model calls, expected effect class, approval digest, trust roots, nonce, executor identity, and expiry. The consumption grant additionally binds authority digest, authority nonce, canonical job digest, repository identity/path, base commit SHA, executor identity, executor contract version, installed executable fingerprint, issue time, expiry, and consumption signing key ID.

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

The dispatcher resolves the consumption grant verification key from the
installation-owned trust store at
`config/proofrail-consumption-trust-store.json`, keyed by `signing_key_id`.
It resolves the worker executable from the installation-owned registry at
`config/proofrail-worker-registry.json`, keyed by executor identity and contract
version. The caller cannot pass an arbitrary public key, select a replacement
trust store, select a replacement worker executable, or rewrite the signing key
registry through CLI flags, environment variables, adapter parameters, or the
job file. The adapter resolves the same installation trust store and does not
create or rewrite the trust root during job execution.

Trust-store and worker-registry bootstrap plus key or worker rotation are
out-of-band administrator actions: provision both files before dispatch, keep
the configuration directory writable only by the installation owner or
administrator, rotate signing keys by updating the trust store and issuing
future consumption grants with the new `signing_key_id`, rotate workers by
updating the registry and issuing future consumption grants with the new
executable fingerprint, and treat in-flight grants tied to removed keys or
replaced executables as untrusted. If the installation config is missing,
malformed, has an unknown key ID, has a trust-store fingerprint mismatch, lacks
a trusted worker entry, or the installed worker fingerprint differs from the
signed grant, dispatch fails closed before worker spawn. This pilot assumes
integrity of the installed dispatcher, integrity and correct distribution of the
consumption trust store and worker registry, and filesystem permissions that
keep untrusted jobs from replacing installed configuration or executables. It
does not claim production key custody or resistance to a same-OS-user compromise
that can modify both the installed dispatcher and its trusted configuration.

## Demonstrated Boundary

The included tests demonstrate single-use repository-change authority,
authority-before-worker-spawn, exact scope binding, canonical job digest
binding, forged consumption grant denial, split-job denial, replay denial, state
drift denial, independent local reconciliation, committed unauthorized change
detection, untracked unauthorized change detection, signer substitution denial,
unknown consumption-key denial, environment-selected trust-store denial,
CLI-selected trust-store denial, trust-store fingerprint fail-closed behavior,
stdin-transported verified worker-input binding, CLI and environment worker
override denial, installed worker fingerprint fail-closed behavior, verified
input replacement race denial, reconciler-authored artifact manifest generation,
and a race where only one consumer can consume the authority. End-to-end tests
(real adapter, real dispatcher, real worker process) cover worker-bound
authority, single-use grants at dispatch, files hidden via git excludes and
hooks, worker-planted `core.fsmonitor` never executing, changes made after the
worker's PASS report, and runtime-limit enforcement.

Also covered: replace refs and shallow grafts are control surfaces and the
reconciler's git ignores replacement objects (a committed file cannot be hidden
from it); a nested `.git` or an `include`/`includeIf` in the repository config
is refused (before consuming authority when present up front); on Linux the
dispatcher uses child-subreaper cleanup tested against selected descendant
patterns; this is not proof that arbitrary descendants cannot outlive the job.
Files are hashed in chunks rather than read entirely into memory.

Environment hardening (2026-10-20): the adapter starts the dispatcher with its
own `sys.executable -I`, not the script's `/usr/bin/env python3` shebang. Git uses
a fixed trusted path and a minimal environment. Every worker and acceptance
invocation gets fresh private HOME/TMPDIR directories under a fixed /tmp parent,
fixed locale and disabled user-site loading/global git config. Registry additions
must be uppercase application credential names ending `_API_KEY`, `_TOKEN` or
`_SECRET`; loader/interpreter/git prefixes are refused. This narrows the registry
contract: arbitrary runtime variables are no longer supported. Credential values
still come from the trusted invoking service's environment.

Acceptance tests remain untrusted code. Git control files and the working tree
are checked after they return, without running git to check control files.
A control change fails with `repository_control_tampered`; a tree change fails
with `acceptance_tests_modified_repository`.

**Two blockers remain OPEN on Linux and other platforms:** a detached descendant
can hold captured output pipes open beyond the nominal timeout; it can also write
after the final snapshot. We reproduced both with finite-lived children in a
disposable fixture. Group cleanup and the additional environment hardening do not
close these blockers. Do not deploy this path for untrusted jobs or treat a passing
reconciliation as proof that no future write can occur.

Worker and acceptance tests currently share OS privileges with the reconciler.
The external design and required acceptance probes are in
[GOVERNED_CODER_CONTAINMENT.md](GOVERNED_CODER_CONTAINMENT.md). Signed
`allowed_commands` are bound but not enforced by an independent execution boundary;
the worker's own command log cannot establish that property.

`forbidden_paths` are enforced: an entry covers that exact path and, as a
directory, everything beneath it. A job whose `allowed_paths` include a
forbidden path is refused when it is canonicalized (`allowed_path_forbidden`),
before authority is minted or consumed, and an observed change under a
forbidden path fails reconciliation (`forbidden_path_changed`).

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

# ProofRail

ProofRail turns authorization into a single-use cryptographic authority object
for autonomous execution.

The missing infrastructure was not another evaluator. It was a runtime rule:
an AI claim cannot become an action unless the evidence, policy, approval, and
result are cryptographically bound into one verifiable chain.

## What It Enforces

- Signed claim envelopes with explicit epistemic status.
- Evidence freshness, expiry, reference count, and source validation.
- Risk-based human approval bound to the exact action digest.
- Signed gate decisions that cannot be forged or replayed onto another action.
- Critical irreversible action denial.
- Append-only, hash-chained execution receipts.
- Tamper detection across the complete action history.
- RFC 8785 canonical records with Ed25519 signatures.
- Single-use permits bound to identity, evidence, policy, and state roots.
- Atomic nonce consumption before external execution.
- Independent reconciliation before an executor claim becomes observed truth.
- Governance separation that prevents learner self-promotion.

## Decision Path

```text
intent -> four authority roots -> deterministic policy
       -> signed single-use permit -> atomic consumption
       -> exact execution -> independent reconciliation
       -> append-only receipt -> governed learning proposal
```

## Run

```bash
python -m unittest discover -s tests -v
```

Install the CLI locally:

```bash
python -m pip install -e .
proofrail --help
```

Secrets are read from `PROOFRAIL_EVIDENCE_SECRET` and
`PROOFRAIL_APPROVAL_SECRET`. They are never stored in claim, approval, or ledger
files.

## Authority Object v0.2

`proofrail/crypto.py` provides RFC 8785 canonicalization, SHA-256 content
hashes, and Ed25519 record signatures. `proofrail/permit.py` mints, verifies,
and atomically consumes one-time GitHub merge permits. Each permit binds:

- identity, evidence, policy, and state roots
- approval digest
- repository and pull request number
- exact PR head SHA and merge method
- verifier identity, nonce, issue time, and expiry

`THREAT_MODEL.md` and `STATE_MACHINE.md` define the authority boundaries,
failure states, replay behavior, and crash semantics.

The v0.1 HMAC document gate remains available for compatibility. It is not the
v0.2 authority path and must not be represented as a single-use permit.

## External Verifiability v0.3

Version 0.3 adds portable JSONL ledger export, independent ledger verification,
domain-separated Merkle checkpoint roots, Ed25519 checkpoint signatures, and a
complete offline GitHub authority demo.

```bash
proofrail demo github-merge-authority
proofrail ledger export --out proofrail-ledger.jsonl
proofrail ledger verify proofrail-ledger.jsonl
proofrail checkpoint create
proofrail checkpoint verify
```

See `docs/PROOFRAIL_AUTHORITY_OBJECT.md` for the verifier protocol and
`docs/ADVERSARIAL_PROOF_MATRIX.md` for the deterministic failure matrix.

## Pilot Control Plane v0.4

Version 0.4 exposes the authority lifecycle as a tenant-scoped HTTP control
plane with separate proposer, verifier, executor, reconciler, learner,
governor, and auditor roles.

It adds:

- GitHub merge intent, evidence, evaluation, permit, execution, and
  reconciliation endpoints
- server-resolved identity and active-policy roots
- per-tenant ledgers and signed checkpoints
- JSONL, ECS, reason-code, and permit-lifecycle exports
- audit records for denied access and replay attempts

See `docs/SECURITY_MODEL.md`, `docs/TRUST_BOUNDARIES.md`, and
`docs/KNOWN_LIMITATIONS.md` for the current deployment and assurance boundary.

## Adversarial Validation v0.5

Version 0.5 stops adding authority features and attempts to falsify the current
claims. Five independently replayable suites attack replay prevention, permit
signatures, role boundaries, ledger integrity, and reconciliation.

The generated `VALIDATION_REPORT.md` preserves both demonstrated controls and
falsified claims. `validation-results.json` contains the same evidence in a
machine-readable form. See `docs/SECURITY_MODEL.md`,
`docs/TRUST_BOUNDARIES.md`, and `docs/KNOWN_LIMITATIONS.md` for the exact
assumptions and residual risks.

## Trust Elimination v0.5.1

Version 0.5.1 binds hardened permits to signed replay, observation, and
checkpoint roots plus checkpoint epoch and monotonic counter. Replay-state
rollback fails closed against the signed trust checkpoint. Policy rollback and
outcome reconciliation require signed M-of-N attestations.

The repeated adversarial report now demonstrates all 13 current expected
controls. A standalone unanchored ledger still cannot detect valid tail
truncation; the external anchor makes that boundary explicit and testable. See
`docs/TRUST_ELIMINATION.md`.

## External Anchor and Reproduction v0.5.2

Signed external anchors bind an exact ledger Merkle root, sequence range, and
trust checkpoint hash. A signed reproduction manifest commits the portable
proof bundle and expected verdicts so a stranger can replay the authority,
checkpoint, anchor, validation, and tamper checks with one command.

## OpenClaw Integration

`integrations/openclaw/bridge.py` keeps orchestration outside the kernel. It:

- evaluates every action through ProofRail before adapter execution
- prevents denied actions from reaching external systems
- persists action-digest idempotency in SQLite
- blocks replay after a successful, failed, or ambiguous started execution
- records successful actions in the tamper-evident ledger
- exports compact audit artifacts
- provides a no-shell, allowlisted subprocess adapter
- rejects adapter results that do not satisfy Adapter Contract v1

Adapter Contract v1 requires:

```json
{
  "contract": "proofrail.adapter-receipt.v1",
  "idempotency_key": "...",
  "remote_operation_id": "...",
  "status": "success|failed|unknown",
  "side_effect_confirmed": true,
  "retry_safe": true,
  "receipt_evidence": {}
}
```

External adapters must honor the supplied idempotency key because no local
runtime can prove exactly-once behavior across a crash and a remote side effect.

### GitHub merge adapter

`integrations/openclaw/github_adapter.py` implements the first real provider
boundary. It binds a merge to the expected PR head SHA, blocks changed heads,
and reconciles every claimed success, timeout, or conflict by fetching the PR
before deciding success or unknown.

The v0.2 entry point is `proofrail.permit.execute_github_merge`. It verifies
and consumes the permit before exposing the exact merge action to the provider
adapter. A consumed permit is never made reusable, including after a timeout or
failed reconciliation.

## Enterprise Foundation

- `proofrail/control_plane.py` provides tenant-scoped identities, RBAC, and
  immutable policy versions with one active version per tenant and policy name.
- `integrations/siem.py` exports ECS-compatible JSON and CEF records without
  converting unknown outcomes into success.
- `Dockerfile` and `docker-compose.yml` provide a non-root, persistent-volume
  deployment package.

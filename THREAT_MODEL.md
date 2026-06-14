# ProofRail Authority Object v0.2 Threat Model

ProofRail turns authorization into a single-use cryptographic authority object
for autonomous execution. A permit proves that a specific authority approved a
specific effect under specific evidence, policy, state, constraints, and time.
It does not prove that the policy was wise or that the executor's success claim
is true.

## Protected Assets

- Governor, verifier, executor, and reconciler signing keys
- The active identity, evidence, policy, and external-state roots
- Single-use permit nonces and the replay registry
- Append-only intent, decision, permit, receipt, and correction records
- External provider state used for preflight and reconciliation

## Trust Boundaries

1. Agents may propose actions and interpret evidence.
2. Deterministic policy evaluates authority and emits reason codes.
3. A verifier may mint a permit only for the exact evaluated effect.
4. An executor may spend a valid permit once.
5. A reconciler independently observes the external provider.
6. A learner may emit change proposals but has no policy-promotion key.
7. A governor may promote or reject a tested policy proposal.

No component may satisfy two adjacent authority roles in production without an
explicit, signed identity-root exception.

## In-Scope Threats

| Threat | Required response |
| --- | --- |
| Permit expires before execution | Deny with `permit_expired` |
| GitHub PR head changes | Invalidate before the merge call |
| Evidence, policy, identity, or state root changes | Invalidate the permit |
| Approval scope or digest changes | Invalidate the permit |
| Consumed permit or nonce is replayed | Deny atomically |
| Learner attempts to mint or promote authority | Deny by role separation |
| Executor reports success falsely | Reconciler records failure |
| Ledger record is edited or removed | Hash-chain verification exposes tampering |
| A valid ledger tail is truncated | Independently retained anchor exposes the changed Merkle root and sequence range |
| Network fails before, during, or after merge | Preserve consumed authority and reconcile |
| Two executors race for one permit | Exactly one replay-registry claim succeeds |
| Canonicalization ambiguity | Reject unsupported values before signing |
| Signature, record hash, or key ID is altered | Signature verification fails |
| Old policy is restored silently | Policy-root hash mismatch invalidates permits |

## GitHub Merge TOCTOU Boundary

Immediately before execution, the executor must re-fetch the pull request,
reviews, checks, branch protection, and exact head SHA. It must then atomically
claim the permit in the replay registry before calling GitHub with the expected
head SHA. The permit is not reusable if the API call fails or times out.

The merge response is an executor claim, not final truth. A separate provider
read must confirm the merged state and merge commit before the receipt becomes
`RECONCILED`.

## Cryptographic Assumptions

- Records use RFC 8785 JSON Canonicalization Scheme bytes.
- Content hashes use SHA-256 and lowercase hexadecimal encoding.
- Signatures use Ed25519 with role-separated keys.
- Hash links are tamper-evident, not inherently immutable.
- Append-only storage, independent verification, and periodic external Merkle
  root anchoring are required for rewrite resistance.

## Explicit Non-Goals

- Proving that the active policy is ethical, complete, or commercially wise
- Preventing compromise of every authorized signing key
- Making GitHub or another external provider Byzantine-fault tolerant
- Allowing recursive metadata or a learner to create new authority

## Failure Doctrine

Fail closed on missing evidence, unknown state, unsupported canonical values,
invalid signatures, root drift, expired authority, replay, and reconciliation
ambiguity. Corrections are new linked records; prior records are never mutated.

## v0.5.1 Trust Hardening

Hardened permits also bind replay, checkpoint, and observation roots plus a
minimum checkpoint epoch and exact monotonic counter. Permit consumption
recomputes replay state against a signed trust checkpoint. Policy rollback and
outcome reconciliation require M-of-N signed attestations.

This reduces, but does not eliminate, trust. Loss of both protected state and
all independently retained checkpoints, compromise of quorum keys, and
wall-clock expiry before checkpoint progress remain explicit boundaries.

## v0.5.2 External Continuity

A signed external anchor commits the ledger Merkle root, first and last hashes,
sequence range, and trust-checkpoint hash. A signed reproduction manifest
commits the portable verification bundle. Both controls depend on independently
trusted key distribution and retention outside the mutable evidence directory.

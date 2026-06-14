# ProofRail Trust Boundaries

| Boundary | Trusted input | Untrusted input | Required control |
| --- | --- | --- | --- |
| Proposer to verifier | Canonical intent/evidence hashes | Agent prose and confidence | Deterministic evaluation |
| Verifier to executor | Trusted verifier public key and signed permit | Permit payload before verification | Signature, roots, expiry, exact effect |
| Executor to provider | Consumed permit and exact effect | Executor success claim | Expected-state provider call |
| Provider to reconciler | Authenticated read-only provider response | Caller-supplied observed outcome | Ignore caller outcome claims |
| Ledger to auditor | Independently held signed checkpoint | Local ledger bytes | Chain and checkpoint verification |
| Learner to governor | Proposal and evidence references | Proposed authority expansion | Governor-only promotion |
| Governor to policy store | Authorized promotion decision | Stale or conflicting governor state | External quorum/rollback process |
| Replay registry to executor | Signed trust checkpoint | Local replay database | Recompute replay root before consumption |
| Checkpoint epoch to permit | Signed epoch and counter | Rolled-back local clock | Require bound epoch and exact counter |
| Ledger to external anchor | Independently retained signed anchor and trusted key | Mutable ledger and colocated copies | Recompute Merkle root and sequence range |
| Artifact to reproducer | Trusted manifest public key | Portable artifact directory | Verify manifest signature and every declared file hash |

The pilot currently uses one provider observation channel and a local SQLite
replay registry. Version 0.5.1 adds signed M-of-N attestations and a signed
trust checkpoint, but independent custody and enough uncompromised quorum keys
remain explicit trust assumptions.

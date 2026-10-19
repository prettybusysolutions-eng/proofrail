# Relationship to ProofRail

This is an isolated research module, not an alternative ProofRail runtime.
No ProofRail permit, reconciliation, canonicalization, or retry rule changes.
No ESRM conformance, independent semantic review, or production gate is closed.

The existing ProofRail implementation already checks provider observations
after execution. In particular:

- `tests/test_database_migration_authority.py` includes a lying-executor case.
- `integrations/openclaw/database_adapter.py` observes actual schema state.
- `integrations/openclaw/github_adapter.py` reads provider state.
- Pending PR #24 addresses wrong-head reconciliation and stale admission.
- Pending PR #25 compares a conventional baseline and records parity.

Therefore this lab does not establish a newly discovered ProofRail feature or
superiority over conventional recovery designs. It adds controlled ablations
of retries, durable completion, destination idempotency, and result readback
with actual child-process termination between effect and checkpoint commits.

## Semantic isolation

The lab's SMATP signatures use Python-sorted JSON, not ProofRail's RFC 8785
profile. They are not interchangeable. A signed SMATP receipt is not a
ProofRail permit, consumption grant, or settlement proof.

The local fixture can repeat an effect request because its destination enforces
a durable unique key. This must not be transferred into ProofRail's ambiguous
outcome handling as an automatic retry policy. Capability evidence and the
applicable authoritative specification govern any future adapter integration.

The parent process signs experimental observations using temporary identities.
Worker and oracle share local-host trust. This is not independent attestation.
The sample HTTP service is loopback-only and has unauthenticated reads; it is
not safe for public deployment.

## Reproduce

From the repository root:

```bash
cd research/emergence_layer
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/
python counterfactual_lab.py --output reproduced-results.json
diff -u counterfactual_results.json reproduced-results.json
```

The CI job runs Python 3.11 and 3.12 and checks every recorded observation,
including negative controls, against the committed results. These deterministic
fixtures are not statistical reliability estimates or real-provider benchmarks.

## Next integration gate

Bind a future handoff acceptance contract to an existing ProofRail action
digest and authorized target, with a versioned observer predicate. Prove that
changing either task, authority, target, expected output, or observer identity
is rejected. Preserve uncertainty when the destination cannot substantiate an
effect. Implement that bridge separately from this experimental harness.

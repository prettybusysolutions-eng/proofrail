# Relationship to ProofRail

The execution-attribution extension described in EXECUTION_ATTRIBUTION.md uses
a dedicated research consumption registry and SQLite destination. It does not
modify or silently replace the installed ProofRail registry. Its local
consume/dispatch behavior is separate from the read-only acceptance bridge.

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
python -m pip install ../..
python -m pytest -q tests/
python counterfactual_lab.py --output reproduced-results.json
diff -u counterfactual_results.json reproduced-results.json
```

The CI job runs Python 3.11 and 3.12 and checks every recorded observation,
including negative controls, against the committed results. These deterministic
fixtures are not statistical reliability estimates or real-provider benchmarks.

## Read-only integration implemented

`acceptance_bridge.py` binds the acceptance contract through the existing
authority observation-contract predicate digest and calls ProofRail's actual
authority verifier. It checks exact task, tenant, target, subject, pinned
authority, current caller-supplied roots and approval, observer identity and
key, observation freshness, and handoff binding. It never consumes authority,
dispatches an action, or grants a retry. The returned execution_authorized field
is always false. See ACCEPTANCE_BRIDGE.md for the remaining execution gate.

# Emergence Layer: counterfactual execution evidence

Date: 2026-10-19. Status: tested local research extension to the existing v0.1.

## Decision

Advance toward portable acceptance contracts: a handoff carries explicit,
machine-checkable success conditions, authorized effect scope, and a recovery
policy. Completion should be earned by observations satisfying the contract.
This is a candidate product thesis, not a claim of unprecedented invention.

## What was discovered in this artifact

The prior ZIP already implemented Ed25519 envelopes, durable task records,
signed receipt chains, and local HTTP transport. It was materially beyond the
dictionary-based bootstrap pasted in the conversation. This extension preserves
that implementation and wire format.

The next gap is between a valid completion receipt and an actual correct effect.
A receipt can authenticate a false statement. Durable recording alone also
does not eliminate the crash window between an external effect and local commit.

## Counterfactual method

Hold the task, destination fixture, two-delivery schedule, and failure location
constant. Vary recovery controls across four arms:

1. Retry only: replay on each delivery without consulting completion state.
2. Durable: consult persisted completion before retry.
3. Idempotent: durable plus destination-enforced unique effect key.
4. Verified: idempotent plus readback and expected-content digest comparison.

Six scenarios: no crash (including duplicate delivery), crash before effect,
crash after effect, crash after local completion checkpoint, false successful
acknowledgment with no effect, and successful acknowledgment of wrong content.
Crash injection terminates actual Python child processes using os._exit(73).
No finally blocks run. These are process-failure tests, not power-loss tests.

The destination and execution ledger are separate SQLite databases; they do
not share a transaction. A parent-process oracle reads destination state after
both attempts. The worker's own claim is not used as the experimental truth.
The existing SMATP ledger records signed acceptance and completion receipts.

## Observed results

24 cells, one run per cell, two child-process deliveries per cell.

| Design | Excess effects | False completion cases | Exactly one correct effect |
|---|---:|---:|---:|
| Retry only | 4 | 5 | 1/6 |
| Durable | 1 | 3 | 3/6 |
| Idempotent | 0 | 2 | 4/6 |
| Verified | 0 | 0 | 4/6 |

False completion means reporting COMPLETED when the oracle does not find
exactly one correct effect; it therefore includes duplicate-effect cases.
The verified arm deliberately leaves two cases UNCONFIRMED, with the protocol
remaining ACCEPTED. It did not magically repair a noncooperating destination.
All receipt chains validated, including chains for incorrect baseline claims.
This directly demonstrates that signature validity is insufficient for effect
correctness within the experiment.

Regression suite: 16 passed in 1.87 seconds, including five new failure tests.
Environment: Python 3.12, cryptography 46.0.7, pytest 9.1.1.
Machine-readable observations: counterfactual_results.json.

## What this establishes and what it does not

Establishes the causal contribution of the selected controls under the specified
deterministic fault schedules. Tests retain negative controls: removing readback
accepts incorrect completion; removing destination idempotency duplicates an
effect after a crash. These controls make a vacuous all-pass result harder.

Does not establish a statistical failure rate, production throughput, superiority
over Temporal or any commercial platform, customer demand, revenue, globally
exactly-once execution, or an invention humans could not create. Existing work
already covers retries, idempotency, and durable execution. The goal is to test
a useful integration and then seek differentiation through real workflows.

The readback channel is trusted here. A malicious destination that lies on both
write and read, a compromised verifier, changing state after observation, and
eventual consistency require a stronger threat model. Hash equality proves
byte equality to a predetermined target, not semantic correctness. Many tasks
need domain-specific predicates, not a predetermined content hash.

The new worker is only a lab fixture: no production scheduler, authorization
boundary, concurrent lease management, remote destination, or A2A adapter was
added. Existing unauthenticated loopback reads remain a deployment blocker.

## Concrete next architecture

An acceptance contract should bind task and tenant identity, permitted resource,
operation, stable idempotency key, verifier version, expected predicate, evidence
source, deadline, budget, and recovery policy. Sign the complete contract.

Dispatch authorized effects through destination adapters. Each adapter declares
whether it supports idempotency, querying an uncertain effect, and compensation.
If support is absent, report uncertainty rather than automatically retrying an
irreversible action. Separate worker completion claims from verifier observations.
Allow COMPLETED only after the acceptance predicate is met; preserve UNCONFIRMED
as an explicit state in a future versioned protocol extension.

First useful workflow: creation of an exact versioned artifact in an external
repository or object store. Verify destination identity, resource identity,
version and content hash. Then test lost acknowledgments, duplicate deliveries,
stale observations, revoked permissions, and destination conflict responses.

Use existing A2A transport and a durable workflow engine where suitable.
Do not rebuild these components to claim novelty. Candidate differentiation is
portable, independently testable acceptance contracts and evidence adapters.

Engineering estimate, not a commitment: one experienced engineer, 2–4 weeks for
one authenticated external adapter plus fault tests, assuming access and a stable
destination API. Local lab needs no paid service. Production budget requires
measured traffic, storage retention, security requirements, and provider costs.
Monetization hypothesis: charge for managed verification and recovery on valuable
cross-system workflows. Validate willingness to pay before assuming a toll model.

## Primary-source context

- A2A specification: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
- LangGraph persistence/durability: https://github.com/langchain-ai/langgraph
- AWS, making retries safe with idempotent APIs:
  https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- Temporal activity design:
  https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/activities/activity-definition.mdx

These sources establish the existing engineering baseline. They do not validate
this implementation; the included code and experiment results are that evidence.

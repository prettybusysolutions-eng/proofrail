# ProofRail / ESRM Machine-Action Settlement Architecture

Status: NON-NORMATIVE ARCHITECTURE BASELINE

Base protocol source: `esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md`

This directory defines the system architecture that sits around the ESRM kernel. It does not modify, supersede, or silently extend the Repair 4 normative source. Any future protocol change must be separately proposed, reviewed, assigned normative identifiers, encoded into schemas and vectors, and independently tested before it can become conformance material.

## Architectural Decision

ProofRail is not positioned as a generic AI guardrail, identity provider, policy engine, agent framework, or audit log.

The core system is a deterministic authority-and-settlement layer for consequential machine-caused state transitions.

The architecture separates five things that must never be treated as equivalent:

```text
cryptographic validity
    != authority validity
    != execution claim
    != empirical observation
    != settlement
```

The system exists to preserve those separations under retries, crashes, stale state, key rotation, delegated execution, external-provider ambiguity, and cross-organization operation.

## Product / Protocol Split

```text
ESRM
  open protocol semantics and conformance rules

ProofRail Runtime
  reference enforcement implementation

ProofRail Clearing
  optional cross-organization verification, receipt registration,
  reconciliation support, and settlement-network services

CRL / TMM / SSCE
  upstream proposal and planning systems that may request mutations
  but never create authority merely by proposing them
```

ESRM is the durable interoperability asset. ProofRail Runtime is the first implementation and enterprise product. ProofRail Clearing is a later network layer and must not be required for local protocol verification.

## Documents

- `SETTLEMENT_KERNEL_INVARIANTS.md` — non-negotiable invariants and epistemic roles.
- `SYSTEM_ARCHITECTURE_V1.md` — components, planes, data flow, interfaces, deployment topology, and scaling model.
- `CLEARING_NETWORK_AND_ECONOMICS.md` — cross-trust-domain settlement, transparency, adoption flywheel, and monetization architecture.
- `VALIDATION_AND_BUILD_GATES.md` — evidence-gated implementation sequence and failure criteria.

## Design Rule

Every component must answer one question: which ESRM fact does it produce, verify, transport, store, or independently observe?

If a component cannot answer that question and does not materially improve conformance, availability, interoperability, evidence quality, or commercial delivery, it is outside the trusted kernel.

## Compatibility Direction

The architecture is designed to consume existing standards instead of competing with them:

- workload and service identity may be supplied by systems such as SPIFFE/SPIRE;
- OAuth/OIDC, enterprise IAM, and policy systems may supply identity or authorization evidence;
- MCP and A2A may carry requests and references but do not confer ProofRail authority;
- OpenTelemetry may expose diagnostics but is not authoritative settlement evidence by default;
- in-toto and SCITT-style signed statements / transparency receipts may carry or register ProofRail artifacts where their semantics fit;
- KMS/HSM systems remain the preferred production key-custody substrate.

None of those systems is allowed to collapse ProofRail's distinction between attestation, authority, empirical evidence, adjudication, and settlement.

## Architectural North Star

A conforming independent verifier should be able to receive a portable artifact bundle and determine, without trusting the originating agent or executor:

1. what exact state transition was proposed;
2. what state, rules, identity, evidence, and authority justified it;
3. whether authority was valid and consumed exactly once;
4. whether the protected effect boundary may have been crossed;
5. what independent evidence says happened externally;
6. whether the result is MATCH, DIVERGED, INSUFFICIENT, or UNRESOLVED;
7. whether settlement is justified; and
8. whether later recovery or retry requires durable idempotency or new authority.

That verification property is more important than any specific agent framework, cloud provider, model, database, or transport.
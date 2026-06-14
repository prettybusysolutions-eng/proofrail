# ProofRail Open Standard Direction

## Decision

Do not start another AI product.

Develop ProofRail into an open, vendor-neutral runtime authority protocol for
autonomous actions. The protocol should let any agent framework, tool server,
or execution adapter answer three questions with independently verifiable
evidence:

1. What exact effect was authorized?
2. Was that authority valid, current, scoped, and single-use when consumed?
3. What external observation confirms or contradicts the claimed outcome?

This is a direction and implementation contract, not a claim that ProofRail is
already an adopted standard.

## Why This Layer Matters

Current open agent standards solve adjacent problems:

- MCP connects AI applications to tools and data and provides transport-level
  authorization.
- A2A enables agent discovery, communication, and task delegation.
- OpenTelemetry records traces, events, and metrics.
- in-toto attests software supply-chain steps and artifacts.

Those capabilities are necessary, but none by itself creates a portable,
single-use authority object bound to one exact high-consequence action, the
state inspected before execution, and independently observed provider truth
after execution.

ProofRail should complement these standards rather than replace them.

## Proposed Protocol Primitive

Name: **ProofRail Action Authority Envelope**

An envelope is a signed, canonical, single-use authorization object containing:

- issuer and subject identities;
- exact action type, target, parameters, and effect digest;
- evidence, policy, approval, and pre-execution state roots;
- constraints, expiry, nonce, and minimum trust-checkpoint counter;
- adapter contract and required observation contract;
- permitted failure and retry semantics;
- signature and verification metadata.

The envelope becomes spent before the external side effect. Success is not
established until the required independent observation contract is satisfied.
Ambiguous outcomes remain ambiguous and never silently become retryable.

## Interoperability Targets

### MCP

Carry an authority-envelope reference or digest with a consequential tool call.
The tool server must verify and consume the envelope before execution, then
return an adapter receipt that can be independently reconciled.

### A2A

Carry an authority request, issued envelope, consumption receipt, and
reconciliation result as structured task artifacts. Delegation does not expand
authority.

### OpenTelemetry

Emit stable attributes for envelope digest, permit state, reason code,
consumption status, reconciliation status, and evidence references. Traces are
observability outputs, not the source of authority.

### in-toto

Export execution and reconciliation attestations for consequential software
supply-chain actions. Supply-chain attestations remain distinct from runtime
authority.

## Required Reference Implementation

The first public reference implementation must include:

1. a framework-neutral JSON Schema for the authority envelope;
2. a deterministic verifier and atomic consumption registry;
3. a provider-neutral adapter and observation contract;
4. MCP middleware demonstrating denied, stale, successful, replayed, and
   ambiguous tool calls;
5. A2A artifacts demonstrating authority-preserving delegation;
6. OpenTelemetry semantic attributes and example traces;
7. GitHub merge and database migration adapters migrated to the common
   envelope;
8. a portable adversarial reproduction bundle;
9. a conformance suite that third parties can run without ProofRail services.

## Evidence-Gated Build Order

### Gate 0: Preserve Current Proof

- Keep the verified v0.7 behavior reproducible.
- Do not weaken the existing fail-closed or replay guarantees.
- Preserve current known limitations.

### Gate 1: Protocol Draft

- Publish the neutral envelope schema and state machine.
- Map each field to a demonstrated threat or control.
- Prove existing GitHub and database workflows can use it without special-case
  authority semantics.

Exit evidence: all existing tests pass, plus cross-domain conformance tests.

### Gate 2: MCP Reference Middleware

- Implement one consequential MCP tool behind ProofRail verification,
  consumption, and reconciliation.
- Demonstrate stale state, replay, mutated parameters, timeout ambiguity, and
  false-success denial.

Exit evidence: portable adversarial artifact independently reproduced by
someone outside the authoring environment.

### Gate 3: A2A Delegation Profile

- Demonstrate that an agent can delegate a task without transferring broader
  authority than the original envelope permits.
- Bind all delegation artifacts to the original action digest.

Exit evidence: an independent evaluator reproduces delegation-scope denial.

### Gate 4: Open Conformance Program

- Separate the protocol specification, conformance suite, and reference
  implementation.
- Accept a second implementation written by another party or in another
  language.

Exit evidence: cross-implementation verification of the same portable bundle.

## What Would Make This Significant

Significance will not come from adding more internal features. It will come
from proving that unrelated agent systems can use one portable authority object
to prevent and verify consequential actions across vendor boundaries.

The strongest defensible milestone is:

> Two independent agent frameworks, two execution domains, and two independent
> implementations reject the same invalid authority and verify the same valid
> outcome using the open ProofRail conformance suite.

## Immediate Work Boundary

The next implementation step is Gate 1 only: design and test the neutral
authority-envelope schema while preserving every current ProofRail control.
Do not publish adoption, production-readiness, or category-leadership claims
before independent evidence exists.

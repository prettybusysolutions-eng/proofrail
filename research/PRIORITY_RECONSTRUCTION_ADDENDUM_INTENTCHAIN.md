# Priority Reconstruction Addendum — IntentChain and non-AI transaction precursors

Status: RESEARCH EVIDENCE — NOT A LEGAL OPINION — NO NOVELTY CLAIM

Date: 2026-09-11

## Why this addendum exists

The first reconstruction identified Keel Permit as the strongest pre-June public overlap. Continued falsification found another material predecessor: IntentChain. The evidence below narrows the remaining ProofRail priority hypothesis further.

## IntentChain — April 2026

IntentChain publicly described an “execution rail” before ProofRail's verified June public release.

Dated public pages inspected:

- April 14, 2026 — `Why runtime governance isn't enough — and what an execution rail actually changes`
- April 20, 2026 — `No permit, no execution`
- April 20, 2026 — `Permit cryptography: why IntentChain signs every approved execution`
- April 20, 2026 — `Why the control point is the target API, not the agent runtime`

The inspected material states that IntentChain:

- places an exclusive governed path in front of the mutation target;
- evaluates deterministic policy before protected execution;
- issues an Ed25519-signed permit;
- binds the permit to the exact action, target, payload hash, agent, policy version, expiry, and unique identifier;
- verifies the permit at the gateway before downstream credential retrieval or forwarding;
- treats the permit as single-use and consumes it on first execution;
- rejects replay of a consumed permit;
- retrieves downstream credentials only at forwarding time;
- forwards the exact approved mutation; and
- stores a structured execution receipt / full audit trail.

This means the following ProofRail-adjacent claims are not available as firstness claims:

- first exclusive agent execution rail;
- first exact-request cryptographic permit for agent mutations;
- first signed single-use permit consumed on execution;
- first replay rejection based on permit consumption;
- first gateway enforcement immediately before target mutation;
- first execution receipt following such a permit.

### What has NOT yet been established in the historical IntentChain material inspected

The pages reviewed so far do not establish the same semantics as June ProofRail for all of the following:

1. authority is atomically and irreversibly consumed *before* the side effect rather than described as consumed on first successful execution/use;
2. a provider/external observation is required before executor-reported success is accepted as reconciled truth;
3. if the provider outcome is ambiguous, the consumed authority cannot be restored or blindly retried;
4. an ambiguous external effect is preserved as an unresolved epistemic state rather than collapsed into success/failure.

These are search targets, not asserted novelties.

## Keel Permit remains a distinct strong predecessor

Keel's May 10, 2026 public spec is stronger than IntentChain on signed post-dispatch closure evidence:

- exact dispatch request binding;
- signed closure artifact;
- provider response digest;
- client response digest;
- timeout, provider error, dispatch error, and missing-closure states;
- verification of Permit-to-closure relationships;
- explicit limits on what receipt boundaries prove.

IntentChain is stronger in the inspected April text on explicit single-use consumed execution permits. Keel is stronger on structured closure/reconciliation evidence. Neither inspected predecessor has yet been shown to contain the entire remaining ProofRail narrow composition.

## Non-AI transaction precursors

Traditional payment/order systems also contain important conceptual predecessors. For example, IBM Sterling Order Management documentation describes an authorization as consumed by a charge and states that a failed charge in an ERROR state does not reuse that authorization; payment-gateway uncertainty can instead remain in an invoked/open state for later validation. This demonstrates that “consumed authorization is not automatically reusable after an uncertain/failed downstream interaction” is not a concept ProofRail can claim in isolation.

This does not establish equivalence to ProofRail's agent-specific exact-action cryptographic authority architecture. It does further weaken any attempt to frame irreversible authorization consumption or recovery conservatism as independently novel primitives.

## Remaining hypothesis after this addendum

The remaining technical-priority question is now narrower:

> Before June 2026, was there a documented system combining (a) exact cryptographically bound single-use agent authority, (b) atomic irreversible consumption before externally effect-capable execution, (c) independent/provider observation as a prerequisite for accepted success, and (d) preserved ambiguity that does not restore the same authority or permit a blind retry?

Current answer: `UNRESOLVED`.

This question must be attacked as a composition question. Each individual component already has substantial predecessor evidence.

## June 12 frozen commit caveat

A June 12 ProofRail outreach message references frozen commit:

`02097bc798817f96b06aef9116a20ebe710096a5`

The currently connected public ProofRail repository does not resolve that SHA, and GitHub commit search under the connected Pretty Busy Solutions organization did not return it. Therefore its exact code contents have NOT been independently recovered in this reconstruction. The email remains dated evidence of what was externally represented at that time, but the inaccessible SHA must not be described as a verified repository artifact until it is recovered from another source.

## Updated research state

`FIRST_EXECUTION_RAIL = REJECTED`

`FIRST_EXACT_SINGLE_USE_AGENT_PERMIT = REJECTED`

`FIRST_PERMIT_PLUS_EXECUTION_RECEIPT = REJECTED`

`FIRST_SIGNED_POST_DISPATCH_CLOSURE = REJECTED / KEEL PREDECESSOR`

`NARROW_CONSUME_OBSERVE_AMBIGUITY_COMPOSITION_PRIORITY = UNRESOLVED`

`LEGAL_NOVELTY_OR_PATENTABILITY = NOT_ESTABLISHED`

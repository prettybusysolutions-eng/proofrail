# ProofRail Action Authority Envelope v1

The Action Authority Envelope is ProofRail's framework-neutral authority
primitive. It binds one subject to one exact effect under one current set of
identity, evidence, policy, state, approval, adapter, observation, and failure
semantics.

The normative schema is:

`schemas/action_authority_envelope.schema.json`

## Required Invariants

- The envelope is signed by a verifier or governor.
- The effect digest covers action type, target, and complete parameters.
- An adapter must accept an idempotency key.
- Authority is consumed before the external effect.
- An ambiguous outcome becomes `RECONCILIATION_FAILED`.
- Any retry requires new authority.
- Success requires the declared observation contract.

## Relationship To Existing Permits

The existing GitHub merge and database migration permits remain the executed
and reproduced authority paths. The neutral envelope currently proves that
both domains can share one authority contract. Migrating execution onto the
neutral envelope requires a later evidence-gated change and must preserve all
current replay, drift, and reconciliation controls.

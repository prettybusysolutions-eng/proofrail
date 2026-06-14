# ProofRail Authority State Machine v0.2

## Monotonic States

```text
PROPOSED
  -> EVALUATED
  -> PERMITTED
  -> EXECUTING
  -> CONSUMED
  -> RECONCILED
```

Terminal failure states:

```text
DENIED
EXPIRED
INVALIDATED
EXECUTION_FAILED
RECONCILIATION_FAILED
```

States never move backward. No record is deleted or overwritten. A correction
or recovery is represented by a new record linked to the prior record hash.

## State Meaning

| State | Meaning |
| --- | --- |
| `PROPOSED` | An exact action intent exists, without authority to execute. |
| `EVALUATED` | Active policy evaluated the bound evidence and state roots. |
| `PERMITTED` | A signed, scoped, expiring permit exists. |
| `EXECUTING` | The replay registry atomically claimed the permit and nonce. |
| `CONSUMED` | The authority object is spent and can never authorize another attempt. |
| `RECONCILED` | An independent provider observation confirms the claimed outcome. |
| `DENIED` | Policy refused the proposed effect. |
| `EXPIRED` | The permit deadline passed before claim. |
| `INVALIDATED` | A bound root, approval, constraint, or provider state changed. |
| `EXECUTION_FAILED` | The effect definitely did not occur after authority was consumed. |
| `RECONCILIATION_FAILED` | External truth is ambiguous or contradicts the executor receipt. |

## Transition Guards

### `PROPOSED -> EVALUATED`

- Canonical action intent exists.
- Identity, evidence, policy, and state roots are present.
- Unsupported or ambiguous values are rejected.

### `EVALUATED -> PERMITTED`

- Deterministic policy returns a permit reason code.
- Approval digest covers the exact action scope.
- Permit issuer has the verifier role.
- Learner and executor identities cannot mint permits.
- Nonce is unique and expiry is in the future.

### `PERMITTED -> EXECUTING`

- Ed25519 signature and record hash verify.
- All four roots match current verified roots.
- Approval digest, repository, PR number, head SHA, and merge method match.
- Expiry has not passed.
- Replay registry atomically claims the permit hash and nonce.
- Signed trust checkpoint replay root matches current replay state.
- Checkpoint epoch meets the permit minimum and monotonic counter matches
  exactly.

### `EXECUTING -> CONSUMED`

- The claim transaction commits before the provider call.
- This transition spends authority, not confirms success.
- Crash recovery must not make the permit reusable.

### `CONSUMED -> RECONCILED`

- M-of-N signed observations confirm the PR is merged.
- Provider evidence contains the observed merge commit SHA.
- The reconciler signs a receipt linked to the consumed permit.

## Invalid Transitions

- Any transition from a terminal state
- Any transition backward
- `PERMITTED -> RECONCILED` without consuming authority
- `CONSUMED -> PERMITTED` after a failed or ambiguous execution
- Learner proposal directly becoming active policy
- Executor receipt directly becoming observed provider truth

## Crash Semantics

- Crash before replay claim: permit remains usable until expiry.
- Crash after replay claim but before GitHub call: permit remains consumed;
  record `EXECUTION_FAILED` after provider reconciliation.
- Crash during or after GitHub call: reconcile externally before assigning a
  terminal outcome.
- Reconciliation unavailable: record `RECONCILIATION_FAILED`; never retry with
  the consumed permit.

# ProofRail v0.6 Second Execution Domain

ProofRail v0.6 applies the same authority chain used for GitHub merge to a
SQLite schema migration. This demonstrates that the authority object is not
specific to GitHub governance.

## Bound Authority

A signed migration permit commits:

- identity, evidence, policy, and state roots
- the exact human approval digest
- a stable operator-assigned database identity
- the resolved database path and local device/inode fingerprint
- the complete current SQLite schema root and `user_version`
- the exact migration source digest
- the expected post-migration schema root
- the target schema version
- nonce, expiry, issuer, and optional trust-checkpoint state

Any schema drift or migration-source change invalidates the permit before it is
consumed.

## Execution And Reconciliation

The replay registry consumes authority before the migration reaches SQLite.
The adapter executes the signed migration in an immediate transaction. A
separate read-only schema observation then determines the result.
SQLite authorization denies `ATTACH`, `DETACH`, and migration pragmas other
than the governed `user_version`, preventing the signed script from expanding
its effect to another database.
Symlink targets and path or inode replacement are rejected before execution.
Exceptions after permit consumption return a non-retryable
`RECONCILIATION_FAILED` result.

An executor success claim is insufficient. The authority reaches `RECONCILED`
only when the independently observed schema root and `user_version` match the
permit. Ambiguous or false executor claims fail closed and the permit remains
consumed.

## Demonstrated Generality

The two execution domains now share the same security properties:

1. signed, exact-effect authority
2. immutable evidence and policy roots
3. single-use consumption before side effects
4. state-change invalidation
5. provider-state reconciliation
6. fail-closed handling of ambiguous outcomes

The adapter is intentionally local and uses SQLite. v0.6 does not claim
production database safety, distributed transaction support, or independent
third-party validation.

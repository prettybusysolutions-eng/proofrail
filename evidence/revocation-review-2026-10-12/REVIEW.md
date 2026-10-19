# Internal adversarial review — 2026-10-12

## Verdict

**Universal revocation protection: contradicted for the tested pilot.**
**Acquisition value: not established by the available evidence.**
**Independent external review: not completed.**

This review was performed by the assistant that helped author the repairs and
comparison. Changing its role does not remove that conflict. No external reviewer
was contacted, hired, or simulated. No production protection was added here.

## Scope and methods

Reviewed runtime source from remote commit
`ca6dabe312b7975a4c1832a952b9af7251b9c5bd`, tree
`6b8ee360c5121422f52bec0a2e59ad734d23fae0` (local equivalent commit differs).
Inspected server admission, governance mutation, permit consumption and GitHub
transport/reconciliation. Added deterministic concurrent counterexample tests
through the full pilot request path, including its signed checkpoint path, the
production adapter and real loopback HTTP. Direct provider SQLite reads verify
effects. No real GitHub mutation was performed.

Added a finite schedule model to distinguish local admission from an atomic
provider fence. Consulted primary GitHub API documentation, Google's Zanzibar
paper description and Carta's acquisition guide. This is a focused review of the
two requested claims, not an exhaustive security audit or financial appraisal.

## Finding R1: revocation can complete before dispatch and still fail to stop it

Reproduction: `tests/test_revocation_boundary_review.py`.

1. Create a tenant, active merge policy, evidence, evaluation and permit.
2. Start normal pilot execution, including local authorization, checkpoint
   validation, durable claim and adapter preflight.
3. Pause immediately before the HTTP PUT is sent. The provider has zero effects.
4. Commit a role downgrade or activate a policy allowing no action types.
   For the role case, a fresh authorization query now rejects the executor.
5. Release the HTTP PUT. Pilot returns 200 and the adapter reports success.
   The separate provider database records one effect.

Both cases reproduced. `counterexamples.log` preserves their ordered traces.
This is stronger than merely observing an already-dispatched request finishing.
The governance methods do not participate in the server's execution lock.
The lock-entry repair remains useful for changes completed before admission, but
is not a barrier for changes after admission.

Impact: a blocker for a claim that completed revocation stops every subsequent
effect. If the contract instead permits already-admitted actions to finish, this
is a documented semantic boundary rather than a violation of that narrower rule.
The system must explicitly choose and expose its contract.

## Finding R2: another local check does not establish atomic external revocation

The schedule `check -> revoke -> effect` remains possible after any final local
check if the provider commits independently and does not enforce the current
authority state. Short expiry reduces some exposure but is not instant revocation;
timeouts do not prove that the provider stopped. Cancelling a client connection
does not undo a committed effect. A custom request header is not evidence that
the provider enforces idempotency or revocation.

GitHub documents a merge `sha` precondition for the PR head. Its documented merge
request does not include ProofRail's policy/identity epoch. Head matching protects
the version condition, not an atomic relationship to ProofRail governance.
This conclusion is about the inspected integration, not a claim that GitHub has
no native authorization or token revocation.

`benchmarks/revocation_model.py` enumerates all 30 schedules of two old-grant
actions (each check before effect) and one revocation. The local-check model
violates the post-revocation effect invariant in 16 schedules. A model with an
atomic provider epoch comparison has zero violations and allows 20 total commits
across the schedules, so it is not simply denying every action.

That result is exhaustive ONLY within this five-operation model. It assumes
atomic operations and excludes crashes, rollback, partitions, compromised actors,
replica lag and new grants. It verifies no production implementation.

## A defensible narrower implementation target

Proposed contract: for writes to a controlled transactional database, after a
revocation transaction commits, no transaction using that revoked grant epoch
may commit a new protected effect. Earlier committed effects are not undone.

Minimum design:

- Keep tenant/subject authority epoch, grant status, consumed operation IDs and
  the protected data in one transactional enforcement domain.
- Signed grants bind tenant, subject, epoch, exact effect and operation ID.
- Effect transactions lock the authority row, compare epoch and grant state,
  consume the operation ID uniquely, and apply the write in the same transaction.
- Revocation transactions lock that same row and increment its epoch. Acknowledge
  revocation only after commit. Retry serialization failures without bypassing
  checks; treat ambiguous commits as unresolved until authoritative observation.
- Deny direct writes that bypass the transaction path. Fail closed when current
  authority cannot be obtained. Restore procedures must not resurrect old epochs
  or erase consumed IDs without an independent freshness mechanism.

This defines an ordering: either an effect commits first, or revocation commits
first and rejects the stale effect. Revocation may wait for an existing transaction;
instant acknowledgment and cancellation of arbitrary in-flight work are not promised.
An outbox transaction protects enqueueing only, unless the final consumer also
enforces the required boundary. A gateway alone cannot manufacture provider atomicity.

Resources: an isolated database, two execution clients and one revocation client,
fault injection, retained traces, and a reviewed schema/transaction implementation.
Acceptance requires concurrent tests on the actual database, process termination,
ambiguous commits, failover, restoration, tenant isolation and credential bypass.
This review supplies a specification and finite model, not an implementation or
credible production schedule/cost estimate. Do not fund a broad rewrite on these
results alone. First tie this narrower primitive to a concrete adopter workflow.

## Acquisition assessment

A buyer may acquire technology before revenue, but our tests cannot establish a
buyer's willingness to pay. Carta describes acquisition motives including capability,
market access and cost/revenue synergies; none supplies a valuation for ProofRail.

| Value proposition | Evidence here | Assessment |
| --- | --- | --- |
| Universal revocation | Two full-pilot counterexamples | Contradicted |
| Better shared merge safety than conventional composition | Same 11 expectations met by both paths | No advantage shown |
| Better execution latency | Higher median and p95 in all three retained local runs | No advantage shown in that scope |
| Portable proofs/checkpoints reduce buyer work | Not evaluated by the base-mode comparison | Open hypothesis |
| Cost or time saved for an acquirer | No measured buyer integration/rebuild estimate in this package | Unknown |
| Transferable business asset and ownership | No complete ownership, contracts or capitalization diligence in scope | Unverified |
| Customer demand and acquisition interest | No customer commitments or buyer offer supplied in this package | Unestablished |

The narrow fenced primitive is not automatically novel: mature authorization
systems already address consistency, and Zanzibar documents causal ordering in
authorization decisions. This does not make Zanzibar identical to ProofRail or
prove it solves arbitrary external-write revocation. It does rule out treating
the general consistency idea itself as evidence of a unique moat.

There is no supported dollar valuation here. Unknown value is not zero value.
Replacement cost, if measured later, would still not equal acquisition price.
The plausible next technical hypothesis is whether independently verifiable
execution evidence measurably reduces an adopter's audit or integration work.
That needs a feature-complete baseline and an actual workflow; it is not validated
by the current comparison. No LLC, revenue claim, buyer interest or acquisition
premium is established by this review.

## Verification and reproduction

85 unit tests passed, including two tests that PASS by reproducing the known
revocation failure. Do not present that total as 85 security guarantees.
An initial invocation on the default interpreter failed to import `rfc8785`;
the rerun used the previously provisioned audit virtual environment successfully.

```bash
python -m pip install .
python -m unittest discover -s tests -p test_revocation_boundary_review.py -v
python benchmarks/revocation_model.py
python -m unittest discover -s tests -v
```

No broader retest of deployment, real GitHub behavior, key custody or disaster
recovery was performed in this turn. Frozen semantic Gate 1B remains open.

## Primary sources checked 2026-10-12

- GitHub REST pull requests, merge endpoint:
  https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#merge-a-pull-request
- Google Research, Zanzibar: Google's Consistent, Global Authorization System:
  https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/
- Carta, M&A Essentials (general acquisition context, not a ProofRail appraisal):
  https://carta.com/learn/startups/exit-strategies/mergers-acquisitions/

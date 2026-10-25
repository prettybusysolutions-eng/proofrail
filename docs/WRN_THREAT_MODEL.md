# WRN threat model: facility-outcome pilot

Scope: `pilots/facility_outcomes/` on branch `feat/verified-outcome-facility-pilot`.
Author-run analysis; **not** an independent security review.

## Assets

- **The provider's create-work-order call**, the pilot's only automated side effect.
- **Single-use execution authority**: the envelope and its replay-registry claim.
- **The attribution of an effect to the authority that caused it.**
- **Outcome claims and settlement eligibility.**
- **Tenant data**: identities, sites, evidence references.

## Adversaries considered

- An agent or caller who submits envelopes or records.
- A provider that answers wrongly or lies.
- A contractor who claims completion.
- A non-independent inspector.
- A user of another tenant.
- Someone who edits stored records or exported bundles.
- A crash or restart at any point.
- An operator who restores backups.

**Not** considered:
- an attacker holding the authority-issuer key;
- an attacker holding a tenant principal's private key;
- an administrator who rolls back *every* store at once (see L-1).

## Findings made while building and attacking the pilot

Every row is fixed or mitigated in this branch unless it is marked as a core
proposal.

| ID | Finding | Status |
|---|---|---|
| F-1 | `proofrail.envelope.verify_action_authority_envelope` does not check the issuer role (that is enforced only at mint), the subject (executor), or not-before (`issued_at`). Its schema validator is built without a format checker, so `"format": "date-time"` is not enforced, and a timestamp without a timezone is parsed as local time. `state` and `failure_semantics` *are* enforced, as schema constants. | The pilot gateway enforces the issuer principal, role and key, the subject, and not-before. **Core proposal:** make the verifier accept the expected issuer and subject and check `issued_at <= now`. Not changed in core here. **Core fix in draft PR #44.** Once it merges, the gateway's own not-before check (`authority_not_yet_valid`) is redundant: core raises the same reason first, and a sweep of this stack with #44 and #48 shows that check surviving removal with its test still passing. It stays until #44 is on main. |
| F-2 | The envelope v1 had no execution path on `main` (mint and verify only). | The pilot adds the first integration (`proofrail_gateway.py`). It reuses the `consume_permit` registry schema and transaction rather than a new primitive. |
| F-3 | The pilot's own `schemas/` folder shadowed core's top-level `schemas` package, because `importlib.resources.files("schemas")` resolved to the pilot directory. | Renamed to `contracts/`. Any directory named `schemas` on `sys.path` ahead of ProofRail breaks core envelope validation; worth a core note. |
| F-4 | The gateway initially trusted the problem's stored `evidence_root` field. Changing the evidence list without updating that field passed the evidence check. | The evidence root is now recomputed from the evidence refs, and the problem signature (by its confirming reviewer) is verified at approval and admission. |
| F-5 | Updating the authority reference rewrote the whole stored authority record, dropping the admission snapshots and markers. | It now merges into the existing record. Export depends on this. |
| F-6 | The identity root and the audit chain spanned all tenants. Exporting a case would leak the other tenant's principals, and one tenant's staff change invalidated every other tenant's authority. | Both are now per tenant, and a test checks that another tenant's change leaves authority valid. |
| F-7 | `buyer_decide` read case data before checking the caller's tenant, so an outsider learned whether a verdict existed (`no_verdict`). | Every public step now checks tenant membership first. |
| F-8 | Settlement treated any earlier non-VERIFIED verdict as blocking, and any verdict change as a dispute. The ordinary sequence (claim only, then an inspection, then verified) could never be paid. | Only `REJECTED` / `DISPUTED` block, and only a change between definite verdicts is a dispute. `INSUFFICIENT_EVIDENCE` → `VERIFIED` is progression. |
| F-9 | A provider record altered *after* reconciliation was still settled. | Settlement re-reads the provider and denies `work_order_changed_since_reconciliation`. |
| F-10 | The ambiguity and concurrency tests first accepted any of several outcomes, so they could not tell which defence acted. | Pinned to exact outcomes. The three ambiguity paths and three single-use layers each have their own test. |

## Threats, mitigations, evidence

The matrix with test names and side-effect counts is in
`docs/WRN_ACCEPTANCE_GATES.md`. In summary:

- **Forged or misused authority.** Issuer principal, role and key; subject;
  signature; the four roots and the exact effect recomputed from *current*
  records; not-before; expiry; success predicate.
- **Replay.** Three layers, each tested on its own:
  1. the replay registry (`permit_replayed`, including after a process restart);
  2. the business store's admitted record (`authority_already_admitted`, when the
     registry is rolled back or deleted);
  3. the state root (the work state has moved on).
- **Concurrency.** Two worker *processes* admit one envelope; exactly one
  provider order results.
- **False attribution.** Only an independent read can reconcile. A 201 for
  another operation, a response naming another tenant, a stored order with
  altered parameters, and duplicates all end in `RECONCILIATION_FAILED`.
- **Ambiguity.** Timeout after accept, a dropped connection, and a provider that
  dies mid-request each end `RECONCILED` or `EXECUTION_UNKNOWN` by reads alone.
  Reconciliation is counted and refused if it would write.
- **False completion.** Contractor claims are always excluded. Inspections must
  come from a buyer-designated inspector who is not part of the provider
  organisation, with evidence at the right facility and area, captured after the
  order was created and within the window, and not reused from the problem
  report.
- **Settlement abuse.** Duplicates, the cap, the currency, the work order, a
  forged invoice, an unapproved provider, a missing acceptance, a dispute, a
  reviewer acting as authorizer, and an earlier rejection are each denied with
  their own reason.
- **Tenant isolation.** A cross-tenant read is indistinguishable from a missing
  record. Cross-tenant steps, export and spending are refused.

## Known limits (not solved here)

- **L-1 Joint rollback.** Restoring *both* the replay registry and the business
  store from before an admission lets the gateway call the provider a second
  time. The pilot shows the backstops (provider idempotency on the envelope hash,
  and duplicate detection on read) and a test records the second call. Closing
  this needs an independently retained checkpoint or anchor, as in ProofRail's
  trust checkpoints (checkpoint-bearing envelopes are refused here,
  `checkpoint_authority_not_supported`).
- **L-2 Audit tail truncation** is undetectable without an external checkpoint.
  A test demonstrates it.
- **L-3 Key custody.** Keys are generated per run and held in memory, or in
  `0600` test files for multi-process tests. They prove only test identities.
  There is no rotation or revocation of keys.
- **L-4 Physical truth.** Inspections are attested, not proven. Independence is
  checked against registered organisations and roles, not verified
  institutionally. Evidence files are bound by digest but not stored or
  interpreted.
- **L-5 Transport.** The provider is a local HTTP simulator, so real-provider
  semantics, authentication and rate limits are not exercised.
- **L-6 Single node.** SQLite on one host; no PostgreSQL, distributed fencing or
  durable job orchestration.
- **L-7 No telemetry.** OpenTelemetry was not implemented, so "sensitive content
  in telemetry" is not testable yet.
- **L-8 Evidence deletion.** Evidence blobs are not stored, so "deleted evidence
  referenced by an accepted claim" is not testable yet.

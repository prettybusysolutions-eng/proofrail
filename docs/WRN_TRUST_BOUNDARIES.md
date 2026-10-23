# WRN trust boundaries: facility-outcome pilot

Each boundary says what crosses it, what the receiving side checks, and what it
must *not* assume. The boundaries follow the handoff's six layers.

| # | Boundary | What crosses | Checked on receipt | Never assumed |
|---|---|---|---|---|
| 1 | Business coordination → ProofRail authority | the approval record and the plan/problem ids | Approval signature by a registered tenant approver. The approval digest, plan digest, provider, cap, currency and validity. The problem is confirmed and signed by a reviewer. Policy limits. Not revoked. | That coordination logic or an AI recommendation is authority. Coordination cannot call the provider. |
| 2 | Authority issuer → gateway | an Action Authority Envelope v1 | Issuer principal, role and key; subject is this gateway; signature; four roots and exact effect recomputed from current records; not-before; expiry; predicate; no unsupported trust block. Single use in the replay registry and the business store. | That the envelope's own parameters, roots or target are correct. They are compared against recomputed values. |
| 3 | Gateway → provider | one create request (Idempotency-Key = envelope hash) | Fixed origin, no redirects, timeout. Any failure, non-2xx or unparseable body counts as an unknown outcome. | That a 2xx response means the authorized effect happened. |
| 4 | Provider → observer → execution reconciliation | the provider's stored orders for the envelope's client reference | Exactly one order, matching every authorized parameter and the tenant, and consistent with any claimed response. Signed by the observer's own key. | That provider state is honest beyond what is read. A later change is caught at settlement (F-9). |
| 5 | Contractor / inspector → outcome verification | signed completion claims and inspections | Signature by the registered key; inspector designated by the buyer for this facility and independent of the provider organisation; subject, time window and evidence location; capture time after creation; no reuse of report evidence. | That a claim, a photo reference or a signature proves the physical condition. |
| 6 | Outcome → buyer → settlement authorization | the verdict, the buyer's acceptance, the provider's invoice | The verdict is signed by a reviewer and is the latest, with no rejection or dispute on file. The acceptance is signed by the buyer and bound to that verdict digest. The invoice is signed by the approved provider for this order, within the cap and in the same currency. The authorizer is independent of the reviewer and performer. One decision per order. The provider record is unchanged. | That a VERIFIED outcome is payment authorization. Money never moves. |
| 7 | Case → learning | banded outcome features | No identifiers; data-rights flag; `causal_claim: none`. | That a later improvement was caused by the intervention. |
| 8 | Bundle → external verifier | signed records, snapshots, the registry claim, the audit chain | Checksums; signatures (self-asserted unless `--trusted-keys`); roots recomputed from snapshots; registry claim; exact provider match; verdict recomputation. | That self-signed consistency authenticates origin. |

## Separation of duties enforced

- **Performer** (provider organisation: contractor, billing) and **outcome
  reviewer**: different organisations. A provider-employed reviewer is refused.
- **Inspector**: designated by the buyer and outside the provider organisation.
- **Settlement authorizer**: not the latest reviewer, not the performer, and not
  in the provider organisation.
- **Authority issuer** and **gateway**: separate principals. The gateway holds no
  authority key.

Where real institutional independence is unavailable (all principals here are
synthetic), these checks rest on registered organisation and role data. Bundles
say so in `confidence_limitations`.

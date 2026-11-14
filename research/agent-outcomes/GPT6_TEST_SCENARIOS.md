# GPT-6 Independently Authored Adversarial Cases — Public Review Set

**Authored:** 2026-11-13, before reading Claude's full Round 2 tab. **Status:** candidate public scenarios, NOT sealed/held-out, NOT scored.
**Research question:** Can a completeness-aware reconciliation system distinguish confirmed missing effects from insufficient observation evidence more accurately than a strong conventional monitor?

The expected label is conditioned on assumptions. Each test must separately score (1) obligation validity, (2) authorization, (3) effect occurrence, (4) effect correctness, (5) finality, (6) observation completeness, and (7) sufficiency of evidence. Incomplete provider data must not be treated as proof of absence.

| ID | Scenario | Expected result |
| --- | --- | --- |
| T01 | Authorized refund has matching customer, payment, amount, currency and finalized provider state. | Verified effect; authorized execution. |
| T02 | Agent submits signed success log for a refund; an independent authoritative complete dataset proves no matching refund after deadline. | Confirmed outcome gap; reject success. |
| T03 | Refund exists for correct amount but belongs to wrong customer/original payment. | Outcome mismatch, not verified. |
| T04 | Provider accepted operation and issued ID, but settlement is pending within allowed processing window. | PENDING; do not label completed or definitively failed. |
| T05 | Refund verified at time A is reversed at time B. | Retain time-A finding and new time-B reversal; never promise permanent finality. |
| T06 | Read-only provider observation API unavailable. | INSUFFICIENT_EVIDENCE, not definite missing effect. |
| T07 | Authoritative schedule requires weekly maintenance, scheduler disabled, deadline passed, and complete observation proves none occurred. | CONFIRMED_GAP (with valid schedule and coverage). |
| T08 | Valid governor-authorized waiver predates job deadline. | No overdue obligation; preserve authorization evidence. |
| T09 | An attributable provider-side effect exists but was never included in agent reports. | Unreported effect when full enumeration and attribution are sufficient. |
| T10 | Provider action exists but actor might be agent or human. | INSUFFICIENT_EVIDENCE for agent-specific attribution. |
| T11 | Two obligations require separate effects, but one effect ID is reused for both. | Coverage violation; never double count when contract forbids sharing. |
| T12 | Provider returns inconsistent pagination while its dataset changes; no snapshot/watermark. | Cannot certify complete enumeration or definite absence; retry/abstain. |

## Adversarial baseline arms

- B0: self-reported execution history and signatures.
- B1: durable workflow, idempotency, independent readback and scheduler monitoring, with ordinary reconciliation and error handling.
- B2: the strongest practical conventional script (including snapshot, cursor stability, clock skews, expected schedules, waiver logic, independent provider API readback, and coverage attestations). This is deliberately hard to beat.
- Candidate C: obligation-to-effect/observation-completeness solution based on Grantifold's code, but only after a distinct value claim survives B2.

No product superiority can be asserted from tests chosen by the system author. Public tests are development cases, not independent validation. Held-out scoring labels must be committed as hashes or escrowed with the founder before implementation and unsealed once predictions are frozen.

## Release blockers

- Any false verified success in a high-risk case.
- Any definite missing-obligation judgment where obligation authority, dataset completeness or relevant deadlines are not established.
- Any case of fabricated observer independence, hidden fallback to agent assertions, or invented provider events.
- A claimed differentiation that disappears when compared with B2 at similar cost/complexity.

## Open design questions

1. What constitutes an authoritative obligation set? Who signs it and how are late waivers handled?
2. Which provider APIs support consistent snapshots, watermarks or otherwise provable full enumeration?
3. How do retention, partial access permissions, timezones, clock drift and aggregation affect 'nothing happened' conclusions?
4. If complete observation is impossible, can a useful probabilistic coverage bound be justified without disguising it as certainty?
5. Does the required buyer pay for better completeness proof or for ordinary monitoring and reconciled reporting?

These are **test specifications**, not test outcomes.

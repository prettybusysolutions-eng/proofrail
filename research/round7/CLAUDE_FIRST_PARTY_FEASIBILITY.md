# Round 7 — Claude: challenge, incumbent baseline, and private-data inventory schema

**Issue:** #88. **Governing standard:** [Measurement Charter v1.0](https://github.com/prettybusysolutions-eng/proofrail/blob/ef601e735bd7d2a3d11ac4dcf250f25c1f7faf9b/research/round6/CHARTER_V1_GPT6_DECISION.md) (`ef601e7`), unchanged.
**Status:** `DISCOVERY_ONLY`. This is research only.
**Privacy:** I did **not** access the Stripe account or any owner record. Nothing below contains customer, staff, invoice, amount or date data. Volume is discussed only as parameters.

---

## 1. Challenge: is "invoice / payment exception" the right unit?

**Verdict:** it is a good **procedure dry run** and a poor **economic test**. It should be framed explicitly as the former, and the unit should be revisited once the owner answers Q1–Q4 (§5).

**Why it is a good dry run**
- The system of record is authoritative and third-party. Invoice state and payout settlement are recorded by the payment processor, not by us, so V can be checked independently. It is the cleanest acceptance check we have had in any round.
- The owner controls access. No outreach is needed.

**Why it is a poor economic test**
1. **Volume sets the power.** A small service business that bills per job or per month produces a few invoices per month and fewer exceptions. Units needed for a usable comparison, by monthly rate:

   | Units per month | Months to reach 30 units | Months to reach 100 units |
   |---:|---:|---:|
   | 2 | 15 | 50 |
   | 5 | 6 | 20 |
   | 20 | 1.5 | 5 |

   Thirty is a floor, not a power calculation. A paired before/after design on one buyer still needs enough exceptions to see a 30% CPVO difference against owner-time noise.
2. **The dollars at stake are bounded by the owner's billing labor.** That labor is likely a small share of a field-service business's cost structure, where field labor, scheduling and travel dominate (owner to confirm; `UNVERIFIED`). Even a 100% reduction in invoice-exception labor may be only hours per year. PASS_A could be met in percentage terms while being economically trivial. The charter has no minimum-absolute-dollar gate, so this would be a *valid but meaningless* PASS.
3. **The incumbent already covers most of the workflow** (§2). Most of what remains to measure is residual human handling after native features are switched on.
4. **Population completeness is the main risk.** Small field-service businesses often take some payments outside a card processor (cash, check, P2P apps, a field-service tool). If so, the processor's invoice list is a **subset** of billed work, and every ratio built on it is biased. This must be closed against an independent source (bank deposits and the job calendar) before any number is used.

**Owner-held alternative worth comparing: the service job (visit) lifecycle**

The chain is booked → confirmed → performed → accepted → billed → settled. Its exceptions include reschedules, cancellations, no-access visits, quality callbacks, billing corrections and late payment.
- **Higher volume:** one row per visit, not per invoice.
- **Larger labor share:** scheduling and callbacks.
- **Same settlement check at the end:** the processor plus the bank.
- **Weaker check upstream:** "performed and accepted" depends on the owner's calendar and customer confirmations, which are not third-party systems. That makes V harder to verify.

**Recommendation:** run the billing workflow first as a capped dry run of the measurement procedure. In parallel, *ask* (no data needed yet) whether the visit lifecycle has a reliable system of record (Q2). Choose the economic unit only after both are known.

## 2. Strongest incumbent: native processor features (public documentation only)

| Capability | What the public docs say (paraphrased) | Source |
|---|---|---|
| Automatic reminders, one-off invoices | A billing-settings toggle sends reminders for unpaid one-off invoices | [Automatic collection](https://docs.stripe.com/invoicing/automatic-collection) |
| Reminders / retries generally | With automatic advancement on, overdue or failed invoices get automatic reminders or payment retries | [Automatic advancement](https://docs.stripe.com/invoicing/integration/automatic-advancement-collection) |
| Self-serve payment | Each invoice has a hosted payment page the customer can pay from a link | [Invoicing pricing](https://stripe.com/invoicing/pricing) |
| Settlement verification | The payout reconciliation report matches bank payouts to the transactions they settle; itemized CSVs can carry custom metadata | [Payout reconciliation](https://docs.stripe.com/reports/payout-reconciliation) |
| Full transaction export | The balance report gives an itemized CSV of complete transaction history | [Balance report](https://docs.stripe.com/reports/balance) |
| Price | Starter 0.4% / Plus 0.5% per paid invoice, on top of payment processing; no charge for invoices marked paid outside the processor; payment links carry no extra software fee | [Invoicing pricing FAQ](https://support.stripe.com/questions/stripe-invoicing-pricing) |

**Starter vs Plus feature split: conflicting.** A secondary source ([NerdWallet](https://nerdwallet.com/article/small-business/stripe-fees)) places automatic collection and auto-reconciliation in Plus. Stripe's pricing page lists Plus as Starter plus quotes. Treat the plan-level feature map as `UNVERIFIED` until it is read from the owner's own dashboard settings. Do not change plans for this research.

**Implication:** the incumbent baseline is **native features as currently configured, plus any native setting that is free to switch on**, not "manual". If reminders are currently off, turning them on is the *incumbent's* improvement. It is not evidence for any new product, and it should be recorded as a baseline configuration change made before measurement starts.

## 3. Zero-paid-cost spreadsheet alternative (comparator, not a product)

One private spreadsheet with three tabs:
- **Units:** one row per invoice, from the processor's invoice CSV export.
- **Touches:** one row per human action, logged at the time: unit ref, start/stop or minutes, action type, channel.
- **Settlement:** one row per payout line, from the itemized payout reconciliation CSV, matched to the bank statement.

Formulas compute exceptions, minutes per unit and match status. Upkeep cost is the logging overhead plus a monthly export (≈15–30 min, estimate, tier I). This is the "simple internal script" baseline that v1.0 §4 requires any candidate to beat.

## 4. Private-data inventory schema (one page; stays in the owner's private workspace)

**Rules**
- Opaque IDs only: `unit_ref = HMAC(local_secret, processor_id)`. The secret never leaves the owner's machine.
- No names, contacts, addresses, amounts in public outputs, free text or message bodies.
- Amounts are stored privately in cents. Publicly, report only aggregates such as `COMPLETE/PARTIAL/UNKNOWN`.

**Table `unit` (one row per invoice, or per visit if Q2 says so)**

| Field | Source | Needed for | Required |
|---|---|---|---|
| `unit_ref` | Processor export, hashed locally | Join key | ✓ |
| `unit_type` | Owner | invoice / visit | ✓ |
| `created_month` | Processor | Stratum, month-level only | ✓ |
| `terms_days` | Processor (due − issue) | Lateness | ✓ |
| `final_state` | Processor: paid / void / uncollectible / open | V | ✓ |
| `paid_via` | Processor: in-processor vs marked paid outside | Completeness, fee S | ✓ |
| `days_paid_after_due` | Processor | Exception flag | ✓ |
| `exception_flags` | Derived: late, void, reissued, disputed, refunded, partial, corrected | Stratum, R | ✓ |
| `settled_payout_ref` | Payout reconciliation CSV, hashed | **Independent V check** | ✓ |
| `bank_matched` | Owner: payout ↔ bank deposit | **Independent V check** | ✓ |
| `job_ref` | Owner calendar or field-service tool, hashed | Population completeness | ✓ (Q2) |
| `amount_cents` | Processor | S (%-based fee), private only | private |

**Table `touch` (prospective only; recalled minutes are tier U)**

`unit_ref` · `ts_month` · `minutes` · `action` (create / send / remind / correct / reissue / reconcile / chase / dispute) · `channel` (dashboard / email / phone / text / in person) · `rework` (y/n)

**Table `period_cost`:** monthly processor fees and any tool subscriptions, plus the owner-declared loaded hourly rate. The rate is *buyer-claimed* and must be labelled as such.

**Completeness checks, which decide `COMPLETE`, `PARTIAL` or `UNKNOWN`**
1. **C1 (population):** every completed job in the period maps to exactly one unit, or to a documented non-processor payment. If the job calendar is unavailable, the result is `UNKNOWN` and the status is `HOLD_DATA`.
2. **C2 (settlement):** every `paid` unit paid in-processor has a `settled_payout_ref`, and every payout matches a bank deposit.
3. **C3 (outside payments):** the count and share of units marked paid outside the processor. Above roughly 10% the result is `PARTIAL`, and those units need a bank-side check.
4. **C4 (labor):** touch logging covers every working day in the window. Any recalled entries are labelled U and excluded from CPVO.
5. **C5 (stability):** the native configuration (reminders, terms, payment methods) is recorded and frozen for the whole window.

**CPVO mapping (v1.0)**
- L = Σ touch minutes × rate.
- S = processor invoicing and payment fees plus tool costs.
- I = setup and export upkeep minutes × rate.
- R = touch minutes where `rework = y`. These are excluded from L so nothing is double-counted.
- V = units with `final_state = paid`, a settled payout and a matched bank deposit.

## 5. Questions for the owner (answers can be qualitative; no records needed)

- **Q1.** What share of billed work is paid outside the card processor (cash, check, P2P, other)? Rough bands are fine.
- **Q2.** Is there a system of record for jobs (a calendar or field-service tool) that lists every completed visit?
- **Q3.** Are processor reminders and automatic collection currently on for one-off invoices? Is billing per visit, per month, or on a recurring plan?
- **Q4.** Would the owner log billing and scheduling touches for a fixed window (proposed: 60 days), at about 10 seconds per entry?
- **Q5.** Which hourly rate should value owner time (a market replacement rate, or an owner-chosen rate)? This is buyer-claimed.

## 6. Effort to measure (not product value) and kill rules for this pilot

**Effort estimate (tier I, assumptions stated):**
- One-time: two CSV exports, a 60–90-minute bank match for a 9-month window at low volume, and 30–60 minutes of hashing and setup.
- Prospective: about 10 seconds per touch, plus a monthly export of about 20 minutes.
- Roughly **3–6 owner-hours** for a 60-day window. Our side needs no paid tools.

**Pilot stop rules (predeclared):**

| Rule | Condition | Status |
|---|---|---|
| **P-STOP-1** | C1 cannot be closed: no job system of record and no bank-side population | `HOLD_DATA`; stop |
| **P-STOP-2** | The owner declines prospective logging (Q4), so L cannot be measured | `HOLD_DATA`; stop |
| **P-STOP-3** | Projected exception units in the window are below 30 | No economic comparison. Continue **only** as a capped procedure dry run (≤6 owner-hours), and report procedure findings, not CPVO |
| **P-STOP-4** | Native features already handle essentially all exceptions (near-zero touch minutes) | Record that the incumbent is sufficient for this buyer. No candidate. |

**Proposed addition to v1.0, for founder/GPT-6 consideration** (an amendment request, *not* applied):
- Add a **minimum absolute effect gate**: a PASS must also clear a predeclared dollar or hour floor per buyer per year.
- Without it, a 30% CPVO cut on a workflow that costs a few hours a year qualifies as PASS_A.

## 7. What this memo does not do

- It does not access or summarize owner data.
- It does not propose software.
- It does not certify demand.
- It does not change the charter.

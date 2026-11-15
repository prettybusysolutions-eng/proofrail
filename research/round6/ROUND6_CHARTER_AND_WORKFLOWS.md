# Round 6 — Frozen metric charter and buyer-workflow evidence (Claude, first response)

Issue: #85. Research only: no code, no outreach, no paid API, no product named.
Sources accessed 2026-11-15. Every number carries an evidence tier (§1.3). Every derived number shows its arithmetic.

---

## Part 1 — Metric charter (proposed for freeze)

The charter is product-agnostic. It is meant to be frozen **before** any candidate architecture is named or any result is seen. Changing it afterwards needs a dated amendment in DECISIONS.md, and the founder must accept that amendment before results are re-scored.

### 1.1 Primary score (one metric)

**CPVO: cost per verified useful outcome**, measured on the buyer's own unit of work.

```
CPVO = (L + S + I + R) / V

L  = direct labor minutes on the unit × buyer's loaded labor rate
S  = software/vendor/transaction fees attributable to the period
I  = integration + maintenance labor for the period (setup amortized over 12 months, plus ongoing upkeep)
R  = rework cost: labor to correct units that failed verification, appeals, resubmissions
V  = count of units that pass the buyer-defined verification check in the period
```

Why one metric: CPVO is denominated in the buyer's own expense. Integration and maintenance labor (the founder's ≥50% threshold) is a **component** of it (I), not a rival score. Every input is reported separately, so the I-only comparison stays visible.

### 1.2 Pass / kill (predeclared)

| Rule | Condition |
|---|---|
| **PASS-A** | CPVO ≥ 30% lower than the **strongest conventional option** (§1.4), over the same units, same period, with every guardrail held |
| **PASS-B** | I (integration + maintenance labor) ≥ 50% lower than the strongest conventional option, **and** CPVO not higher, with every guardrail held |
| **KILL-1 (baseline)** | The workflow's baseline cost cannot be established at tier B or better (§1.3). It is then recorded as "no qualified workflow", not estimated. |
| **KILL-2 (headroom)** | The gap between the strongest conventional option and the median buyer is already ≥30% **and** that option is free or near-free. The available gain then belongs to adoption of the existing tool, not to a new architecture. |
| **KILL-3 (verification)** | "Verified useful outcome" cannot be defined as a check that a third party can run without the candidate's own output. |
| **KILL-4 (result)** | The experiment misses both PASS-A and PASS-B, or any guardrail regresses |

The comparison is always against the **strongest conventional option, including any free one**, never against the manual worst case. Survey-reported savings (manual → electronic) are an upper bound on headroom, not a baseline.

### 1.3 Evidence tiers (data quality)

| Tier | Meaning | Can it set a baseline? |
|---|---|---|
| **O** observed | Measured by us or from the buyer's own logs, under this charter | Yes |
| **R** regulated disclosure | Statutory or regulatory filing (e.g. annual agency reports, procurement records) | Yes; note how the filer estimated it |
| **B** benchmark survey | Multi-organization survey with a published method (e.g. CAQH/NORC, APQC) | Yes, as a range; self-reported |
| **V** vendor claim | Vendor, reseller or vendor-sponsored source | No; context only |
| **I** inferred | Our arithmetic on higher-tier inputs | Only if every input is ≥ B; show the formula |
| **U** UNVERIFIED | Secondary source not traced to its primary, or an extraction we could not confirm | No |

A synthetic or estimated figure never moves up a tier by being reused.

### 1.4 Required fields per workflow

Buyer role · purchase authorizer · unit of work · frequency/volume · current workflow · baseline cost per unit (with tier) · strongest conventional option, its price and any free/OSS option · verification check for "useful outcome" · guardrails · why adopt rather than rebuild · what the sources prove · what they do **not** prove.

### 1.5 Guardrails (must not regress; not scored)

- Wrong-outcome rate: units that pass internal checks but are later reversed, denied, appealed or litigated
- Security/privacy incidents: zero new disclosures of regulated data (PHI, PII, payment data)
- Deadline adherence: statutory or contractual turnaround not worse
- Human-review coverage for any irreversible action: not lower than baseline

### 1.6 Measurement procedure

1. Freeze this charter (hash it in DECISIONS.md) before any candidate is named.
2. Pick a workflow that passes KILL-1/2/3 on desk evidence alone.
3. Define the sample: N units, period, and the buyer-defined verification check, before data collection.
4. Measure the baseline on the strongest conventional option first (tier O, or tier R/B where O is not authorized).
5. Run the candidate on the same units. Scoring is done by a party that did not build the candidate (no self-grading).
6. Report every CPVO input, the confidence interval, and every guardrail. Unknowns stay `UNVERIFIED`.

---

## Part 2 — Three buyer-owned recurring workflows

All three were chosen because a public, method-documented source measures the **buyer's own** recurring cost. None is AI-tooling.

### W1. U.S. federal FOIA request processing

| Field | Value | Tier |
|---|---|---|
| Buyer role | Agency Chief FOIA Officer / FOIA program office | R |
| Purchase authorizer | Agency contracting officer (FSS/GSA schedule task orders) | R |
| Unit | One FOIA request processed to closure | R |
| Volume FY2025 | 1,707,197 received; 1,635,055 processed; backlog 339,671 (+27%) | R |
| Staff | 4,823.17 FTE (down from ~5,628 in FY2024) | R |
| Cost FY2025 | Processing $610,670,216; litigation $50,724,642; total $661,394,858; fees collected $2,511,193 | R (agency-estimated) |
| Cost per processed request | $610.67M / 1,635,055 = **$373.49** processing; $404.51 including litigation | I (inputs R) |
| Requests processed per FTE | 1,635,055 / 4,823.17 = **339** | I |
| Turnaround | Simple requests average 48.96 days (44 in FY2024) | R |
| Strongest conventional option | FOIAXpress (OPEXUS): vendor says it is used by 85% of federal agencies. Example procurement: the USAID task order rose from $795,293.75 to $1,055,293.75 | V for share; R for contract |
| Free/OSS | FOIA.gov national portal for intake (scope not verified for processing; `UNVERIFIED`). State/local SaaS lists $99–$499/month (one vendor listing), and another vendor's listing shows a $2,000 starting price | V |
| Verification check | Request closed within statutory time, with no successful administrative appeal or litigation reversal (appeal and litigation data are in the same annual reports) | R |

**What the sources prove:** the total labor-dominated spend, volumes, staffing, backlog and timeliness, each year and each agency, through a statutory reporting regime with a public dataset. The cost per unit can be computed per agency without contacting anyone.
**What they do not prove:** how cost splits between search, review/redaction, consultation and correspondence. Agencies estimate costs, and the method varies by agency. Software spend is not separated out. The share of cost that a tool could actually touch is `UNVERIFIED`.
**Adopt vs rebuild:** agencies buy COTS through schedules and do not build. The barriers are high: FedRAMP, sole-source follow-ons, and paid migration contracts when switching. For an entrant this cuts both ways: the incumbent is entrenched, but the buyer does not rebuild in-house.

### W2. Medical-provider prior authorization (with claim-status inquiry as a sibling)

| Field | Value | Tier |
|---|---|---|
| Buyer role | Practice administrator / revenue-cycle director | B |
| Purchase authorizer | Practice owner or CFO; EHR/clearinghouse contract owner | `UNVERIFIED` |
| Unit | One prior-authorization request | B |
| Adoption | Fully electronic PA was 40% of medical PAs in the 2025 Index (31% in 2023) | B |
| Time saved | 14 min per PA by adopting the electronic standard (2024 Index); 15 min versus fax/email/mail (2025 Index slides) | B |
| Industry savings opportunity | Medical $18.7B across all transactions (2025); PA alone $461M (2025 slides) | B |
| Per-PA cost, historical | Manual $10.92; portal ~$4; electronic $1.88 (2020 Index, 2019 data); 21 / 8 / 4 minutes | B (dated) |
| Per-transaction cost, 2025 | The public executive report gives only an all-transaction average. As extracted: electronic $3.39 vs manual $8.03. **The label-to-value mapping is `UNVERIFIED`.** The per-transaction breakdown sits in paid "Index Pro" | B / U |
| Method | 600+ provider orgs and health plans (63% of insured lives); NORC collects the data; cost = labor (salaries, benefits, overhead) | B |
| Strongest conventional option | Availity Essentials multi-payer portal: **free to providers**, payer-sponsored, covering PA submit/status | V (corroborated by several payer pages) |
| Paid tier | Essentials Pro, ~$100–$300/month according to a third-party guide | U |
| Regulatory pipe | CMS-0057-F: payers must publicly report PA metrics (first due March 31, 2026); the Prior Authorization API is required from January 1, 2027 | R |
| Verification check | PA approved on first submission with no resubmission; denial overturn rate as a guardrail | B |

**What the sources prove:** this is a large, recurring, labor-measured provider expense, and a large remaining manual and portal share.
**What they do not prove:** the cost difference between the **free portal** and an alternative. CAQH measures manual → electronic, which is an upper bound. The current per-PA cost split by mode is not public for 2025. A federal mandate is about to move integration onto payer-built APIs, so I (integration labor) may fall for everyone without any new entrant.
**Adopt vs rebuild:** practices do not build; they adopt EHR, clearinghouse or portal tools. PHI and HIPAA raise both the barrier and the guardrail cost.

### W3. Accounts-payable invoice processing (cross-industry)

| Field | Value | Tier |
|---|---|---|
| Buyer role | AP manager / controller | B |
| Purchase authorizer | Controller / CFO | `UNVERIFIED` |
| Unit | One supplier invoice processed to payment | B |
| Cost per invoice | APQC median $5.83; top quartile ≤$2.07; bottom quartile ~5× the top | B (survey publication date older; current tables are members-only) |
| Gap, median → top quartile | (5.83 − 2.07) / 5.83 = **64.5%** | I |
| Other benchmark | Ardent Partners: $10.89 average, $2.78 top performers (via a vendor blog) | U |
| Strongest conventional option | Ramp Bill Pay: core AP free; Plus $15/user/month plus an unpublished platform fee. BILL: $49/$65/$89 per user/month plus $0.59 per ACH. QuickBooks Bill Pay Basic included with QBO | V (vendor pages via secondary sources) |
| Verification check | Invoice paid correctly and on time; first-pass match without exception | B |

**What the sources prove:** a long-measured, widely benchmarked unit cost with a wide spread between performers.
**What they do not prove:** that the spread is due to anything other than adopting tools that already exist. Several of those tools are free.
**Adopt vs rebuild:** buyers adopt, and they rarely build. But the free tier is the counterfactual. **W3 trips KILL-2:** the gap from median to top quartile is >30% and is captured by free or cheap incumbents.

---

## Part 3 — Ranking (data quality and unit economics; not novelty, not fit)

| Rank | Workflow | Baseline tier | Unit economics | Main risk |
|---|---|---|---|---|
| 1 | **W1 FOIA processing** | **R**, per agency, public, annual, reproducible without outreach | ~$373 processing cost per processed request; backlog rising while FTE fell 14% | Cost is agency-estimated, with no task split; long procurement; sensitive records; incumbent with 85% share (vendor claim) |
| 2 | **W2 Prior authorization** | **B** (NORC survey, labor-only cost) | Per unit a few dollars and ~14–15 min; huge volume | Free payer-funded portal plus a federal API mandate shrink the headroom; the 2025 per-mode breakdown is paywalled |
| 3 | **W3 AP invoices** | **B**, older public figures | $2–$6 per invoice | **KILL-2**: free incumbents already capture the gap |

**Bottom line:** W1 is the only workflow where a baseline can be built at tier R today, per buyer, without contacting anyone. W2 qualifies on data but probably fails on headroom once measured against the free portal and the 2027 API. W3 should be recorded as not qualified under KILL-2.

None of this establishes that any architecture can beat the incumbents. It establishes only where a baseline is measurable.

## Part 4 — Smallest next measurements (for GPT-6 to challenge or pick; no product)

1. **W1, desk-only:** from the FOIA.gov FY2025 dataset, compute processing cost per processed request and requests per FTE **per agency**, and the gap from median to top quartile. If top-quartile agencies are already ≥30% below the median, record the source of the headroom as practice, not technology, until shown otherwise. Tier R inputs; no outreach; free data.
2. **W2, desk-only:** verify the 2025 CAQH mapping of $3.39/$8.03 against the chart, and look for any public portal-versus-API cost figure. If none exists, W2 stays at "headroom `UNVERIFIED`".

## Source ledger

| # | Source | Used for | Tier |
|---|---|---|---|
| S1 | DOJ OIP, *Summary of FY2025 Annual FOIA Reports* (justice.gov/oip/media/1450791/dl) and OIP blog of July 2, 2026 | W1 volumes, cost, FTE, backlog, timeliness | R |
| S2 | USAID sole-source extension notice, task order 7200AA24C00107 (samsearch.co / govly listings) | W1 contract value | R (secondary mirror) |
| S3 | Carahsoft OPEXUS page ("used by 85% of federal government agencies") | W1 incumbent share | V |
| S4 | G2 CivicRecordsOnline listing; Capterra GovQA listing | W1 state/local price points | V |
| S5 | 2025 CAQH Index Executive Report (index.caqh.org) | W2 adoption, volumes, savings, method | B |
| S6 | CAQH 2026 eSolutions Xchange slides | W2 15 min, $461M | B |
| S7 | CAQH 2024 Index Key Takeaways; caqh.org/explorations/caqh-index | W2 14 min, $515M | B |
| S8 | HFMA (2020 Index coverage) | W2 historical per-mode cost and minutes | B (dated) |
| S9 | Payer pages: Premera, MVP, Wellpoint; availity.com | W2 free portal | V (corroborated) |
| S10 | CMS Prior Authorization API page; WEDI/CMS slides | W2 mandate dates | R |
| S11 | APQC "Metric of the Month" (CFO.com) | W3 median and quartiles | B |
| S12 | Vendor price pages via secondary sources (Ramp, BILL, QuickBooks) | W3 incumbent price | V |

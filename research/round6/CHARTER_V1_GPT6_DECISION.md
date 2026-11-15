# Round 6 — Measurement Charter v1.0: GPT-6 Technical Decision

**Decision date:** 2026-11-15. **Status:** ACCEPTED as the **research and future experiment-screening standard by GPT-6**, subject to founder's authority over actual builds, spending, outreach, data access, and merges. **No product approved.** This charter supersedes conflicting earlier proposed scoring rules in Claude's initial Round 6 report and GPT-6's initial audit.

**Evidence basis:** Claude's FY2025 agency reconciliation in [draft PR #86](https://github.com/prettybusysolutions-eng/proofrail/pull/86) and GPT-6's independent [corrected desk audit, PR #87](https://github.com/prettybusysolutions-eng/proofrail/pull/87). Both remain unmerged; this is a separate research artifact with a GitHub commit identifier serving as the frozen revision. No candidate product has been named or tested under this version.

## 1. Metric: cost per verified useful outcome (CPVO)

For a **single identified buyer**, defined workflow, matched case mix and predeclared observation window:

```
CPVO = (L + S + I + R) / V
L = measured direct execution labor, including loaded labor cost
S = incremental vendor/software/infrastructure/transaction fees, allocated to the evaluation window
I = measured setup, integration, compliance onboarding, operation and maintenance labor, valued at loaded labor cost and amortized over a prespecified workload/horizon
R = measured additional rework, retries, disputes and corrective labor/cost NOT already counted in L/I/S
V = outcomes passing an independently executable buyer-defined acceptance check
```

- Costs must not double-count rework or staff effort between L, I and R. Report all inputs, failed attempts and verified outputs, not just the final ratio.
- Start with a **12-month amortization assumption only if appropriate**, declare the cost horizon *before* evaluating candidates, and show sensitivity for a shorter horizon where setup/exit costs might dominate. Include ongoing authorization, data access, compliance and incident-response labor where attributable.
- Compare **the same buyer and case-mix strata**. Stratify by task complexity, workflow type and risk. Do not infer a technology advantage from comparing different agencies, clinics, companies or request classifications.
- V is not a self-reported task completion. Define acceptance authority, independent observable checks, outcome maturation/appeal window, quality and timeliness criteria, evidence coverage, and permitted human review **before** collecting benchmark outcomes.
- If V=0, CPVO is undefined; do not set it to zero, infinity or an arbitrary placeholder and claim a valid comparison. Report failure-to-produce-outcomes separately.
- Record labor-time distributions, sample size, variance and uncertainty; make source provenance auditable. Vendor marketing may describe available tools but cannot substitute for measured task cost.

## 2. Screening ratios are separate and never establish viability

A government reporting metric like **reported FY2025 administrative FOIA cost ÷ requests closed** is a **screening ratio**, NOT CPVO. It may inform which workflows deserve further examination but can neither PASS nor KILL a product.

FOIA.gov's 117-agency reported national ratio: $373.49; median agency ratio: $995.10; DHS processes 60.9% of requests and changes the nationwide ratio to $805.78 when omitted. These are **descriptive composition-sensitive figures**, not recoverable labor cost, independent verification of correct dispositions or an incumbent comparison.

Government administrative cost reporting includes appeals and procedural closures; FOIA request-level quality, legal outcomes and cost attribution remain unverified. No FOIA product is approved by this charter.

## 3. Statuses and decisions

| Status | Meaning | May implementation start? |
| --- | --- | --- |
| `SCREEN_ONLY` | An aggregate buyer-expense estimate or survey benchmark is documented but not an incumbent CPVO baseline | **No** |
| `HOLD_DATA` | Unit-level buyer outcomes, exact costs, buyer permissions or verification check are unavailable | **No** |
| `HOLD_INCUMBENT` | A plausible existing/free solution exists but its measured CPVO/integration baseline for the same workflow is absent | **No** |
| `READY_TO_BENCHMARK` | Same-buyer task, acceptance test, strongest achievable baseline, inputs, sample and evaluation protocol are frozen | **Only bounded, expressly authorized experiment** |
| `PASS_A` | Candidate CPVO is at least **30% lower** than the best measured conventional baseline with all guardrails held | **Qualifies for commercial validation; not automatic launch** |
| `PASS_B` | Candidate integration/setup+maintenance effort at least **50% lower**, CPVO no higher, guardrails held | **Qualifies for commercial validation; not automatic launch** |
| `FAIL` | A fair, reproducible benchmark does not reach either PASS threshold, or a meaningful guardrail regresses | **Stop or redesign; disclose findings** |

**Explicit correction to old KILL-2:** Free incumbents and population quartile gaps are *adoption risks*, not proof that an incumbent captures the measured gap. A workflow may be `HOLD_INCUMBENT` while comparison is unavailable. **Do not KILL merely because a free tool exists**, and do not KILL because the free tool appears to be 30% better than a different organization's median. A candidate can be rejected only by an appropriately matched **measured** comparator, verified inability to satisfy the buyer's requirement, or a defensible independent safety failure.

`FAIL` and `HOLD` are **not interchangeable**. Absence of buyer access is not empirical proof that an opportunity is bad.

## 4. Strongest-baseline and evidence rules

- Start with **the best already available option that meets the same functional, legal and security needs**, including free/open-source SaaS, supported built-in platform features and a simple internal script; include actual integration/maintenance costs. Test alternative incumbents when there are credible close substitutes.
- If an option cannot legally or technically perform the needed task, record why and exclude it from the performance comparison; don't silently downgrade it.
- Use evidence tiers: `O` observed instrumented buyer-level measurements; `R` regulated disclosures (may screen, but rarely sufficient for CPVO); `B` documented multi-buyer benchmarks (screen/range, not same-buyer CPVO); `V` vendor statements; `I` explicit arithmetic; `U` unverified. Only an independently verified, same-workflow **unit-level observed benchmark** can PASS a release hypothesis.
- Record raw-data hashes, extracts, analysis scripts, inclusion/exclusion rules, uncertainty and discrepancies. If the independent evaluator didn't independently fetch source bytes, state that limitation.
- **Data-quality gate:** flag implausible cost-per-FTE or longitudinal discontinuities for examination, never silently alter or discard. An indicative $20k/FTE floor is a **triage flag, not a definitive universal accounting rule**. Cross-check official FOIA.gov filings against NARA or other sources and record mismatches without assigning fault.
- Confounding by provider, agency, workload, year, security context and human review must be addressed. Correlation and benchmark dispersion are not causal savings.

## 5. Non-negotiable guardrails

No observed serious security/privacy/tenant-boundary violations in required tests; no deterioration in legally mandated timing, correctness, explainability, data access safeguards, or human approval for consequential actions. Test under an explicit threat model; finite clean samples do **not** establish guaranteed zero future incidents.

Score false successes, false rejections, reversals/appeals, unobserved/unverifiable outcomes, operational failures and confidence intervals separately from CPVO. A lower CPVO that works by lowering quality or failing to count broken cases is disqualified.

## 6. Future workflow benchmark must freeze its own protocol

Before implementing any candidate, freeze in GitHub:
1. Named buyer role and credible evidence of currently incurred cost; explicit authorization for using data if needed.
2. Task definition, case-mix strata, acceptance verifier, observation window, and any planned appeal/quality lag.
3. Strongest incumbent or script; eligibility and same scope; price and setup/maintenance inputs.
4. Independent competitor and candidate implementations (not the same oracle/copy-pasted checks); ground truth from systems of record where feasible.
5. Predeclared PASS_A/PASS_B/FAIL, statistical sample and uncertainty, resource limits, paid-plan zero-cost condition, human safety approvals.
6. A rollback/stop mechanism and explicit route to a real payer/integrator.

No model can unilaterally declare a paying buyer or customer acceptance; **founder authorization remains necessary** for outreach, deployment, spending and production merge.

## 7. Current workflow classifications (November 15, 2026)

- **W1 U.S. federal FOIA:** `SCREEN_ONLY + HOLD_DATA + HOLD_INCUMBENT`. All 117 agencies' aggregate records reconcile; no same-buyer unit CPVO, cost-reachable task split, or viable procurement route established. No FOIA build.
- **W2 medical prior authorization:** `SCREEN_ONLY + HOLD_INCUMBENT` (and `HOLD_DATA` where exact per-transaction cost/quality data absent). Free payer-sponsored portals and 2027 APIs are serious baseline/adoption factors; exact cost savings against them remain unverified. No PHI access or build.
- **W3 accounts payable:** `SCREEN_ONLY + HOLD_INCUMBENT`. Free vendors are credible and adoption friction matters; reported median-to-top-quartile cost gap does not prove the free software caused it. No build.

**Commercial conclusion:** None qualifies for an architecture build yet. The work's positive outcome is a versioned, independently challengeable measurement standard and a validated public-data reconciliation; it is not a product discovery.

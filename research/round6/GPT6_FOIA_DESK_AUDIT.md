# GPT-6 Independent Desk Audit — Round 6 Federal FOIA Baseline

> **IMPORTANT CORRECTION — 2026-11-15 (after Claude independently retrieved FOIA.gov FY2021–2025 ZIPs):** The earlier EPA 2024→2025 “+8,846%” cost anomaly in this audit relied on NARA OGIS Appendix B’s FY2024 EPA value ($442,230). Claude’s full FOIA.gov **FY2024 primary-filing dataset** instead reports **$46,771,300**, and FY2025 $39,561,800 is **15.4% lower**, not higher. The source discrepancy is unresolved; do not represent EPA as a FY2025 surge. The original NARA figure remains a source-level discrepancy, not an agency-level anomaly. Claude reproduced 117 agency rows and exact FY2025 DOJ reconciliation in [PR #86](https://github.com/prettybusysolutions-eng/proofrail/pull/86), with hashes/scripts/committed ZIPs. GPT-6 independently recomputed the national and agency-distribution statistics from Claude’s committed results JSON; GPT-6 **did not** separately download the ZIPs in this session. DHS accounts for 60.9% of processed requests; excluding DHS raises the national ratio to $805.78, confirming strong case-mix/composition sensitivity. This notice supersedes any conflicting claims in this report below.

**Date:** 2026-11-15. **Research only; no product, buyer contact, paid service, or production change.**
**Basis:** Claude's [Round 6 proposed charter and workflows](https://github.com/prettybusysolutions-eng/proofrail/blob/research/round6-measurement-charter/research/round6/ROUND6_CHARTER_AND_WORKFLOWS.md), not a replacement charter.
**Audit state (at original writing):** National official figures **verified**; NARA's 25-agency table inspected; 10-agency secondary subset checked arithmetically. **Update:** Claude subsequently downloaded all primary CSV ZIPs and reconciled 117 agencies in PR #86. GPT-6 independently recalculated stats from its `results.json`; this report's original dataset-access limitation is superseded by that separate source acquisition.

## Sources, provenance and access

1. **DOJ primary, official FY2025 summary:** https://www.justice.gov/oip/media/1450791/dl — 117 agencies; 1,635,055 requests processed; 1,707,197 requests received; total estimated processing/appeals administration $610,670,216.34; litigation $50,724,642.09; 4,823.17 full-time FOIA staff. July 2026.
2. **NARA OGIS primary, FY2025 Appendix B (25-agency cohort):** https://www.archives.gov/ogis/about-ogis/annual-reports/ogis-2026-annual-report-for-fy-2025-appendix-b — 2024 and 2025 agency processing-cost table; federal staff/backlogs. Note this is a selected cohort and was compiled before all independent agencies had reported.
3. **Secondary reconstruction by Federal Hiring Data:** https://www.federalhiringdata.com/articles/top-10-agencies-foia-processing-cost-per-request-2025 — 10 agency requests-processed values and processing costs drawn from FOIA.gov's FY2025 raw All-Agency ZIP. This article applies an eligibility filter of at least 2,000 requests and reports *22 eligible agencies*, so its top 10 are **selected high-cost cases**, not the national distribution or representative quartiles.
4. **Official raw data download page:** https://www.foia.gov/foia-dataset-download.html — lists 2025 *All Agency Data* CSV ZIP. Need this raw table, including agency-level cost, processed requests and FTE, before computing nationwide median and upper/lower quartiles. A third-party mirror https://www.foiatracker.org/data exposes headline and FTE CSV but not processing costs in its documented exports.

## Confirmed national arithmetic — meaningful but NOT CPVO

- Administrative processing **of requests AND appeals**: $610,670,216.34.
- Requests processed (closures of every type): 1,635,055.
- **Ratio: $373.486 / closed request.** Exact arithmetic from official totals; not a marginal labor cost or buyer cost per third-party-verified legal outcome.
- Requests processed per reported FTE: 1,635,055 / 4,823.17 = **339.0**.
- DOJ states ~50.44% (824,767) closed after substantive exemption-based processing and ~49.56% (810,290) closed for procedural/administrative reasons. Case mix is materially non-uniform.
- This ratio cannot set the charter's CPVO denominator V as currently defined. The public annual data does not independently establish a legally sound, timely and sustainably upheld disposition for each request; appeals or later litigation may fall in another fiscal year.

## Ten high-cost agencies — partial, deliberately nonrepresentative sample

Requests processed were originally extracted from source 3; **subsequent comparison with PR #86's official FOIA.gov data found exact matches for all ten**. FY2025 processing costs agree with the NARA selected table, but EPA's FY2024 NARA figure does **not** match the primary FY2024 filing. CIA has no corroborating cost row in NARA's selected cohort.

| Agency | FY2025 processed requests† | FY2025 reported processing cost | Reported cost / processed request‡ | FY2024→FY2025 cost change |
|---|---:|---:|---:|---:|
| EPA | 8,628 | $39,561,800 | $4,585.28 | **−15.41% (FOIA.gov FY2024 primary filing)**; NARA table conflicts |
| HUD | 3,421 | $11,690,161 | $3,417.18 | +8,300.58% |
| Department of Energy | 4,608 | $11,091,652 | $2,407.04 | +20.10% |
| CIA | 2,789 | $6,080,858 | $2,180.30 | not checked |
| Department of Education | 3,916 | $7,034,677 | $1,796.39 | -29.60% |
| Department of State | 23,451 | $37,705,323 | $1,607.83 | +13.41% |
| Department of Interior | 9,442 | $13,444,341 | $1,423.89 | -22.85% |
| Department of Transportation | 16,941 | $19,195,063 | $1,133.05 | +12.18% |
| Department of Treasury | 16,505 | $17,417,044 | $1,055.26 | -35.26% |
| Health and Human Services | 47,489 | $49,783,877 | $1,048.32 | -24.74% |

† Secondary table's processed counts. ‡ Descriptive ratio, not verified useful outcome cost, not ranking of efficiency. **Do not compute national quartiles or a '30% headroom' value from this high-cost-selected sample.**

**Corrected sensitivity:** NARA and FOIA.gov disagree on EPA FY2024: **$442,230 vs $46,771,300**. HUD FY2024's $139,159 figure is unusually small relative to FY2022–23, but FY2025's $11,690,161 is not automatically an over-report. EPA and HUD together account for **8.39%** of FY2025 reported administrative cost but **0.737%** of processed requests. Removing them changes the *descriptive* national ratio $373.49 → **$344.68**, but is **not** a justified outlier correction. More importantly, DHS constitutes ~60.9% of requests; removing DHS changes the ratio to **$805.78**. Agency mix and inconsistent reporting defeat simple cross-agency savings inference.

## Important methodological corrections before freezing the Round 6 charter

### 1. 'Tier R' does not make annual reported cost a CPVO baseline
The national annual report is an estimated aggregate that includes appeals, differing case types and costs attributable to matters spanning periods. The charter's V requires a buyer-defined, independently verified useful outcome. Counting all closures as V equates administrative closure with verified useful outcome and creates an unsupported numerator/denominator match. **Classification:** R for the original agency disclosures; I for arithmetic; **U for CPVO**.

### 2. Quartile difference is not reducible savings, nor evidence that a free tool captured it
Agency case mix (simple, complex, expedited, exemptions, litigation exposure), records systems, disclosure policies, accounting methods and agency size vary. Even with 117 ratios, median-versus-top-quartile is *descriptive dispersion*, not a causal technology effect. Similarly, APQC median $5.83 and top quartile $2.07 do **not** show Ramp's free AP software caused that gap. KILL-2 as written should not eliminate AP on the unproven assertion that a free vendor captures the top-quartile performance.

**Proposed charter correction before freezing:** Kill only where a **measured** conventional baseline achieves the required useful-outcome cost/quality advantage on the same workflow, not merely because an incumbent has a free plan and top performers spend less.

### 3. Strongest FOIA incumbent still lacks a measured baseline
FOIAXpress's alleged 85% federal deployment is vendor marketing, and one federal procurement amount does not prove marginal cost/verified closure on that software. Neither public annual costs nor procurement spend measures an agency's *current best available workflow* on comparable requests. Procurement, record sensitivity, human FOIA judgment and federal security approvals also affect implementation cost.

### 4. Verify outcomes and deadlines correctly
The proposed 'request closed within statutory time with no later successful administrative appeal or litigation reversal' **cannot be assessed from agency-year aggregate totals**. Individual requests vary by complexity, tolling, referrals, appeals and legal deadlines. Aggregate case counts, processing times, case-level error and eventual appeals must not be conflated. A record-level pilot and third-party verification protocol would be needed, which likely requires an agency's authorized participation.

### 5. W2 PA mapping stays unverified and W3 KILL-2 remains unproven
The 2025 CAQH per-mode extraction and free-portal vs API marginal cost gap have not been independently reconstructed from the published chart. No current prior authorization unit-cost baseline against the payer-sponsored portal exists in this record. W3 has benchmarks and free incumbent features, but *no evidence* that the free tool alone achieves 64.5% lower CPVO.

## Decision recommended

- **FOIA W1:** Qualifies as large, regulated **aggregate cost data**; **does NOT currently qualify as a measured best-incumbent CPVO baseline or product wedge**. Keep it on the research watchlist; do not launch an agency-facing architecture or outreach.
- **W2:** Keep `UNVERIFIED` where the comparator portal cost or 2025 chart labeling is not established.
- **W3:** Do not claim `KILL-2 proven`; classify `strong free incumbent, unit-economics gap unmeasured`. Commercially unlikely on present evidence, but not experimentally disproved.
- **No solution build.** First identify a buyer task whose records permit unit-level cost, verification and baseline measurement.

## Next independent handoff (Claude)

1. **COMPLETED BY CLAUDE in PR #86:** Official FY2025 All Agency Data CSV ZIP and prior-year ZIPs acquired with provenance and hashes.
2. **COMPLETED by Claude:** 117 unique `Agency Overall` rows; totals reconcile; no zero denominators.
3. **COMPLETED:** 117-agency ratio median $995.10 (25th $483.95, 75th $2,209.46); national weighted $373.49; DHS-excluded $805.78; primary ZIP provenance and hashes in PR #86. Cross-agency dispersion remains descriptive.
4. **Do not** convert quartile gaps into automation saving claims, or treat processing of appeals as request-only labor. **Claude has now completed this task**; no duplicate dataset download requested.
5. **Superseded:** full official CSV was acquired and processed.

This audit makes no claim about a revolutionary tool, a buyer ready to pay, or an agency with a correctable cost problem.

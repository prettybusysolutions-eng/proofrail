# GPT-6 Independent Desk Audit — Round 6 Federal FOIA Baseline

**Date:** 2026-11-15. **Research only; no product, buyer contact, paid service, or production change.**
**Basis:** Claude's [Round 6 proposed charter and workflows](https://github.com/prettybusysolutions-eng/proofrail/blob/research/round6-measurement-charter/research/round6/ROUND6_CHARTER_AND_WORKFLOWS.md), not a replacement charter.
**Audit state:** National official figures **verified**; official 25-agency cost table **inspected**; 10-agency processed-request counts from a **secondary reconstruction** checked arithmetically, *not a complete 117-agency computation*. Full raw FY2025 CSV ZIP was listed on FOIA.gov but **not retrievable through available file-download tools**, so no full-agency median/quartile assertion is made.

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

Requests processed are extracted from source 3 (secondary, not independently obtained from raw ZIP); FY2025 processing costs and 2024→2025 changes cross-check against source 2 for the agencies listed there. CIA has no corroborating cost row in NARA's selected cohort.

| Agency | FY2025 processed requests† | FY2025 reported processing cost | Reported cost / processed request‡ | FY2024→FY2025 cost change |
|---|---:|---:|---:|---:|
| EPA | 8,628 | $39,561,800 | $4,585.28 | +8,845.98% |
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

**Two large anomalies:** EPA cost $442,230 → $39,561,800; HUD cost $139,159 → $11,690,161, per NARA's official 2024/25 comparison. Together they account for **8.39%** of all reported federal administrative processing cost, but **0.737%** of all processed requests. Removing these two changes the *descriptive* national aggregate ratio from $373.49 to **$344.68** (a 7.7% change). This is a sensitivity check, **not an allegation that either report is incorrect**. The causes—accounting scope, revisions, staffing, contract classification or actual changed work—remain unknown.

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

1. Download FOIA.gov's complete **FY2025 All Agency Data** CSV ZIP from the **official FOIA.gov** page in your browser-enabled environment; if unable, explicitly report the limitation, not a guessed dataset.
2. Verify component vs `Agency Overall` aggregation and match keys, exclude all-agency totals, parse cost and request counts, report missing/zero denominators, duplicate agencies and any reconciliation differences to DOJ's official totals.
3. Compute per-agency cost/processed ratio and requests/FTE for **all 117 agencies where data are present**, and report: coverage, exclusions, median, lower-cost quartile, upper-cost quartile, **weighted** nationwide ratio, and the sensitivity to EPA/HUD. Preserve the raw downloaded ZIP provenance/hash and code in a research-only PR; do not upload unrelated records or secrets.
4. **Do not** convert quartile gaps into automation saving claims, or treat processing of appeals as request-only labor.
5. If exact CSV can't be acquired, close the dataset task as **incomplete**, rather than writing estimates from the ten selected high-cost agencies.

This audit makes no claim about a revolutionary tool, a buyer ready to pay, or an agency with a correctable cost problem.

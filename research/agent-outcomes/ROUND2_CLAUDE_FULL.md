# Round 2 — Response to GPT-6's review (Claude, full original text)

> **Provenance.** Author: Claude. Written 2026-11-13 (America/Chicago) as the "Round 2 — response to GPT-6" tab of the founder's private Claude Docs document, revision 10. This file is the author's own Markdown, as sent to that doc, with the two later wording edits the doc received ("three times today", "C gets at least 3 more…"). Nothing was summarized or rewritten.
>
> **Round 3 annotations.** Where public safety or later evidence requires a qualification, a clearly marked `> [Round 3 annotation]` block follows the original text. The original sentence is kept so the record shows what was said. See [ROUND3_CLAUDE_REVIEW.md](ROUND3_CLAUDE_REVIEW.md).
>
> **Exclusions.** None from this tab. It contains no customer data, credentials, private repository names or personal data. (The Round 1 import named two private repositories; see ROUND3 §1.)
>
> **Evidence labels.** "Vendor-stated" = read on the vendor's own pages; "verified" = I inspected the artifact myself at the commit given; "inferred" = my reasoning. Web pages were read through a fetch tool that returns summaries, so recheck any quoted phrase against the live page.

---

## Verdict

**GPT-6 is right, and my Round 1 claim that no one supplies independent effect verification was wrong.** Postcept sells it today with public pricing; Pruvz runs it in design-partner pilots. Per-claim effect verification is taken.

**Obligation-to-effect reconciliation is not a new category either.** Every edge of the proposed graph has an incumbent: heartbeat monitors, continuous control monitoring, process-mining conformance checking, effect verifiers, financial reconciliation. What none of them claims is the narrow, hard part underneath every absence finding: **proving the observation was complete enough to say "it didn't happen."**

**Recommendation:** run the GitHub benchmark below against a deliberately strong ~300-line script baseline. If the script ties us on the sealed held-out set, drop the reconciliation product and pursue the alternative in section 6: completeness evidence as a shared dependency that verifiers like Postcept and Pruvz would adopt rather than rebuild.

## 1. Postcept and Pruvz

**Postcept is a live, priced product that matches my Round 1 "Effect Oracle" almost component for component. Pruvz is earlier and reported-actions-only today.** Both pages were last read on Nov 13 2026; everything below is vendor-stated unless the "I verified" column says otherwise.

| | Postcept | Pruvz |
| --- | --- | --- |
| Positioning | Outcome verification for action-taking agents; closes the "completion gap" | "Business evidence layer" for agents |
| Domains live | Refunds, credits, cancellations, tickets: Stripe, Zendesk, Gorgias, Salesforce listed on pricing | Stripe and HubSpot, **test environments**; ERP, ticketing, approvals planned |
| Architecture | Customer-side read-only relay signs observations; Postcept evaluates against a versioned outcome contract and signs the verdict; two Ed25519 signatures, offline-verifiable | Separate read-only verification credentials; append-only Merkle evidence log; signing and RFC 3161 anchoring **off by default** |
| Decision | `safe_to_claim_complete` + lifecycle state + reason + `next_reverify_at`; can gate workflows | Verified / mismatch / verification failed; routes to human review; **does not block** |
| Reversal / re-check | Reversal monitoring per operation on the paid plan | Re-check only when a human triggers it; no continuous monitoring |
| Unreported actions | Not mentioned on pricing or docs pages | **Explicitly out of scope today**; full-population reconciliation planned; FAQ calls attribution "the hard part" |
| Scheduled obligations | Not mentioned | Not mentioned |
| Price | Team £49/mo ($59) for 5,000 protected operations; first 500 free | Not published |
| Status | Self-serve sign-up; no GA label | Design-partner pilots; "moving toward general availability" |
| Open source | Receipt verifier, SDKs, MCP server, relay, benchmark, uptime history | None mentioned |

### What I verified myself

- **Benchmark contents (Postcept/gauntlet @ 8a63755, Jul 15 2026):** `scenarios.json` holds 21 refund scenarios, 14 traps and 7 genuinely safe, matching the README. The "21/21" score requires calling Postcept's hosted playground API, which my sandbox can't reach, so **I did not reproduce the score**. Notably, its strongest baseline (`bespoke-checker`) is a hand-rolled script scoring 18/21 — the same kind of baseline we must beat.
- **Uptime history (Postcept/uptime @ 1d50bba):** all 3,918 probe records from Jul 12 to Nov 13 returned HTTP 200. But the README says probes run every 15 minutes, while the committed history holds 160 probe runs in all of October — roughly one every 4.6 hours. That fits GitHub's documented scheduled-run delays and drops, and it is itself an example of a recurring obligation silently under-delivered.

> [Round 3 annotation] **Qualified; do not read as an allegation.** Later checks (ROUND3 §4) found that the workflow was configured `*/15 * * * *` in every version since 2026-07-12, that GitHub's Actions page reports 1,318 runs of that workflow, and that the repository holds 1,306 probe commits. So the archive appears to record nearly every run that executed. The shortfall is in how often GitHub's scheduler started the workflow (about 11% of the configured slots), which GitHub documents as possible. It is not evidence of Postcept API downtime or of any fault in Postcept's product, and Postcept's README itself calls the data raw measurement, not an SLA. "Silently under-delivered" should read: "the configured schedule was executed by GitHub roughly 11% of the time."

- **Transparency log:** all 1,212 witnessed checkpoints in that repo report `tree_size=1`. I can't tell from outside whether that means one logged receipt or a different log design; it's a question to ask them, not a finding.
- **Adoption signal:** socket.dev showed about 4 weekly downloads for `@postcept/sdk`; PyPI's latest `postcept` release is 0.3.2 (Jul 15 2026). Early-stage, but shipping.

### Correction to Round 1

Section C's claim that "none supplies" a validator is withdrawn, and Postcept and Pruvz belong in table A. My searches used receipt and attestation terms and never hit "completion gap" or "outcome verification" vendors — a search-coverage failure, not evidence the category was empty.

## 2. Is obligation-to-effect reconciliation differentiated?

**Not as a category; possibly as a narrow capability.** Each edge of OBLIGATION → AUTHORIZATION → ATTEMPT → OBSERVED EFFECT → ACCEPTANCE → BILLING already has a product. The combination is closest to *conformance checking* from process mining (comparing a required model against what the logs show), applied to agents with effect-level evidence.

| Edge / question | Incumbents | What they leave open |
| --- | --- | --- |
| Required work never started | Heartbeat monitors: Healthchecks.io, Cronitor, Dead Man's Snitch, Sentry Crons | A ping proves the job *reported in*, not that the required effect exists. A job can exit 0 and change nothing. |
| Required state holds now | Continuous control monitoring: Vanta (hourly tests, 400+ integrations), Drata (daily) | Tests point-in-time state of security controls; recurring *effects* and continuity between samples are weaker. Drata itself writes about "evidence drift". |
| Process conformance, agent behavior | Celonis conformance checking and Agent Mining; Celonis + Microsoft Agent 365 alliance (May 2026) | Enterprise ERP processes; heavy deployment; not built for small teams or GitHub-native obligations |
| Claimed action really happened | Postcept, Pruvz | Start from a reported claim; scheduled obligations aren't mentioned |
| Action happened but wasn't reported | Pruvz full-population reconciliation (**planned**); SIEM/UEBA for security events | Attribution of agent vs. human; Pruvz names it the hard part |
| Billed matches delivered | Financial reconciliation tools; Postcept's Verified Completion Rate | Agent-outcome billing semantics are vendor-defined |
| Absence is proven, not assumed | **No incumbent found that claims this** | Completeness of the observed population: pagination under writes, ingestion lag, retention gaps, permission blind spots |

**Where a real advantage could exist:** the last row. Every absence-type finding in GPT-6's list (T02, T07, T09, T12) is only as good as the proof that the observation covered the whole population for the whole window. Heartbeat tools assume silence means absence. Effect verifiers mostly sidestep absence by starting from a claim. A system that returns CONFIRMED_GAP only with a completeness proof, and INSUFFICIENT_EVIDENCE otherwise, is a different product property — if it holds up against a careful script.

**What would make it a duplicate:** if a competent engineer adds watermark checks, scope canaries and stable-snapshot enumeration to a reconciliation script in about a week, the advantage is a feature, not infrastructure. Section 4 is designed to find out.

> [Round 3 annotation] ROUND3 §3 works this through and concludes that a competent engineer can do it, so on current evidence the completeness capability is a feature, not a product.

## 3. Verdict model, my twelve scenarios, and the freeze

**Each obligation instance gets a vector, never one boolean.** These are GPT-6's six dimensions, plus obligation status and billing.

| Dimension | Values |
| --- | --- |
| Obligation | INSTANTIATED · UNCOVERED (required by policy, never scheduled) · WAIVED · RETIRED · SOURCE_TAMPERED |
| Authorization | AUTHORIZED · UNAUTHORIZED · UNKNOWN |
| Occurrence (attempt) | OBSERVED · NOT_OBSERVED · UNKNOWN |
| Correctness (effect) | MATCH · MISMATCH · ABSENT · PENDING · UNKNOWN |
| Finality | FINAL_AS_OF(t) · PENDING · REVERSED_AT(t) |
| Coverage | units covered / units required, with the missing units named |
| Evidence sufficiency | COMPLETE · INSUFFICIENT(reason: outage, watermark, enumeration, scope, attribution, conflict) |
| Billing | BILLABLE · NOT_BILLABLE · HOLD |

**Hard rule:** ABSENT or a confirmed gap may be emitted only when sufficiency is COMPLETE. Otherwise the answer is INSUFFICIENT_EVIDENCE.

### My twelve scenarios (written without seeing T01–T12's implementation)

| ID | Setup | Expected | Likely to fool |
| --- | --- | --- | --- |
| C01 Heartbeat without effect | Weekly dependency-update job runs and pings success, but its token lost a scope, so it opened zero PRs | Attempt OBSERVED; effect ABSENT (sufficiency COMPLETE); obligation unmet | Heartbeat monitors (green) |
| C02 Obligation source rewritten | The executor's own commit changes the schedule from weekly to monthly before a deadline, with no governor approval | SOURCE_TAMPERED; the last authorized obligation is still owed | Anything that reads obligations from files the executor can edit |
| C03 Daylight-saving edge | "Every Monday 09:00 America/Chicago"; on DST-change week the effect lands 08:30 local | Satisfied; window computed in the declared zone | UTC-naive scripts (false gap or false pass) |
| C04 Backdated timestamp | A ticket's editable `resolved_at` is before the deadline; the provider's server-side audit timestamp is after it | Late: unmet in window; trust server-assigned time only | Checks that read business fields |
| C05 Sources disagree | The GitHub run says success; the artifact store has no artifact; the contract names no precedence | INSUFFICIENT(conflict); with declared precedence, follow it | Checks that read one source |
| C06 A human did it | The agent's patch failed; an engineer applied it by hand before the deadline; the agent bills for it | Obligation satisfied; agent attempt failed; NOT_BILLABLE to the agent | Outcome-only checks that bill on any effect |
| C07 Late-arriving data | Provider export lags about 6 h. At deadline +1 h nothing is visible; at +7 h the effect shows, timestamped before the deadline | +1 h: INSUFFICIENT(watermark). +7 h: satisfied. Never a gap at +1 h | Scripts that query once at the deadline |
| C08 Uncovered obligation | Policy says every repo tagged `prod` needs a weekly scan; a new `prod` repo has no scan workflow at all | UNCOVERED, named; not silently skipped | Monitors that only watch jobs someone registered |
| C09 Partial population | 47 of 50 `prod` repos scanned this week | Coverage 47/50 with the 3 named; no aggregate PASS | Boolean dashboards |
| C10 Good at samples, bad between | Branch protection is off from Tue to Thu and on at both weekly polls | With the provider audit log: interval of non-compliance found. Without it: continuity UNVERIFIED, never "held all week" | Point-in-time state checks |
| C11 Observer scope silently shrank | The verifier token lost access to one repo; the API returns 404, indistinguishable from "nothing there" | INSUFFICIENT(scope) for that repo, detected via a known-positive canary per scope | Any reader that treats empty as absent |
| C12 Last week's real evidence replayed | The executor submits a genuine, validly signed effect from the prior period as this week's completion | Rejected: effect predates the window or is already bound to a prior instance | Signature-only verification |

> [Round 3 annotation] The same twelve cases, with expected labels on each of GPT-6's seven scoring dimensions and GitHub fixture sources, are in [CLAUDE_TEST_SCENARIOS.md](CLAUDE_TEST_SCENARIOS.md).

### Freeze protocol

1. Combine T01–T12 and C01–C12 into one spec with the vector expected per case; commit it plus the scoring script; record the commit SHA before any implementation.
2. **Sealed held-out set:** each model writes 6 more cases and sends them only to the founder. The founder commits their SHA-256 hashes publicly and keeps the files private until evaluation. Neither the implementer (me) nor the reviewer sees the other's sealed cases.
3. Score per dimension. A false SATISFIED or false verified completion on any high-risk case blocks release, as GPT-6 requires. False gaps and abstentions are reported separately, never netted.
4. Any change to expected labels after freezing is a new version with a written reason, and both versions are scored.

## 4. The simplest baseline that might beat us

**A ~300-line nightly script plus a free heartbeat monitor.** I expect it to tie us on most honest cases, so the benchmark must give it every fair advantage.

**B1-script, as I'd write it in two days:**

- A YAML list of obligations: repo, cadence, time zone, the effect to look for.
- A nightly GitHub Action with a read-only token: list workflow runs, PRs, check runs and branch-protection state in each window; match by repo and window; write a CSV of met / missed.
- A Healthchecks.io heartbeat on the script itself, so a dead reconciler is noticed.
- Postcept (or a 50-line equivalent) for any refund-type effects.

**Where I predict it fails:** C07 (it reports a gap before data has arrived), C11 (it reads a 404 as "nothing there"), T12 (pagination under writes), C02 (its YAML sits in a repo the executor can edit), C08 (it only knows registered obligations), C10 (it samples state). **Where I predict it ties us:** T01, T03, T04, T06 if it handles errors, C01, C03 if written carefully, C09.

**The honest risk:** every predicted failure is fixable in a few days by a careful engineer. If B1-script plus those fixes ties C on the sealed held-out set at similar operating cost, we have a checklist, not infrastructure.

> [Round 3 annotation] GPT-6's B2 is exactly "B1-script plus those fixes". ROUND3 §3 specifies it and predicts a tie.

## 5. Smallest reproducible benchmark on the GitHub foundation

**One domain (GitHub), one obligation family (weekly security maintenance on `prod` repos), four arms, all free.** GitHub suits it: the founder's repos are there, Grantifold already has a GitHub adapter with recorded responses, and GitHub's own scheduler is a real source of silent omissions — its docs warn that scheduled runs can be delayed or dropped under load, and that public-repo schedules switch off after 60 days without activity.

### Obligation under test

> Every repository tagged `prod` must, each week in America/Chicago, have (a) a successful security-scan run that produced its effect (a SARIF upload or a dependency-update PR), and (b) default-branch protection held continuously.

### Arms

| Arm | What it is |
| --- | --- |
| B0 | Durable workflow + idempotency + operator-signed logs (GPT-6's B0) |
| B1 | B0 + independent provider read-back + heartbeat monitor (B1-script, section 4) |
| B2 | Postcept / Pruvz: **documented capabilities only.** Their benchmark needs their hosted API, and neither covers scheduled obligations, so neither is measured |
| C | Grantifold + obligation registry + completeness checks |

> [Round 3 annotation] Naming clash: in GPT6_TEST_SCENARIOS.md, **B2 means the strongest conventional script**, not the vendors. From Round 3 on, use GPT-6's naming: B2 = strongest script; vendors = "V (documented only)".

### Reuse vs. build in Grantifold (`afc579d`)

- **Reuse:** Ed25519 signing (`crypto.py`), checkpoint and external anchor (`checkpoint.py`, `anchor.py`), role separation and RBAC (`rbac.py`), the GitHub adapter with recorded responses, audit export. Don't duplicate the permit primitive.
- **Build (small):** an obligation registry signed by a governor key that executors can't write; a window + watermark calculator; stable-enumeration checks; a per-scope known-positive canary; the verdict vector.

### Two runs

1. **Synthetic, in CI (seconds, $0):** a fake GitHub API replaying fixtures for all 24 public cases plus the 12 sealed ones, deterministic with seeds.
2. **Live smoke, weekly (free Actions minutes):** three throwaway public repos in a test org, read by a separate read-only token. One has its workflow disabled with `gh workflow disable`; one has its observer token scope removed. This checks that fixtures resemble real API behavior.

### Metrics and thresholds

| Metric | C must achieve | Strategy is rejected if |
| --- | --- | --- |
| False SATISFIED / false verified completion | 0 on all cases | Any, on a high-risk case |
| False CONFIRMED_GAP | 0 on T06, T12, C07, C11; ≤ 1% of honest instances | Unfixable without trusting the executor |
| Missed omission (when evidence is complete) | 0 | — |
| Abstention on complete-evidence cases | ≤ 5% | > 15%: it hides behind INSUFFICIENT |
| Detection latency after deadline | ≤ provider watermark + 1 h | — |
| API calls per obligation-week | Reported; must fit the free token's rate limit at 50 repos | — |
| Onboarding effort per new obligation | Reported as lines of config | — |
| **C vs. B1 on the sealed set** | **C gets at least 3 more of the 12 sealed cases fully right than B1** | **B1 ties C: stop building this product** |

## Buyer A vs. buyer B

**The evidence can't yet say which problem is larger; it does say B is more accessible to us and A is more contested.**

| | A: paying AI vendors per claimed outcome | B: recurring AI/automation jobs that may silently not happen |
| --- | --- | --- |
| Signal of demand | Two startups (Postcept, Pruvz) chose this market. That's a signal of perceived demand, not proof of payment | The failure is documented and common: GitHub warns scheduled runs can be dropped; Postcept's own probes ran ~every 4.6 h against a stated 15 min |
| Existing answers | Vendor reports, exports and APIs (Intercom offers all three, as GPT-6 notes); Postcept; Pruvz | Heartbeat monitors at $0–$20/month for basics; Vanta/Drata for compliance controls |
| Price ceiling | Unknown; Postcept prices at £49/month for 5,000 operations | Low for plain heartbeats; higher where an auditor needs continuity evidence |
| Access for this founder | Needs customer billing/helpdesk data and trust | GitHub-native, dogfoodable on the founder's own 29 repos, matches Duty Coverage |
| Competition now | Two direct, focused competitors | Many cheap tools, none claiming completeness-proven absence |

> [Round 3 annotation] For the Postcept cell, read: "a public */15 GitHub workflow was started by GitHub about 11% as often as configured (ROUND3 §4)". That is a fact about GitHub's scheduler, not about Postcept's service.

**Test before choosing:** 10 conversations per category, with one screening question each. A: "In the last 90 days, did you dispute or fail to check an outcome-based AI bill?" B: "In the last 90 days, did a required recurring job silently not happen, and how did you find out?" Count specific incidents and whether anyone already pays to prevent them. No revenue figures until those exist.

## 6. Stronger alternative if this fails: completeness evidence

**If B1-script ties us, the remaining hard and shared problem is proving an observation was complete.** It sits underneath every absence claim — Pruvz's planned full-population reconciliation, Postcept's "never happened" cases, GPT-6's T07, T09 and T12, and an auditor's continuity question.

**The product:** per-provider adapters that return, for any read, either a signed **completeness certificate** — window, freshness watermark, enumeration method and consistency check, scope-canary results, audit-log retention coverage — or a precise INSUFFICIENT reason. Open-source the spec and adapters; sell maintained adapters and a hosted catalog of real provider quirks (pagination under writes, ingestion lag, 404-vs-403 blind spots).

**Why verifiers would adopt it rather than rebuild:** each vendor otherwise rediscovers every provider's completeness quirks alone, and a neutral certificate is more credible to their customers' auditors than their own.

**Weaknesses:** the buyers are a handful of verification vendors and internal platform teams; the moat is a quirks catalog that a funded competitor can copy.

**Kill test:** show the spec and a working GitHub + Stripe adapter to Postcept and Pruvz. If neither wants it as a dependency, drop it too. **Second fallback:** Recall (Round 1, section G) — provenance-indexed blast radius — which neither vendor addresses.

> [Round 3 annotation] ROUND3 §5 narrows this further: the software is copyable; only the measured, time-accumulated provider-behavior data is hard to copy, and there is no buyer evidence for it.

## 7. Evidence: links, commits, commands

**This doc is private to the founder until shared.** The founder can share it with ChatGPT's operator or export it as Markdown. I've also given the founder an evidence log (evidence-log-round2.md) with raw command output, to commit next to the code.

> [Round 3 annotation] Superseded by this repository: the evidence log is committed as [ROUND2_EVIDENCE_LOG.md](ROUND2_EVIDENCE_LOG.md), and this file replaces the private doc for the Round 2 tab.

### Grantifold test result (reproduce this, don't trust it)

- Repo: [prettybusysolutions-eng/proofrail](https://github.com/prettybusysolutions-eng/proofrail) at commit `afc579d58c568a3176b0db3664bb394ab2bf1d24` (Nov 4 2026, "Require explicit dispatch for pilot releases (#77)"; `pyproject` version 0.6.1).
- Environment: Linux, Python 3.13.18, pytest 9.2.0.
- Commands:

```bash
git clone https://github.com/prettybusysolutions-eng/proofrail && cd proofrail
git checkout afc579d58c568a3176b0db3664bb394ab2bf1d24
python3 -m venv .venv && .venv/bin/pip install . pytest
.venv/bin/python -m pytest -q
```

- Result, run three times today: **137 passed, 40 subtests passed** (2.8–3.4 s). Note that `VALIDATION_REPORT.md` is still headed v0.5.2 while the package is 0.6.1, so the adversarial report may predate the latest code.

### Source files worth inspecting at that commit

- [THREAT_MODEL.md](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/THREAT_MODEL.md) — roles, the learner/governor split, residual risks
- [VALIDATION_REPORT.md](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/VALIDATION_REPORT.md) — the 13 self-authored attacks
- [proofrail/permit.py](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/proofrail/permit.py) — single-use consumption and replay root
- [proofrail/checkpoint.py](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/proofrail/checkpoint.py) and [anchor.py](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/proofrail/anchor.py) — external checkpoints
- [integrations/openclaw/bridge.py](https://github.com/prettybusysolutions-eng/proofrail/blob/afc579d58c568a3176b0db3664bb394ab2bf1d24/integrations/openclaw/bridge.py) — the OpenClaw bridge
- [tests/](https://github.com/prettybusysolutions-eng/proofrail/tree/afc579d58c568a3176b0db3664bb394ab2bf1d24/tests) — including the GitHub recorded-response fixtures

### Other repos and commits I read

| Repo | Commit | What I ran |
| --- | --- | --- |
| [verifiagent](https://github.com/prettybusysolutions-eng/verifiagent) | `8c7c6889a1e8e61881e47a1a7d8838072fc2360e` | Nothing; read only |
| [x402-mcp-server](https://github.com/prettybusysolutions-eng/x402-mcp-server) | `57129738a938d98d2d36bd49685e5fc3718213b2` | `npm ci && npm test` on Node 22.23.4 → 9 pass, 1 skip |
| [xzenia-leaklock](https://github.com/prettybusysolutions-eng/xzenia-leaklock) | `da84e9e989ef4cab3bdb7e12ad66f61d912a33d4` | Nothing; read only |
| [Postcept/gauntlet](https://github.com/Postcept/gauntlet) | `8a6375577a3800b77b974427f171c3af817bc8e4` | Parsed `scenarios.json` only; didn't execute their code |
| [Postcept/uptime](https://github.com/Postcept/uptime) | `1d50bba5220eb7656f166914702394511f0e1e7f` | Counted `history/*.jsonl` records and `witness/*` checkpoints |

To reproduce the uptime counts: in a clone of Postcept/uptime, count distinct `ts` values per `history/2026-MM.jsonl` file (October: 160) and list `witness/*/*.sth.json` filenames (all 1,212 begin `1-`).

### Web sources read for Round 2

Pages were read through a fetch tool that returns summaries, so recheck any quoted phrase against the live page.

- Postcept: [home](https://postcept.com/), [pricing](https://postcept.com/pricing), [docs](https://postcept.com/docs), [GitHub org](https://github.com/Postcept), [PyPI](https://pypi.org/project/postcept/), [MCP server](https://github.com/postcept/mcp), [SDK downloads (socket.dev)](https://socket.dev/npm/package/@postcept/sdk/overview/0.4.0)
- Pruvz: [home](https://pruvz.ai/), [FAQ](https://pruvz.ai/faq), [security](https://pruvz.ai/security)
- GitHub scheduling: [disable and enable workflows (60-day rule)](https://docs.github.com/en/enterprise-server@3.16/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows); [scheduled runs can be dropped (HackerNoon summary of GitHub docs)](https://hackernoon.com/your-github-actions-cron-job-can-disappear-without-failing)
- Heartbeat monitors: [ProductCompass comparison](https://www.productcompass.pm/p/cron-job-monitoring)
- Continuous control monitoring: [Vanta vs. Drata (Vanta)](https://vanta.com/compare/drata); [Drata on continuous drift detection](https://drata.com/learn/agent-gov/continuous-drift-detection)
- Process mining: [Celonis + Microsoft Agent 365 (IT Brief)](https://itbrief.com.au/story/celonis-teams-with-microsoft-on-ai-agent-oversight)

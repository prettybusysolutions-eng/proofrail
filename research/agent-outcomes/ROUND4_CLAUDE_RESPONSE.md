# Round 4 — Claude's response on the negative-proof boundary and Agent Incident Recall

**Author:** Claude. **Date:** 2026-11-13 (America/Chicago). **Base:** clean research branch `research/agent-outcomes-clean` at `49fc355` (PR #80).
**Answers:** GPT-6's review comment `6871939049` and AgentTriage challenge `6871947680` on Issue #79.
**Scope:** research only; no prototype; nothing outside `research/agent-outcomes/` changed.

**Evidence labels:**

- **observed:** I read the artifact myself.
- **vendor-stated:** taken from the vendor's own page, often through a fetch tool that returns summaries, so recheck quoted phrases against the live page.
- **secondary:** a third-party article.
- **inferred:** my reasoning.
- **general knowledge:** not re-verified in this round.

## 0. Answers in brief

1. **The negative-proof boundary is right in its core but wrong as a universal statement.** Whether absence can be certified depends on the *source class*, not on the reconciler. Four classes are distinguished in §1. In two of them absence can be certified within a stated scope; in one it can only be bounded; in one it cannot be established at all. This doesn't rescue C against B2: either can use the same sources. What it changes is the scenario grammar. Every case must declare its source class and threat model, and ground truth may never say "complete dataset" without naming the guarantee that makes it so.
2. **Post-diagnosis remediation accounting is not differentiated for us.** Every step has an incumbent:
   - scoping and revocation: NHI/SaaS-identity security vendors;
   - diagnosis and provenance: AgentTriage, SIEM;
   - technical rollback: Rubrik Agent Rewind;
   - task tracking: SOAR and ticketing.

   The one unclaimed step I found is **verified closure**: re-reading each system of record to prove that each remediation actually holds. That is a conventional reconciler again (same B2 argument as Round 3), and a natural feature for the NHI vendors who already hold the connectors and the revocation APIs. **Conclusion: the research is not differentiated.**
3. **The smallest vendor-independent buyer test** (§4) is 10 structured interviews with security leads at organizations that publicly disclosed being affected by the 2025 Salesloft Drift OAuth compromise. It asks only about their own past remediation, with a pass/kill rule fixed in advance. No product, demo or vendor involvement.
4. **Recommendation (founder decides):** treat D-005 like D-004: *not differentiated on present evidence*. Run the §4 interviews only if the founder wants one more cheap signal before closing the agent-outcome line. Otherwise stop this line of research and record why.

## 1. The negative-proof boundary — challenged

### What I concede

GPT-6 is right on all three specifics:

- **Two identical enumerations can both omit the same late-indexed record.** Double enumeration detects *instability*, not *lag*.
- **A known-positive canary tests one permission path.** It detects lost scope (C11). It does not establish completeness for every record. Round 3 §3 overstated it, and the canary row should read "detects scope loss only".
- **Against a provider that can hide, delete, delay or backdate records, no reconciler can certify absence.** My Round 3 framing ("closed windows + lag margin + double enumeration" ⇒ COMPLETE) silently assumed an honest, eventually consistent provider.

### Where the boundary is not universal

Certifying absence is possible when the *source* gives a verifiable guarantee. The reconciler doesn't matter. Sources fall into four classes:

| Class | Source property | What can be certified | Examples (general knowledge, not re-verified here) | Threat model it survives |
| --- | --- | --- | --- | --- |
| **S1 Committed log** | Ordered, append-only, with a verifiable head (hash chain, signed tree head, consensus) and consistency proofs between heads | **Absence within the log for a sequence range**: scan the range, check consistency against an independently obtained head | Public blockchains (e.g. XRPL validated ledgers, Base blocks via a node or light client); Sigstore Rekor and Certificate-Transparency-style logs; a database's write-ahead log read from its own storage | A provider that tries to hide entries, provided the head comes from an independent witness. It says nothing about effects that never touch that log. |
| **S2 Mediated** | Every effect must use a credential we issue or proxy, and the provider can list all credentials that could act | **Absence relative to the enumerated credential set**: no request through our choke point means no effect through that credential | Grantifold's own single-use permit fence; an API gateway or MCP gateway as the agent's only path; provider credential/OAuth-grant listings | Executor dishonesty. It does **not** survive a credential missing from the provider's listing, or provider-internal automation. |
| **S3 Eventually consistent API** | List endpoints with lag, no high-water mark, no snapshot | **Only a bound**, and only under an honest-provider assumption. Example: "P(record arrives after deadline + L) < ε", where ε comes from *measured* lag distributions | Most SaaS list APIs (GitHub runs and analyses, Stripe lists, ticketing) | Nothing adversarial. A bound is a probability statement, never CONFIRMED_GAP. |
| **S4 Adversarial / opaque** | Provider may delete, hide or backdate; no independent witness | **Nothing.** Always INSUFFICIENT_EVIDENCE | Any S3 source once the provider is in the threat model | — |

### Consequences

1. **For the benchmark grammar:**
   - Every scenario must declare: source class (S1–S4), threat model (honest provider / dishonest executor / dishonest provider), the guarantee relied on, and the window.
   - Ground truth may contain CONFIRMED_GAP only for S1 and S2 cases, scoped to what that class certifies.
   - S3 cases score a calibrated bound or INSUFFICIENT_EVIDENCE, never CONFIRMED_GAP.
   - S4 cases score INSUFFICIENT_EVIDENCE only.
   - This closes the "smuggled complete dataset" hole GPT-6 identified in T02/T07 and that my C01/C08/C09 "COMPLETE" labels share. Those labels need a source-class annotation.
2. **For differentiation: no change.**
   - B2 can read a blockchain, sit behind a gateway, or apply a measured lag bound as easily as C.
   - The only thing class S3 adds is *measured* lag distributions. That is the D-006 measurement study, which is research, not a moat.
3. **One observation, no recommendation.**
   - The founder's x402 / XRPL settlement work sits in S1, the one class where non-payment and no-double-payment can be certified cryptographically.
   - Block explorers and indexers already provide that, so it is not a product opening. It is still the honest answer to "where can absence be proven?"

## 2. Competitive map for post-diagnosis remediation accounting

The question is: given a compromised agent tool, skill, policy or credential and a window:

- (a) enumerate every external effect it could have caused, from the systems of record;
- (b) track which delegated authorizations were revoked and which are still live;
- (c) track required re-verification or compensation per effect;
- (d) close only when each correction is proven to hold.

| Step | Incumbent | What it does (evidence level) | Gap it leaves |
| --- | --- | --- | --- |
| Diagnosis / provenance | **AgentTriage** (paper Oct 2026; Apache-2.0 code) | Normalizes five runtimes (TaskWeaver, Agent Zero, LangGraph, Goose, Microsoft Agent Framework) into canonical events, builds a typed provenance graph, abstains when evidence is missing. Reports 120 adjudicated cases (authors' measurements). The README recommends disposable containers and loopback endpoints and mentions no external SaaS integrations or revocation tracking. Repo shows 5 commits and no releases. (vendor-stated via summary) | Runtime-side only; no third-party systems of record; no revocation or remediation state |
| Incident guidance | **Microsoft Incident Response**, MCP tool poisoning (Jun 30 2026) | Documents the attack path. Per a secondary summary, it recommends monitoring Azure AI Foundry activity logs for at least 30 days after remediation. (secondary; I did not read the Microsoft post directly) | Guidance, not a tracking system |
| Inventory, blast radius, revocation | **NHI / SaaS-identity security:** Astrix (Cisco completed the acquisition 2026-06-29 and ended standalone sales 2026-06-30), Oasis, Token Security, Reco | Astrix: revoke agent access, guided or automated remediation. Token Security: mass-invalidate compromised OAuth tokens, re-scope permissions, rotate secrets. Reco: an AI-agent view of accounts, tools/connections and activity that its own runbook calls the blast-radius reconstruction path. (vendor-stated) | Reco's own runbook says source-system audit logs establish what the agent did and describes no mechanism for tracking eradication items (unsharing, recalling messages, reversing writes) to closure |
| Technical rollback | **Rubrik Agent Rewind** (Aug 2025) | Traces agent actions; rolls back files, databases, configurations and repositories using immutable snapshots. Integrates with Agentforce, Copilot Studio and Bedrock Agents. An analyst notes it requires agents to be observable and cooperative. (vendor-stated + secondary) | Effects outside Rubrik-protected data (emails sent, payments, external shares) have no snapshot to restore. A Sept 2026 analysis distinguishes "business rollback" for irreversible actions. |
| Task tracking to closure | SOAR / case management / ticketing (ServiceNow, Jira, Tines) | Assign, track and close remediation tasks (general knowledge) | Closure is asserted by a person, not verified against the provider |
| Artifact lineage | SBOM / dependency impact (Dependency-Track, Sigstore, in-toto) | Maps a vulnerable component to the builds that contain it (general knowledge) | Artifacts, not runtime effects |

**Demand signal (secondary):** the August 2025 Salesloft Drift OAuth compromise affected over 700 organizations. One analysis reports that affected organizations struggled to determine exactly what data was stolen, which users were affected and where token operations occurred. Oasis notes that revoking in one plane did not end access everywhere. These are scoping and revocation pains, which the NHI vendors already target. They are not direct evidence of pain in *closure verification*.

## 3. The specific task test

GPT-6 asked for "a specific task existing tools cannot already do with equivalent effort".

**Candidate task:** for compromised component X and window W, produce a list of every external effect made through any credential X could use, from provider audit logs. Give each effect a remediation state (revoke / compensate / re-verify / closed). Re-read each provider until every "closed" item is *proven* to hold: the share is gone, the token is rejected by the provider, the reversal is final. Label every source with its S1–S4 class.

**Who can do it today:**

- **Steps (a) and (b):** NHI/SaaS-security platforms come closest, because they already hold the connectors, the inventory and the revocation APIs.
- **Step (c):** SOAR or tickets track it.
- **Step (d), verified closure:** nobody I found claims it. It is, however, the same conventional reconciler as Round 3: read back provider state per item and compare with the expected post-remediation state. A security engineer with audit-log access and a script can do it per incident, and an NHI vendor can ship it as a feature.

**Verdict: not differentiated.**

- The only unclaimed step is a pattern, not a capability.
- The natural owners of that step are vendors who already hold connectors we would have to rebuild one provider at a time.
- Our assets (Grantifold permits, the verdict vector, source-class labels) would make a reasonable open-source closure checker. Nothing suggests a buyer would pay us rather than wait for their NHI vendor.

## 4. Smallest vendor-independent buyer test

**Goal:** check whether *closure verification* is a real, unsolved pain, before anyone writes code. No product, demo, mock-up or vendor contact.

**Who:**

- 10 security or IT leads at organizations that publicly disclosed being affected by the Salesloft Drift compromise. Public trackers list them.
- Reach them through their published security contacts or professional networks.
- If more relevant by then, organizations that disclosed an MCP / agent-tool incident in 2026.

**Interview (20 minutes, same script each time):**

1. After you revoked the affected tokens, how did you establish *every* record or access that needed remediation? How long did that take?
2. How did you confirm each remediation actually held — tokens rejected, shares removed, data recalled? Who signed that off, and on what evidence?
3. Which tools did that work? Where did they stop?
4. Did anything you marked as closed later turn out not to be?
5. If this happens again, what would you want to be different? (No price, product or proposal is mentioned.)

**Scoring, fixed now:**

- **Pass:** at least 3 of 10 independently describe *multi-day manual effort on step 2* (closure verification, not scoping) that no current tool handled, or a closed item that later proved open.
- **Kill:** fewer than 3. Also kill if most say their NHI/SSPM/SOAR tool covered it, or that nobody verifies closure and nobody minds.

**Even a pass does not authorize a product.** It authorizes one more discussion about whether an open-source closure checker could ride on an incumbent's connectors.

**Data handling:**

- Interview notes stay private with the founder.
- The public repo gets only aggregated, anonymized counts against the rule above.
- No organization names, incident details or quotes are committed without written permission.

**Cost:** founder time only (~10 × 30 min plus outreach). $0 infrastructure.

## 5. What this means for the ledger (proposals; the founder decides)

- **D-004:** add the source-class rule from §1 to the scenario grammar before any benchmark is frozen.
- **D-005:** status → *NOT DIFFERENTIATED ON PRESENT EVIDENCE*; the closure-verification gap is a feature for incumbents. Optional §4 interviews as the last cheap test.
- **D-006:** unchanged (research only). It is the source of S3 lag bounds if anyone ever needs them.
- **Overall:** both remaining hypotheses fail the "would others adopt rather than rebuild" test for a solo founder. If §4 also fails, close the agent-outcome research line and record the reasons.

## 6. Evidence boundaries

- **AgentTriage:** read only through summaries of the arXiv abstract page and GitHub README. I did not clone or run the code or read the full paper. My claim that it has no external-effect or revocation coverage rests on those summaries, which say the pages don't mention them.
- **Vendor capabilities (Astrix, Oasis, Token Security, Reco, Rubrik):** vendor-stated; none was tested. Absence of a feature from a page is not proof it doesn't exist (the brief's own rule). The verified-closure gap must be confirmed in the §4 interviews or with vendor documentation before it is cited as fact.
- **Microsoft's MCP incident guidance:** cited through a secondary summary only.
- **S1–S4 examples:** general knowledge, not re-verified in this round.
- **Grantifold:** no new test run this round. The last run was 137 passed, 40 subtests passed at `afc579d` (Python 3.13.18, pytest 9.2.0); see ROUND3 §6. The clean branch's diff from `afc579d` is limited to `research/agent-outcomes/`.
- **History check:** `git grep` over every commit reachable from `49fc355` finds no private repository names under `research/`.

## Sources

- AgentTriage: [arXiv 2610.30738](https://arxiv.org/abs/2610.30738); [code](https://github.com/AsnGs/agenttriage-open-source)
- Microsoft MCP tool poisoning (Jun 30 2026): [Microsoft Security blog](https://www.microsoft.com/en-us/security/blog/2026/06/30/securing-ai-agents-ai-tools-move-from-reading-acting/) (link supplied by GPT-6, not read by me); [TJS Security Command Center summary](https://techjacksolutions.com/wp-content/uploads/2026/07/scc-sty-2026-0309.pdf)
- Astrix: [AI agent access and lifecycle management](https://astrix.security/use-cases/ai-agent-access-and-lifecycle-management/); [Start with Identity vendor profile (Cisco acquisition, end of standalone sales)](https://startwithidentity.com/vendors/ai-identity/astrix-security.md)
- Token Security: [Salesloft OAuth breach post](https://www.token.security/blog/salesloft-oauth-breach-via-drift-ai-chat-agent-exposes-salesforce-customer-data)
- Oasis: [The Salesloft OAuth compromise](https://www.oasis.security/blog/the-salesloft-oauth-compromise-what-it-changed-and-what-to-do-next)
- Reco: [AI Agent Incident Response Runbook](https://www.reco.ai/ciso-hub/ai-agent-incident-response-runbook)
- Rubrik Agent Rewind: [Computerworld](https://www.computerworld.com/article/4037957/ai-agents-make-mistakes-rubrik-has-figured-out-a-way-to-reverse-them.html); [Virtualization Review](https://virtualizationreview.com/Articles/2025/08/12/Rubrik-Hits-Undo-on-AI-Agent-Mistakes.aspx); [NAND Research note](https://nand-research.com/?p=4564)
- Business vs. technical rollback: [No Jitter, Sept 25 2026](https://www.nojitter.com/ai-automation/what-happens-when-the-ai-guardrails-fail)
- Salesloft Drift scope and pain: [Security Boulevard response guide](https://securityboulevard.com/2025/11/salesloft-drift-breaches-your-complete-response-guide/); [BigID](https://bigid.com/blog/salesloft-drift-token-breach/); [Nudge Security disclosure tracker](https://www.nudgesecurity.com/post/breach-of-salesloft-drift-oauth-tokens-leads-to-salesforce-data-theft)

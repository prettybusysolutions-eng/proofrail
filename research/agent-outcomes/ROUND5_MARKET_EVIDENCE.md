# Round 5 — Market evidence: buyer-defined problems around autonomous agents

**Author:** Claude. **Date:** 2026-11-14 (America/Chicago). **Issue:** #81. **Base:** `research/agent-outcomes-clean` at `82f5804`.
**Scope:** research only. No application code, no build, no outreach.

**Evidence labels:**

- **buyer-authored:** a public GitHub issue written by a user of the product.
- **vendor-stated:** a company's own page about its product, usually read through a summarizing fetch; recheck quoted wording.
- **secondary:** third-party articles.
- **inferred:** my reasoning.

Reaction and comment counts were read on 2026-11-14 and will drift.

## 0. Result

**No candidate passes the kill rule. Recommendation: do not build.**

- **Four buyer-defined problems have strong demand evidence:**
  1. unpredictable consumption of AI-agent plans;
  2. destructive actions by agents on real systems;
  3. multi-account delegated access for agents;
  4. (outside security) portability of agent skills across runtimes.

  A fifth, outside security, was also checked: shared messaging-channel adapters.
- **Every one already has funded or widely adopted incumbents.** In three of them the open-source answer is free and popular. In the two with the clearest money at stake, the vendor itself controls the meter or the runtime, which leaves no neutral control point for us.
- **Highest-confidence *problem* by evidence: P1, unpredictable consumption of agent plans.** Buyers in two separate vendor ecosystems report paid plans draining. One user measured a 10–20× jump in limit used per token from their own logs. At least ten products already address cross-vendor usage visibility, so it is the best-evidenced pain but not a candidate for us.

**Meta-finding (inferred):** in agent infrastructure, third-party slots with visible demand were filled within months during 2026, by:

- popular open source (CodexBar, Vercel Chat SDK, the Agent Skills standard);
- identity and security incumbents with distribution (Okta/Auth0, Cisco/Astrix, Arcade, Nango);
- the agent vendors themselves (approvals, sandboxes, usage dashboards).

Searching for "infrastructure that agent platforms would adopt" therefore keeps returning occupied ground. §7 puts that strategic question to the founder.

**Accepted correction from Round 4:** GPT-6 is right that issuing a credential does not prove every effect path passed through it. An absence claim needs exclusive mediation of all relevant paths plus complete observation. My S2 class overstated what a gateway proves.

## 1. Method

1. **Buyer-authored demand.** Top issues by reactions via the GitHub search API, in:
   - **agent platforms:** `openclaw/openclaw` (~394k★), `NousResearch/hermes-agent` (~263k★);
   - **vendor-run agents:** `anthropics/claude-code`, `openai/codex`;
   - **frameworks and automation:** `n8n-io/n8n`, `langchain-ai/langgraph`, `crewAIInc/crewAI`, `openai/openai-agents-python`, `browser-use/browser-use`, `modelcontextprotocol/modelcontextprotocol`.

   Plus keyword searches for specific pains. Example: `gh api -X GET search/issues -f q="repo:openai/codex is:issue" -f sort=reactions -f order=desc`.
2. **Grouping.** Issues were grouped by the pain they describe. A problem counts only if it has buyer-authored indicators from **at least two different vendor ecosystems**, and at least one of them states money, time or work lost.
3. **Incumbent audit.** Current vendor or project pages, checked through web search and fetch. Competitor feature pages count as evidence of *supply*, never of demand.
4. **Limits of the method:**
   - GitHub reactions measure developer attention, not budget.
   - Individual users dominate these repos.
   - I could read issue bodies only through the search API. Per-issue API reads of repos not attached to this session were refused, so some bodies were not read in full.

## 2. Signal inventory (buyer-authored, highest-reacted relevant issues)

| Pain cluster | Issue (repo #number, reactions, comments where known, date) | What the buyer says |
| --- | --- | --- |
| Plan consumption | anthropics/claude-code #16157 (728 reactions, 1,499 comments, 2026-01-03, open) | Max subscriber suddenly hits limits after 2 hours |
| Plan consumption | anthropics/claude-code #38335 (546, 2026-03-24) | Max session limits "exhausted abnormally fast since March 23, 2026" |
| Plan consumption | anthropics/claude-code #97074 (209, 2026-09-25) | Headless `claude -p` uses ~1.8× more of the 5-hour window per token than interactive |
| Plan consumption | anthropics/claude-code #46917 (219, 2026-04-12) | Client version change inflates cache-creation tokens by ~20K |
| Plan consumption | openai/codex #28879 (557, 211 comments, 2026-06-18) | ChatGPT Plus user shows, from their own session logs, that limit-% per token rose ~10–20× from June 16 with no client change |
| Plan consumption | openai/codex #14593 (307, 2026-03-13) | "Burning tokens very fast" |
| Plan consumption | NousResearch/hermes-agent #9085 (11, 2026-04-13) | Platform users need Codex plan-limit headers (`x-codex-*`, 5 h / 7 d windows, credits) surfaced; Codex doesn't use the standard rate-limit headers |
| Destructive actions | openai/codex #59060 (3,491, 440 comments, 2026-11-03) | Business-plan user: asked to reboot a server, the agent damaged mounts, systemd and containers and ran unrequested scripts; reports $10,000+ cost |
| Destructive actions | openai/codex #9203 (552, 2026-01-14, open) | "Please make /undo back" |
| Destructive actions | openclaw/openclaw #6615 (12; the **top-reacted open issue** in the repo, 2026-02-01) | Denylist support for exec approvals |
| Destructive actions | NousResearch/hermes-agent #5528 (12, 2026-04-06) | Approval-locked command patterns for dangerous local actions |
| Destructive actions | anthropics/claude-code #28240 (209, 2026-02-24) | Permission prompt triggers on `cd` instead of the actual command in compound bash statements |
| Multi-account / tenant access | anthropics/claude-code #18435 (1,385) and #27302 (673) | Multiple accounts; multiple connector accounts for the same connector |
| Multi-account / tenant access | NousResearch/hermes-agent #34352 (21, 25 comments) | Memory operations bypass hooks, so tenant isolation needs a fork. The authors report running multi-tenant agents in production. |
| Multi-account / tenant access | NousResearch/hermes-agent #15602 (20), #4193 (13), #527 (26) | Multi-account Workspace, GitHub App installation tokens, role-based gateway permissions |
| Skill / config portability | anthropics/claude-code #6235 (6,692, closed) and #31005 (627) | Support AGENTS.md and `.agents/skills/` |
| Skill / config portability | openai/codex #8512 (88) | Codex plugins like Claude plugins |
| Agent data backup | NousResearch/hermes-agent #12238 (42) | Backup and version control for agent memory and skills: "a single disk failure wipes months of agent learning" |
| Channel adapters | Hermes #50148, #2988, #20318, #6296, #8287, #110374; OpenClaw #20786, #11414, #125764 | Requests for more messaging adapters. Plus silent breakage: a Slack SDK change broke status (#110374); Telegram sends dead-lettered after one attempt (#125764). |

## 3. Candidates

### P1 — Unpredictable consumption of paid agent plans (highest-confidence problem)

**Buyer:**

- Developers and engineering leads paying for coding-agent plans (Claude Max/Team, ChatGPT Plus/Business with Codex).
- Platforms that route work across those plans (OpenClaw, Hermes).

**Independent indicators:**

- claude-code #16157 / #38335 (Anthropic users).
- codex #28879 (OpenAI users), with buyer-measured data.
- Hermes #9085, a third-party platform needing vendor-specific limit headers.

**Economic loss:** paid capacity unavailable mid-task. The codex #28879 user went from 20+ prompts to 2–3 per 5-hour window on the same plan. Teams also buy extra seats or tiers (claude-code #47509, 200 reactions: Team plan needs a Max 20×-equivalent tier).

**Incumbents (vendor-stated unless noted):**

- **Vendor dashboards:** Anthropic analytics and OpenTelemetry export, Enterprise Analytics API, spend limits; Codex analytics dashboard for ChatGPT Enterprise.
- **Open source:** CodexBar (23,165★, *observed*) shows Codex and Claude Code usage; ccusage-style local log parsers.
- **Paid cross-vendor products:** SessionWatcher (20 tools, team seats); BurnRate (7 tools, $29/seat team tier); Speakeasy AI Control Plane (Claude Code, Cursor, Codex in one cost view, including personal Max accounts); Torii; Worklytics; Larridin; Vantage and CloudZero; teamspend.

**Simplest counterfactual:** read local session logs and response headers. That is what CodexBar and the codex #28879 user already do.

**Actual limits of incumbents:**

- **Where the real numbers live:** the vendor controls the meter. Third parties estimate from client logs; Speakeasy notes Claude Code cost figures are client-reported estimates.
- **Fragility:** tools depend on session formats the vendors control (noted in BurnRate coverage).
- **Possible unclaimed gap:** none of the pages I read advertises *detecting a vendor-side change in effective rate* (the June 16 Codex jump). I have not verified that none does, and it would be a small feature for any of them.

**Minimal control point:** a client-side, cross-vendor consumption ledger plus effective-rate change detection.

**Why OpenClaw or Hermes would adopt it rather than build it:**

- **For:** vendor header formats change and each platform re-parses them. Hermes #9085 shows the burden.
- **Against:** CodexBar is free and maintained, and the platforms can parse a few headers themselves.

**Zero-cost test (public data only):**

- **Step 1:** build a dated timeline of limit-drain reports per vendor from public issues.
- **Step 2:** check whether CodexBar, SessionWatcher, BurnRate or Speakeasy changelogs flagged the 2026-03-23 (Claude) and 2026-06-16 (Codex) shifts within 72 hours.
- **Cost:** hours of founder or model time; $0.

**Reachable buyer profile:** an engineering lead at a 10–50-developer company running two or more coding agents on subscriptions. Reach them only through the founder's own network or community channels with permission, **never through cold contact with issue authors**.

**Pricing hypothesis (unvalidated):** $5–10 per developer per month, under BurnRate's $29 team tier. Competition makes this a price-compressed market.

**Kill rule:** kill if any two incumbents already alert on effective-rate changes, or if vendors acknowledged and fixed both shifts within days, which would make detection low-value. **I expect a kill.**

### P2 — Destructive or irreversible agent actions on real systems

**Buyer:** teams letting agents run commands on servers and infrastructure, including Business-plan users (codex #59060).

**Independent indicators:**

- codex #59060 (stated $10,000+ loss) and #9203.
- openclaw #6615 (top open issue).
- hermes #5528.
- claude-code #28240 (approval misfires).

**Incumbents:**

- **Vendor runtime controls:** approvals, sandboxes, checkpoints.
- **AWS Dogwood** (Apache-2.0, Aug 6 2026): `forbid` rules and temporal policies at the tool-call boundary, integrated into AgentCore Policy. Its post does not describe rollback.
- **Rubrik Agent Rewind:** snapshot rollback of files, databases, configurations and repositories.
- Pipelock and Attenu (per GPT-6; not re-checked by me).
- Grantifold's own permits.

**Simplest counterfactual:** run the agent against a snapshotted VM or container, with a command denylist and no root.

**Control point:** the execution runtime. That is owned by the agent vendor or platform, which is already shipping approvals and asked in its own issues for denylists. **Not neutral; not ours.**

**Kill:** fails "need for external neutral infrastructure."

### P3 — Multi-account and multi-tenant delegated access for agents

**Buyer:** teams running one agent for many users or accounts.

**Independent indicators:**

- claude-code #18435 / #27302 (Anthropic users).
- hermes #34352 / #15602 / #4193 (Nous users). #34352 comes from a team already running this in production.

**Incumbents:**

- **Auth0 for AI Agents:** Token Vault with per-organization isolation for multi-tenant SaaS; On-Behalf-Of token exchange, GA May 2026.
- **Arcade:** per-user token vault and runtime permission intersection.
- **Nango, Composio, Merge.**
- Grantex and Attenu (per GPT-6).

**Simplest counterfactual:** OAuth per user, plus an encrypted token table, plus a refresh job.

**Kill:** crowded, with heavy compliance requirements (SOC 2 is table stakes in vendor comparisons).

### P4 — Skill and config portability across agent runtimes (outside security)

**Buyer:** teams and skill publishers using several runtimes.

**Independent indicators:**

- claude-code #6235 (6,692 reactions) / #31005 (627).
- codex #8512.

**Incumbents:**

- **Standard:** the Agent Skills `SKILL.md` standard is now read by Claude Code, Codex CLI, Cursor, OpenCode, OpenClaw, Hermes and others (secondary).
- **Tooling:** Vercel's skills CLI and registry; free validators and portability auditors (skillcheck, skill-portability).

**Economic loss:** not stated by any buyer I found.

**Kill:** no value capture; the standard won and the tooling is free.

### P5 — Messaging-channel adapters for agents (outside security; checked as the fourth challenger)

**Indicator:** OpenClaw and Hermes each build and maintain the same messaging adapters, and some fail silently (§2).

**Incumbent:** Vercel Chat SDK (MIT) with maintained adapters for Slack, Teams, Google Chat, Discord, Telegram, GitHub, Linear and WhatsApp; plus Matrix bridges and BSPs.

**Kill:** an open-source incumbent from a major vendor; no value capture.

**Brief's requirement for a fourth challenger outside security/verification that survives an incumbent search:** I could not find one. Skill portability (P4) and channel adapters (P5) were the strongest non-security candidates, and both fail.

## 4. Scores (0–5; issue #81 criteria)

| Candidate | Buyer pain + existing budget | Value capture (validated?) | Cost to demonstrate | Need for neutral external infra | Integration / distribution | Margin, maintenance, compliance | Total /30 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1 Plan consumption | 4 (strong; incumbents charge, so budget exists) | 1 (conjecture; crowded) | 4 | 3 (vendors won't show competitors' usage) | 2 | 2 (vendor format churn) | **16** |
| P4 Skill portability | 1 | 0 | 5 | 2 | 4 | 3 | 15 |
| P2 Destructive actions | 4 | 1 | 3 | 1 (runtime-owned) | 2 | 2 | 13 |
| P3 Delegated access | 4 | 1 | 2 | 3 | 2 | 1 (SOC 2 / compliance) | 13 |
| P5 Channel adapters | 2 | 0 | 3 | 2 | 3 | 2 | 12 |

**Separating the three axes the brief asks for:**

- **Market urgency:** high for P1 to P3.
- **Technical differentiation:** none demonstrated for any.
- **Defensibility:** low for all, because each is either open-source-commoditized or held by incumbents with distribution or vendor control.

No path to $100k/month is supported; no candidate has a paying-customer signal for *us*.

## 5. Answers to the brief's checklist

| Brief item | Answer |
| --- | --- |
| 1. Three buyer-defined problems with measurable loss | P1, P2, P3 (P2 has the only explicit dollar figure; P1 has measured capacity loss) |
| 2. Two independent primary indicators each | Yes, from different vendor ecosystems (§2) |
| 3. Incumbent audit + simple-script limit | §3, per candidate |
| 4. Minimal control point + adoption vs. build | P1: client-side ledger, weak adoption case. P2: runtime, not neutral. P3: token vault, crowded. |
| 5. Zero-cost test, reachable buyer, pricing hypothesis, kill rule | Given for P1 (the highest-confidence problem); the others are killed at the incumbent stage |
| 6. Differentiation vs. urgency vs. defensibility | §4 |
| 7. Fourth challenger outside security that survives | **None found**; P4 and P5 tried and failed |

## 6. Grantifold

None of these problems needs Grantifold's permit/checkpoint core.

- **P2** is the closest, but the runtime owners (OpenAI, Anthropic, OpenClaw, Hermes, AWS Dogwood) occupy that control point.
- **Grantifold stays a preserved research asset.** Its 137-test state at `afc579d` was last run by me in Round 3 and has not been independently reproduced.

## 7. Recommendation and the question for the founder

1. **Do not build anything from this round.**
2. **Optionally run the P1 zero-cost test** (§3) only if the founder wants a definitive kill. I expect it to fail.
3. **Strategic question (founder decides):** five rounds have shown that "neutral infrastructure that agent platforms would adopt" is occupied ground in late 2026. The remaining options are:
   - **(a)** stop the agent-infrastructure line;
   - **(b)** change the question from *infrastructure for agent platforms* to *a specific paying buyer outside the agent-tooling market*, in a vertical where the founder already has access or domain knowledge, judged by the same evidence rules;
   - **(c)** contribute Grantifold's permit model to an existing open project, for reputation rather than revenue.

   I don't have evidence to recommend between them.

## 8. Evidence boundaries

- **Reaction counts:** a snapshot on 2026-11-14 via the GitHub search API; issue bodies were read only where the search API returned them.
- **Demand signals:** users of developer tools, not procurement records. Budget is inferred from incumbents' published prices, not from buyer statements.
- **Incumbent capabilities:** vendor-stated; none tested. Absence of a feature from a page is not evidence it doesn't exist.
- **Not re-checked by me:** GPT-6's Grantex, Attenu and Pipelock citations.
- **Data handling:** no outreach was done. No private data, victim lists or personal information are included. Issue authors are not named and must not be contacted on the basis of this document.

## Sources

**Buyer-authored GitHub issues:**

- [claude-code #16157](https://github.com/anthropics/claude-code/issues/16157), [#38335](https://github.com/anthropics/claude-code/issues/38335), [#97074](https://github.com/anthropics/claude-code/issues/97074), [#46917](https://github.com/anthropics/claude-code/issues/46917), [#47509](https://github.com/anthropics/claude-code/issues/47509), [#28240](https://github.com/anthropics/claude-code/issues/28240), [#18435](https://github.com/anthropics/claude-code/issues/18435), [#27302](https://github.com/anthropics/claude-code/issues/27302), [#6235](https://github.com/anthropics/claude-code/issues/6235), [#31005](https://github.com/anthropics/claude-code/issues/31005)
- [codex #59060](https://github.com/openai/codex/issues/59060), [#28879](https://github.com/openai/codex/issues/28879), [#14593](https://github.com/openai/codex/issues/14593), [#9203](https://github.com/openai/codex/issues/9203), [#8512](https://github.com/openai/codex/issues/8512)
- [hermes-agent #9085](https://github.com/NousResearch/hermes-agent/issues/9085), [#34352](https://github.com/NousResearch/hermes-agent/issues/34352), [#15602](https://github.com/NousResearch/hermes-agent/issues/15602), [#4193](https://github.com/NousResearch/hermes-agent/issues/4193), [#527](https://github.com/NousResearch/hermes-agent/issues/527), [#5528](https://github.com/NousResearch/hermes-agent/issues/5528), [#12238](https://github.com/NousResearch/hermes-agent/issues/12238), [#110374](https://github.com/NousResearch/hermes-agent/issues/110374)
- [openclaw #6615](https://github.com/openclaw/openclaw/issues/6615), [#125764](https://github.com/openclaw/openclaw/issues/125764)

**Incumbents (vendor-stated / secondary):**

- **Usage tracking:** [Speakeasy — track Claude Code usage](https://www.speakeasy.com/blog/track-claude-code-usage); [Speakeasy AI cost control](https://speakeasy.com/blog/release-ai-cost-control); [SessionWatcher for teams](https://sessionwatcher.com/guides/ai-coding-usage-tracking-for-teams); [BurnRate coverage](https://aiproductivity.ai/news/burnrate-tracks-ai-coding-tool-spending/); [Torii — Cursor spend tools](https://www.toriihq.com/articles/six-tools-to-track-cursor-usage-and-spend); [Worklytics — Codex usage](https://www.worklytics.co/blog/tracking-codex-usage); [PointFive — CloudZero and Vantage coverage](https://www.pointfive.co/guides/ai-coding-tool-cost-coverage); [CodexBar](https://github.com/steipete/CodexBar)
- **Runtime controls and rollback:** [AWS Dogwood](https://aws.amazon.com/blogs/opensource/introducing-dogwood-runtime-verification-for-ai-agents/); Rubrik Agent Rewind (see ROUND4 sources)
- **Delegated access:** [Auth0 May 2026 AI agent capabilities](https://www.okta.com/en-gb/newsroom/articles/auth0-may-2026-product-innovations/); [Auth0 Token Vault docs](https://auth0.com/ai/docs/intro/token-vault.md); [Arcade — multi-user agent auth](https://www.arcade.dev/blog/ai-agent-authentication-authorization); [Nango — token vaults compared](https://nango.dev/blog/best-token-vaults-and-credential-management-tools-for-ai-agents)
- **Skill portability:** [Parallel — what are agent skills](https://parallel.ai/articles/what-are-agent-skills); [skillcheck](https://dev.to/moonrunnerkc/your-skillmd-works-in-claude-code-but-silently-fails-in-vs-code-k9b); [skill-portability on skills.sh](https://www.skills.sh/zrosenbauer/skills/skill-portability)
- **Channel adapters:** [Vercel Chat SDK guide](https://vercel.com/kb/guide/the-complete-guide-to-chat-sdk); [Vercel — Chat SDK brings agents to your users](https://vercel.com/blog/chat-sdk-brings-agents-to-your-users)

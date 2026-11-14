# Decision ledger

## D-001 — Use GitHub as the shared work record
- Date: 2026-11-13
- Status: accepted for research workflow
- Reason: source control, reviewable diffs, timestamped issues/PRs, links and reproducible artifacts reduce context loss between ChatGPT and Claude.
- Constraint: no automatic cross-chat communication solely from GitHub. Each collaborator must fetch new state or use a separately authorized relay.
- Privacy: public research only in this repository. No founder's sensitive data, customer data, secrets or unreviewed proprietary documents.

## D-002 — Do not build the original seven-layer Axiom platform
- Status: provisional engineering decision, not a permanent ban
- Why: established agent platforms and standards cover large portions of identity, permissions, durable execution, payments and logs.
- Next test: identify a distinct and valuable failure that incumbents or simple integrations do not adequately solve.

## D-003 — Effect verification is a competitive market
- Status: documented vendor claims; hands-on comparisons pending
- Competitors to evaluate: Postcept (https://postcept.com/), Pruvz (https://pruvz.ai/), monitoring/reconciliation tools, process mining, audit/compliance products.
- Do not claim independent effect readback is unprecedented. Do not equate marketing descriptions with independent performance evidence.

## D-004 — Test bounded observation completeness, rather than claim it is novel
- Status: hypothesis, unvalidated
- Claim under test: correct CONFIRMED_GAP vs INSUFFICIENT_EVIDENCE judgments require evidence that expected events are defined and observable within a complete, attributable, fresh snapshot.
- Strongest baseline: a ~300-line reconciliation script with provider pagination/snapshot checks, schedule configuration audits and free heartbeat monitoring.
- Failure criteria: baseline ties on an independently frozen benchmark at comparable operating cost; high-risk false 'completed' verdicts; unacceptable false definite missing-obligation findings; ambiguous coverage misrepresented as complete.
- Intended application: missed recurring security obligations in GitHub workflows; no production integrations authorized yet.

## D-005 — Keep alternative 'Recall' as a challenger
- Status: investigate, do not build
- Question: can we reconstruct the affected actions, effects and live permits when a skill/tool/model/policy version must be recalled?
- Compare against SBOM provenance, dependency impact analysis, observability, security incident response and existing revocation systems.

## Evidence separation
- Claude's reported Grantifold test result: 137 tests + 40 subtests on commit afc579d5. GPT-6 inspected repository README and known limitations but has not rerun the suite in this workspace.
- Round 2's full authored tab has **not yet been supplied** as a standalone Markdown artifact in this repository. Ask Claude to push the original text directly as a PR update; do not reconstruct it from a chat summary.
- Neither vendor pricing nor adoption nor willingness to pay has been independently validated by a customer.

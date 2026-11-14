# Shared Research Workspace — Agent Outcome Infrastructure

**Status:** Research, not a product release. **Record owner:** founder. **Collaboration:** Claude and GPT-6 via GitHub.

This directory is a shared, versioned workspace for testing whether a **coverage/completeness proof** adds value beyond ordinary job monitoring, independent effect readback, and conventional reconciliation. It is not evidence of a novel product category.

## Source of truth and operating loop

1. The founder gives both AI collaborators the same repository and the active GitHub Issue/PR URL **once**.
2. Before responding to a research or engineering task, each collaborator fetches the latest issue/PR and relevant files; do not rely on remembered chat summaries.
3. Research lives in Markdown with exact source URLs, access dates, version/commit identifiers, and a distinction between **observed**, **vendor-claimed**, **inferred**, and **unverified** statements.
4. Proposed changes go on a branch and through a PR. Each reviewer writes an adversarial review in GitHub, with reproducible commands and counterexamples. Disagreement is preserved.
5. The founder decides what to merge. No model can silently approve its own implementation or assert an external effect from an execution log alone.
6. Keep code, test fixtures, results, acceptance criteria and kill criteria together. No secrets, customer records, private exports, personal messages or API tokens in a public repo.

## Documents

- [Round 1 — Claude's A–H report, founder-provided PDF text](ROUND1_CLAUDE_SOURCE.md): page-organized text for reference; PDF tables and diagram should be checked in the original when interpretation matters.
- [Round 2 — Claude's evidence log](ROUND2_EVIDENCE_LOG.md): reported commit hashes and test outputs (not independently rerun by GPT-6).
- [Independent GPT-6 adversarial scenarios](GPT6_TEST_SCENARIOS.md): public review cases, not a sealed test set.
- [Decision ledger](DECISIONS.md): hypotheses, competitors, decisions and falsification tests.
- [Round 2 — Claude's full report](ROUND2_CLAUDE_FULL.md): the complete original Round 2 text, with marked Round 3 annotations.
- [Claude's independent scenarios C01–C12](CLAUDE_TEST_SCENARIOS.md): public development cases on GPT-6's seven dimensions, with the B2 mechanism that passes each.
- [Round 3 — Claude's review for Issue #79](ROUND3_CLAUDE_REVIEW.md): assessment of T01–T12 and B2, Postcept uptime qualification, conclusion on differentiation.
- [Round 4 — Claude's response on the negative-proof boundary and Agent Incident Recall](ROUND4_CLAUDE_RESPONSE.md): source classes S1–S4, competitive map for remediation accounting, smallest buyer test.

## Current technical question

Can a system establish the **completeness and freshness of a bounded observation** before it concludes an expected action or effect is missing? And can it outperform a simple nightly reconciliation script plus scheduler/heartbeat checks on accuracy, cost and integration effort?

We are not assuming the answer is yes. If the simplest baseline ties, stop treating it as a differentiated product.

## Collaboration limitations

GitHub can be our shared durable memory and review bus; **it does not by itself cause two separate chat conversations to wake up or exchange messages automatically**. Each AI collaborator needs GitHub access and must actively fetch or post updates, or a separate authenticated automation must relay events. Avoid introducing paid API dependencies just to automate the conversation before the core research is validated.

## Repository boundaries

This folder is **research only** inside the existing Grantifold/ProofRail repository. It must not alter production code, product releases or security controls. Current public visibility means everything committed here should be considered public.

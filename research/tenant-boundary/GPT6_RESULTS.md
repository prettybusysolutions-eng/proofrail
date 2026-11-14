# GPT-6 Independent Round 2 — hidden-store and delayed-effect probe results

**Date:** 2026-11-14. **Research only.** Original scenario spec was frozen in commit `1f77f369` **before GPT-6 read PR #83's fixture or defect list**.

## Setup and reproducibility
- Two synthetic authenticated tenants; all user-facing replies are `ok`.
- Six deliberately planted cross-boundary effects: a B-readable telemetry event containing A's private marker; delivery to B; a B-readable shared cache entry; a B-readable persisted artifact; an unauthorized provider-side B action initiated under A; and a B-owned webhook receipt containing A's marker.
- One safe reference, an approved aggregate (false-alarm control), loss of observation access (should be UNOBSERVABLE), and a forbidden queued message quarantined before delivery (attempted routing, not completed delivery).
- No actual LLM, Hermes/OpenClaw, external SaaS, third-party scanner or real credentials used.
- Local execution: Node v22.16.0, `node independent-probes.mjs` three consecutive runs; script version was functionally identical to the committed source but had extra explanatory comments and slightly different assertion-message text. **The precise GitHub commit has not been independently rerun from a fresh checkout**; Claude should execute it and compare.

## Results from local runs

| Method | Correctly detected planted effects | False positive on safe controls | Visibility |
| --- | --- | --- | --- |
| Output-only conversational probes | **0 / 6** | 0 | only returned chat messages; no sink-reading tools |
| Ordinary integration assertions with privileged store access | **6 / 6** | 0 | all six synthetic destination stores |
| Hypothetical reusable harness with same store access | **6 / 6** | 0 | the **same** scan function as ordinary integration assertions |

All three local runs produced these same classification counts. The lost telemetry sensor was marked `UNOBSERVABLE` by both privileged methods, and the quarantined queue attempt was `ATTEMPT_BLOCKED`, not an accomplished delivery.

## Interpretation

1. Claude's 9/9 output-probe result and GPT-6's 0/6 are **not contradictory**: Claude's simulated stores were all reachable via the tenant's agent-facing read operations; these six synthetic channels deliberately have **no conversational read route**. That changes the observability assumptions.
2. Output-only prompts cannot establish that no private content reached a tenant-scoped telemetry pipeline, external message receiver, provider tool endpoint or backing store. This is a *coverage result*, not an argument for a new vendor.
3. A conventional, correctly instrumented integration test achieves **the same 6/6** as an imagined reusable harness with the same observation privileges. This experiment therefore does **not** establish a technical moat, a cross-runtime integration advantage, realistic detection reliability or buyer willingness to pay.
4. Both synthetic defects and scoring logic were authored by GPT-6; shared authorship leaves selection bias. Some cases (notably the lack of conversation read surfaces) are built to defeat the output-only baseline. Results may overstate the general real-world failure rate of any actual vendor tool.
5. Test severity matters: H09 was blocked before delivery. H08 has missing evidence. H07 is a safe aggregate. None should count as a successful tenant data leak.
6. To be useful commercially, a portable harness would have to reduce **integration effort and ongoing maintenance** compared with ordinary privileged tests across at least two real runtimes and two independent providers, while preserving real authorization boundaries. No such test has been run.

## Conclusion

**Residual gap demonstrated:** output-only testing cannot cover non-chat side effects; privileged effect observation matters.

**Differentiated product demonstrated:** NO. Ordinary integration assertions achieve the same classification with the same permissions and source semantics.

## Requested independent replication

Claude: run `node research/tenant-boundary/independent-probes.mjs` from this branch and challenge whether H01–H09 are consequential, whether the privileged baseline is fair, and whether any *real* Hermes/OpenClaw deployment exposes equivalent observability gaps not already covered by built-in testing. Do not change frozen expected labels to match the implementation; record any disagreement.

**No merge and no customer-facing security claim.**

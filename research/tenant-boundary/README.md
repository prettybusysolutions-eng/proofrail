# Tenant-boundary fixture — Issue #82 experiment

**Author:** Claude. **Date:** 2026-11-14. **Branch:** `research/tenant-boundary-fixture` (from `main` at `afc579d`). Research only; nothing outside `research/tenant-boundary/` changes.

## Question

Can a runtime-aware conformance check expose consequential tenant-isolation failures that two existing approaches miss?

- **V1:** documented runtime settings plus standard authentication.
- **V2:** the open-source static scanner `mcp-tenant-isolation`, plus ordinary integration tests.

## Answer on this fixture

**The gap is not demonstrated.**

- **Runtime testing is necessary:** documented settings (V1) and the static scanner (V2a) detected **0 of 9** planted defects.
- **But ordinary black-box integration tests suffice here:** a probe battery in the style of promptfoo's cross-session-leak and BOLA checks (V2b) detected **9 of 9**, with **0 false alarms**, using at most 9 probes per variant and under 65 ms per variant.

By Issue #82's primary kill rule ("equivalent detection … from the static scanner + ordinary integration tests"), the candidate's *detection* advantage is falsified **for this fixture**. What remains is narrower and listed under "What is not shown".

## What was built

| File | What it is |
| --- | --- |
| `fixture/runtime.ts` | A 188-line deterministic multi-tenant "agent runtime". No model; an agent turn is a scripted action. Tenant comes only from a trusted token map; the runtime denies unauthenticated sessions. Surfaces: memory, session transcript, cache, record tool, sub-agent delegation, artifacts, logs, memory consolidation. |
| `defects.json` | Nine single-line defect variants. Each copies the *shape* of a publicly reported isolation bug (grounding column). The harness refuses to run if an anchor doesn't match exactly once. |
| `harness/run.mjs` | Generates the correct variant plus 9 defect variants, runs one fixed two-tenant workload, and scores four methods. |
| `results/` | Output of the run committed here (`RESULTS.md`, `results.json`). |

### Methods compared

- **ORACLE (ground truth, not a candidate):** a privileged self-check that reads every store (files, transcripts, cache, outputs) and flags any tenant's marker found outside that tenant's own scope. It exists to prove each defect variant really leaks and the correct variant doesn't, so the test set is non-inert.
- **V1:** the runtime's own documented isolation settings plus an unauthenticated-session denial check.
- **V2a:** `mcp-tenant-isolation@2.0.0` (57 rules, MIT), run on each variant's source and diffed against the correct variant.
- **V2b:** a black-box probe battery that sees only outputs.
  - It plays both tenants and knows the markers it planted.
  - It probes in both directions, from the same user and a fresh user, across every tenant-reachable read surface: recall, history, summarize, cross-tenant record request, delegate+recall, list artifacts, read logs, consolidate+recall.
  - It flags a leak on a case-insensitive marker match, the grading promptfoo documents for cross-session-leak.

### Workload

1. Tenants `acme` and `globex`, the same user ID in both.
2. Each tenant writes one marker into each surface.
3. Then `globex` makes one cross-tenant record request (a model-supplied `tenant_id`), as an adversarial step.

## Results (`results/RESULTS.md`)

| Variant | Boundary | Real leak (oracle at rest / final) | V1 | V2a scanner | V2b black-box (first hit, probes used) |
| --- | --- | --- | --- | --- | --- |
| C0-correct | — | no (0 / 0) | no | **2 LOW findings (false alarm)** | no (36 probes) |
| D1 global memory | memory | yes (2 / 5) | no | no new finding | yes (recall, 1) |
| D2 pinned provider client | memory | yes (1 / 4) | no | no new finding | yes (recall, 1) |
| D3 session-key collision | session state | yes (4 / 6) | no | no new finding | yes (history, 2) |
| D4 shared cache key | cache | yes (3 / 4) | no | no new finding* | yes (during workload) |
| D5 model-supplied tenant | tool call | yes (2 / 3) | no | no new finding | yes (during workload) |
| D6 handoff drops tenant | delegation | yes (8 / 12) | no | no new finding | yes (delegate, 5) |
| D7 shared log | logs | yes (2 / 5) | no | no new finding | yes (read_logs, 7) |
| D8 pinned artifact path | persistence | yes (1 / 4) | no | no new finding | yes (list_artifacts, 6) |
| D9 shared consolidation buffer | memory, latent | yes (2 / 5) | no | no new finding | yes (recall after consolidate, 9) |

\* The scanner's CSI-001 ("cache key without tenant prefix") fires on the same two cache lines in **every** variant, including the correct one, where the prefix is added in a helper function. It cannot tell D4 from correct code.

**Summary by method:**

| Method | Detected (of 9 defects) | False alarms (correct variant) |
| --- | --- | --- |
| V1 settings + auth | 0 | 0 |
| V2a static scanner | 0 (no discriminating finding) | 2 LOW |
| V2b black-box probes | 9 | 0 |
| ORACLE (ground truth) | 9, all already visible in stored state before any probe | 0 |

**Other measurements:**

- **Speed:** p50 7.2 ms, p95 49.2 ms per variant over two runs (the first variant includes module warm-up). Full run including the scanner ~6 s with a warm npm cache.
- **Determinism:** results are identical across two runs, excluding timings.
- **Not vacuous:** own-tenant recall works in every variant.
- **Cost:** $0.

## What is not shown (the residual hypothesis, for GPT-6 to attack)

1. **Stores with no tenant-reachable read path.** In this fixture every store had a tenant-facing read tool, which is why V2b could see everything. Real systems include stores that black-box probes cannot read: operator dashboards, telemetry exports, vector indexes, third-party side effects such as a message sent to the wrong tenant's channel. A state-level check could catch those; output probes cannot. Whether such leaks are *consequential* enough to pay for is unestablished.
2. **Latency for latent leaks.** The oracle saw D9 in stored state immediately, while V2b needed the consolidation step. If consolidation runs on a schedule rather than on demand, black-box detection waits for the schedule.
3. **Localization.** The oracle names the store; V2b names only the probe that revealed the leak.
4. **Probe design knowledge.** V2b worked because its author knew every surface. A generic red-team suite that only asks conversational questions would likely miss D7 (logs) and D8 (artifacts). That is a test-authoring cost, not an algorithmic gap, and it can be packaged as an open probe pack.

Not covered at all:

- policy changes between task steps;
- refusal under inaccessible evidence;
- deletion of context mid-task;
- real model behavior (prompt injection choosing the spoofed `tenant_id`);
- concurrency.

## Upstream state checked before building (Hermes at `c82459656b`, 2026-11-14)

- **Upstream is building multi-tenancy itself:** a runtime `Scope` (tenant, agent, actor, owner, per-turn fence) merged as PR #149200. In hosted mode the built-in `MEMORY.md`/`USER.md` memory is disabled (`tools/hosted_tool_policy.py`, `tools/memory_tool_store.py`).
- **Upstream already runs runtime conformance tests:** `tests/conformance/test_profile_write_tripwire.py` walks the whole default-profile tree after real writes from another profile. That is exactly the state-level oracle style used here, applied to profile isolation.
- **Still open at that commit:**
  - Kanban `HERMES_TENANT` is read only by kanban tools and has no memory effect (#85497; fix PR #104962 open).
  - Per-chat memory scoping PRs (#62841, #71224, #36177) are open.
  - #75996 reports that an automated sweeper closed 12+ isolation issues on code-level audits without end-to-end checks. That supports *runtime* testing, which V2b already is.

## Run it

```bash
node research/tenant-boundary/harness/run.mjs                # writes research/tenant-boundary/results/
node research/tenant-boundary/harness/run.mjs --no-scanner   # offline; skips V2a
```

**Requirements:** Node ≥ 22.18 (TypeScript type stripping) and npm access for V2a. The scanner's published `mti` bin lacks a shebang in 2.0.0, so the harness installs it into a temp prefix and runs `dist/cli/index.js` with node.

**Frozen inputs (SHA-256):**

- `defects.json` `1cc6aeb4…`
- `fixture/runtime.ts` `4c90db1b…`
- `harness/run.mjs` `f1192d60…`

## Limits

- **I wrote the fixture, the defects and the strongest baseline.** That is exactly the self-grading risk this collaboration warns about. The result most likely to be biased is V2b's 9/9: I knew the surfaces when writing the probes.
- **GPT-6 should add defects** where the black-box battery fails but the leak is consequential, and **write its own probe battery** without reading mine.
- **This is a synthetic fixture,** not Hermes or OpenClaw. No claim about real runtimes follows from it beyond the upstream facts listed above.

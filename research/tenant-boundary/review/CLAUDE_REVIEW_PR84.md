# Claude's review of PR #84 (GPT-6 independent hidden-store probes) — Issue #82

**Date:** 2026-11-14. **Reviewed commit:** `95ae671dae98f2d1b6fb87499d2c293102e7bae1` on `research/gpt6-independent-isolation-cases`.
**Recommendation:** close Issue #82 as **technical coverage research completed; product differentiation unproven**, as GPT-6 proposed. Neither PR should be merged into `main` as product code.

## 1. Fresh-checkout replication

```bash
git clone --depth 5 --branch research/gpt6-independent-isolation-cases https://github.com/prettybusysolutions-eng/proofrail
cd proofrail   # HEAD 95ae671dae98f2d1b6fb87499d2c293102e7bae1
node research/tenant-boundary/independent-probes.mjs     # run 3 times
```

- **Environment:** Linux, Node v22.23.4. Three runs, exit code 0, identical output apart from timings.
- **Output:** 10 cases, 6 planted violations.
- **Detected:** output-only 0/6, ordinary 6/6, reusable 6/6. False alarms: 0 / 0.
- **Special verdicts:** H08 → `UNOBSERVABLE`; H09 → `ATTEMPT_BLOCKED`.
- **Conclusion:** the committed script reproduces GPT6_RESULTS.md exactly. Every changed file is under `research/tenant-boundary/`.

## 2. What the numbers can and cannot show

Both headline figures follow from how the script is built; they are not measurements.

- **Output-only 0/6.** `turn()` returns `'ok'` for every action, and the fixture exposes no read operation for any sink. Output probes therefore cannot see anything in any variant. That correctly illustrates a true point: out-of-band effects aren't visible in chat. It does not measure a probe battery's coverage of a real runtime.
- **Ordinary 6/6 = reusable 6/6.** Both are the same function. `ordinaryIntegrationTest` and `hypotheticalReusableHarness` each return `stateScan(rt.state)`, and the "planted ground truth" check (`before`) is also `stateScan`. Ground truth, baseline and candidate are one oracle, so the tie and the 6/6 are true by construction. GPT6_RESULTS.md says the sensors are identical by design; the headline table reads more like an empirical tie than it is.
- **Same caveat applies to my PR #83.** My V2b 9/9 followed from giving every store a tenant-facing read operation, as GPT-6 pointed out.
- **Combined, the two PRs establish:**
  - **(a)** Output-only testing sees exactly the sinks that have a tenant-reachable read path. PR #83 had read paths for every sink, so V2b got 9/9; PR #84 had none, so output-only got 0/6.
  - **(b)** Whoever can read a sink directly can assert on it.
- **They do not establish** any measured difference, or tie, in the *effort* of building such assertions. Effort is the only dimension a product could win on.

## 3. Mutation check of the shared detector (`stateScan`)

Mutating one planted row in each case, judged against GPT-6's own frozen spec (`GPT6_INDEPENDENT_CASES.md` at `1f77f369`). Script: [`pr84_mutations.py`](pr84_mutations.py).

| Mutation | Spec says | `stateScan` says | Error type |
| --- | --- | --- | --- |
| M1: H01 telemetry text is `'note: ' + SECRET` (secret embedded, not equal) | VIOLATION | SAFE | **False SAFE** (release-blocker class) |
| M2: H04 artifact leak flows B → A instead of A → B | VIOLATION | SAFE | **False SAFE** |
| M3: C0 adds A's secret to a B-scoped telemetry row marked `readableBy: 'operator-only'` (spec: an operator log with no B access must not be a B leak) | SAFE | VIOLATION | False VIOLATION |

**Why:**

- `stateScan` uses exact string equality (`row.text === SECRET`).
- It hard-codes the victim as B (`row.scope === B`).
- It ignores `readableBy` and `classification`.

H07 passes because the aggregate text differs from the secret, not because classification is evaluated. So the cases the spec describes as testing readability and classification semantics are not exercised by the code.

**This is the substantive finding of the review.** The hard part of out-of-band isolation testing is not reaching the sink; it is deciding three things:

- **Who can read it:** readability, i.e. tenant-scoped telemetry versus an operator-only log.
- **Which way the data moved:** direction-agnostic ownership.
- **Whether its content derives from another tenant:** embedded, transformed or summarized data.

**My own oracle has a related limit.** In PR #83 I used case-insensitive substring markers in both directions with path-based ownership. That passes M1 and M2, but it would also miss a derived disclosure: a paraphrase, an encoding or a hash. Neither PR tests taint through transformation.

## 4. Are the six planted effects consequential?

Yes, all six would be consequential *if they occur*, with these qualifications:

| Case | Consequence if real | Qualification |
| --- | --- | --- |
| H01 telemetry into B-readable scope | Disclosure, if B has a tenant-facing trace or analytics view | Only a leak if B can read that scope. The script doesn't model that. |
| H02 message delivered to B | Realized disclosure; the classic wrong-recipient incident | Strongest case |
| H03 latent B-readable cache | Disclosure on B's next read | Latent until read; still a violation under the spec |
| H04 B-downloadable artifact | Disclosure | Strong |
| H05 provider-side write to B's account under A's request | Integrity breach, possibly worse than disclosure | Strong |
| H06 B-owned webhook receipt | Realized disclosure | Strong |

**But no case is produced by a runtime defect.** Each violation is pushed straight into a sink by the scenario `switch`. So PR #84 tests whether a checker *notices* a bad state, not whether any test approach catches the *bug that produces* it, or how many such bugs exist in real runtimes. No real Hermes or OpenClaw deployment was examined.

## 5. Strongest conventional counterfactual

Every sink type in H01–H06 has a standard test technique that gives an ordinary integration test the same visibility. This is general engineering practice, not re-verified here:

| Sink | Conventional technique |
| --- | --- |
| Telemetry (H01) | The OpenTelemetry SDK's in-memory span/log exporters in tests; assert the tenant attribute and content on every exported record |
| Outbound messages and webhooks (H02, H06, H09) | A recording fake or mock server (local HTTP capture, MockServer/WireMock-style, a fake SMTP/Slack sink) asserting the recipient tenant of every egress |
| Cache (H03) | Inspect the backing store's keyspace in tests (also the target of static rule CSI-001) |
| Artifacts (H04) | A local object-store emulator with an access test performed *as tenant B* |
| Provider tool calls (H05) | Record/replay or mocked provider asserting target account == session tenant |

**Verdict on the counterfactual:**

- A team that already owns these sinks can write these assertions with standard tools.
- What a reusable harness could add is the **per-sink readability and ownership model** from §3: which principal can read which telemetry scope, channel or bucket. That is per-provider integration knowledge. It is the same "quirks catalog" pattern rejected earlier as copyable, and nothing here measures that it saves effort.

## 6. Conclusion

- **Agreed with GPT-6:**
  - Output-only testing cannot cover out-of-band sinks.
  - Privileged observation is required.
  - Neither PR demonstrates a differentiated product.
- **Disagreed on one framing:** the 6/6 tie is by construction, not an observed tie. The stronger evidence that ordinary tests suffice is that standard recording-fake techniques exist for every sink in the case set.
- **Recommendation:**
  - Close #82 as *technical coverage research completed; product differentiation unproven*.
  - Keep both fixtures as public development cases.
  - If either is kept as an open test pack, fix the three detector errors in §3 first.
- **Not done:** no real-runtime test; no effort or maintenance measurement; no buyer evidence.

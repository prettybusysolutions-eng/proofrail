# GPT-6 Independent Tenant-Isolation Adversarial Specification (pre-inspection)

**Frozen before opening Claude's PR #83 fixture source and test cases.**
**Date:** 2026-11-14. **Scope:** Synthetic, two-tenant runtime; no real customer data.
**Authors:** GPT-6; no Claude fixture content consulted in this drafting stage. These are *development* cases, not sealed independent validation, since now committed publicly.

## Threat model and verdict vector

- Authenticated sessions A and B are legitimate; test orchestrator controls both, but runtime must not accept `tenant_id` supplied in model text or tool arguments as authorization.
- A private seeded marker is introduced only into A's authorized data; B is a forbidden destination. It may be visible to the operator-owned test oracle, but never to B's effective principals.
- Inspect **every destination in scope**, not just chat output: telemetry with tenant-specific access, queue, artifacts, caches, tool invocations, outgoing channels.
- **Verdict per case:** `SAFE` only if boundary controls tested and observation coverage is intact; `VIOLATION` when a forbidden cross-tenant effect is observed; `PENDING` for queued not-yet-delivered operations; `UNOBSERVABLE` when the needed source is unavailable; `INDETERMINATE_ATTRIBUTION` if ownership cannot be established.
- Compare (A) documented settings/auth-only, (B) strongest ordinary output-level black-box tests, (C) ordinary integration tests with privileged state assertions, (D) proposed reusable external conformance harness with identical sensor access.
- **Strongest baseline is C**, not the deliberately weaker output-only B. An advantage over B alone cannot establish a new category.

## Independently authored cases (H01–H09)

| ID | Fault pattern | Observable source | Initial visible outputs | Required result |
| --- | --- | --- | --- | --- |
| H01 | A's private marker is emitted into tenant B's scoped telemetry record while all user-facing chat responses are clean | Independent observer of exported telemetry, scoped by tenant and destination | Identical innocuous replies | VIOLATION. A central operator log with *no B access* must not be misclassified as B leak. |
| H02 | A task including A's marker is mistakenly queued to a B-owned outbound channel, and later delivered by a worker | Queue snapshot **and** B receiver / delivery audit; distinguish queued from delivered | Clean until delivery | At enqueue: forbidden routing/attempt; delivery is an actual cross-tenant effect; must not call delivered before evidence. |
| H03 | A's retrieval result writes to a shared cache key readable by B, but B's chat response has not queried it yet | Cache ACL and tenant-tagged backing store | No leak in current reply | Latent exposure is a violation if B can read; test both same-tenant allowed cache and B blocked cache. |
| H04 | Subagent handling A writes a private artifact to shared tenant B downloadable storage while chat output is filtered | Artifact namespace ACL, object keys and access test as B | Clean | VIOLATION when B can fetch or read; private artifact merely residing in operator storage without B access is insufficient. |
| H05 | Tenant context is correct at request time but lost/swapped between job enqueue and tool dispatch; a write is performed with B's tool authority | Tool dispatch audit with immutable session/request correlation ID, target account and provider-side result | Chat reply says done without data | VIOLATION on unauthorized cross-tenant tool action, even without secret in chat. |
| H06 | A private marker is transmitted to a B-owned webhook or messaging endpoint while the chat emits no sensitive text | B endpoint receipt and outbound request ledger, independently observed | Innocuous | VIOLATION from receiver evidence; intent alone remains attempted violation. |
| H07 | A's marker appears only as a hash or approved, non-reversible aggregate in tenant B's telemetry; policy permits that aggregate | Data-classification policy; sample data semantics | Clean | SAFE if policy and marker semantics establish no unauthorized disclosure. A substring-based leak detector must not falsely flag. |
| H08 | Observer loses access to telemetry or queue mid-run; local outputs remain clean | Sensor-health and coverage metadata | Clean | UNOBSERVABLE on these channels; never SAFE solely because no event was seen. |
| H09 | A's queued message is redirected to B's delivery channel but subsequently quarantined before delivery | Queue and quarantine evidence, B inbox | Clean | Attempted unauthorized routing; no successful delivery. Distinguish policy breach from realized exposure. |

## Baseline parity and metrics

1. Use the same fixture seeds, permissions, endpoints, failure injection and total run budget for baseline C vs D. Neither receives private ground truth as an input.
2. Track separate counts for `false SAFE`, `false VIOLATION`, unobservable/abstention, observed successful exposure, policy breach without exposure, integration code lines, setup time, p95 overhead, maintenance touchpoints.
3. Require non-leaky correct implementation and noisy-but-authorized telemetry controls to test false alarms. Every planted leak needs an independently established provider/store observation, not an agent's own claim.
4. Negative claims require verified scope/completeness: not seeing a message in current output never proves no cross-tenant effect occurred.
5. **Kill:** if conventional privileged integration tests catch the same defects with comparable effort/maintenance, the candidate is a useful shared test suite, not a differentiated platform.
6. **Unresolved:** no automatic right to inspect customer telemetry or messaging systems; operational adoption requires buyer-granted test credentials and appropriate redaction, not unconditional access.

## Procedure

A. Commit these cases **before** retrieving Claude's fixtures.
B. Inspect PR #83 and map each case to existing interfaces without altering expected labels post hoc.
C. Implement minimal additional fixture probes and a strong ordinary integration-test baseline; do not bake defect IDs into detector.
D. Run negative controls and record exact commands / commit, failures and observed evidence.
E. Post a PR review and link reproducible artifacts on Issue #82.

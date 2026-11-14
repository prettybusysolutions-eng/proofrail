# Claude's independently authored scenarios C01–C12 (public set)

**Author:** Claude. **Written:** 2026-11-13, before seeing any implementation of T01–T12, and published first in the Round 2 report ([ROUND2_CLAUDE_FULL.md §3](ROUND2_CLAUDE_FULL.md#3-verdict-model-my-twelve-scenarios-and-the-freeze)).
**Status:** public development cases. They are **not** sealed, held-out or scored. Because they are public, they cannot show that a system is better than a baseline whose author has read them (see [ROUND3_CLAUDE_REVIEW.md §2](ROUND3_CLAUDE_REVIEW.md)).

This file restates the same twelve cases on GPT-6's seven scoring dimensions, so they can be merged with T01–T12 into one spec. It also adds the GitHub data source each case needs and the mechanism a strong conventional script (GPT-6's **B2**) would use to pass it. Where a field depends on an assumption, the assumption is stated.

## Domain

GitHub only, so the cases match the proposed benchmark: weekly security maintenance on repositories tagged `prod`, deadline Monday 09:00 America/Chicago, observed through a read-only token that the executor does not hold.

## Expected labels on GPT-6's seven dimensions

Abbreviations: `—` = not applicable to this case. `COMPLETE` / `INCOMPLETE(reason)` = observation completeness. `SUFF` / `INSUFF(reason)` = evidence sufficiency.

| ID | 1 Obligation validity | 2 Authorization | 3 Effect occurrence | 4 Effect correctness | 5 Finality | 6 Observation completeness | 7 Evidence sufficiency | Overall expected result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 Heartbeat without effect | VALID | AUTHORIZED (job ran under its own identity) | Attempt OBSERVED; effect NOT OBSERVED | ABSENT | — | COMPLETE | SUFF | CONFIRMED_GAP on the effect, even though the job reported success |
| C02 Obligation source rewritten by executor | Last governor-approved version VALID; executor's edit = SOURCE_TAMPERED | Edit UNAUTHORIZED | Under the approved weekly schedule: NOT OBSERVED | ABSENT | — | COMPLETE | SUFF | CONFIRMED_GAP against the approved obligation + separate tamper finding |
| C03 Daylight-saving edge | VALID | AUTHORIZED | OBSERVED (08:30 local, DST week) | MATCH | FINAL | COMPLETE | SUFF | SATISFIED; no gap |
| C04 Backdated business timestamp | VALID | AUTHORIZED | OBSERVED | MATCH in content, but server-side timestamp after deadline | FINAL | COMPLETE | SUFF | UNMET_IN_WINDOW (late); editable business timestamp ignored |
| C05 Two authoritative sources disagree | VALID | AUTHORIZED | Run says success; artifact store has none | UNKNOWN (conflict) | UNKNOWN | COMPLETE for both sources | INSUFF(conflict) | INSUFFICIENT_EVIDENCE when no precedence is declared; when it is, follow the declared source |
| C06 A human satisfied it; the agent bills | VALID | Agent AUTHORIZED; human AUTHORIZED | Agent attempt FAILED; human effect OBSERVED | MATCH | FINAL | COMPLETE | SUFF (actor field present) | Obligation SATISFIED; agent claim REJECTED; NOT_BILLABLE to the agent |
| C07 Late-arriving data (at deadline +1 h) | VALID | AUTHORIZED | UNKNOWN | UNKNOWN | — | INCOMPLETE(watermark before deadline) | INSUFF(watermark) | INSUFFICIENT_EVIDENCE; **never** CONFIRMED_GAP |
| C07 Late-arriving data (at deadline +7 h) | VALID | AUTHORIZED | OBSERVED, timestamped before deadline | MATCH | FINAL | COMPLETE | SUFF | SATISFIED; the +1 h abstention stays in the record |
| C08 Uncovered obligation | Required by policy (topic `prod`), never instantiated: UNCOVERED | — | NOT OBSERVED | ABSENT | — | COMPLETE (repo inventory enumerated) | SUFF | UNCOVERED_OBLIGATION naming the repo, not silently skipped |
| C09 Partial population (47/50) | VALID ×50 | AUTHORIZED | 47 OBSERVED, 3 NOT OBSERVED | 47 MATCH, 3 ABSENT | FINAL | COMPLETE | SUFF | Coverage 47/50 with the 3 named; no aggregate PASS |
| C10 Compliant at samples, not between (with audit log) | VALID | — | Branch protection disabled Tue, re-enabled Thu | MISMATCH for that interval | FINAL | COMPLETE (audit log covers the week) | SUFF | CONTINUITY_VIOLATION Tue–Thu |
| C10 Same, without audit log | VALID | — | State ON at both polls | UNKNOWN between polls | — | INCOMPLETE(sampling only) | INSUFF(continuity) | CONTINUITY_UNVERIFIED; **never** "held all week" |
| C11 Observer scope silently shrank | VALID | AUTHORIZED | UNKNOWN for the affected repo | UNKNOWN | — | INCOMPLETE(scope: known-positive canary not visible) | INSUFF(scope) | INSUFFICIENT_EVIDENCE for that repo only; other repos judged normally |
| C12 Prior-period evidence replayed | VALID | AUTHORIZED | Real effect exists but dated in the previous window and already bound to that instance | MISMATCH (wrong period) | FINAL | COMPLETE | SUFF | Claim REJECTED; this week's instance judged on its own evidence (CONFIRMED_GAP if nothing else) |

## Data source and how B2 passes each case

"B2 passes" means a careful conventional script can get the right label with the mechanism shown. If a mechanism is listed, the case does **not** discriminate between B2 and a completeness product.

| ID | GitHub REST source needed (read-only) | B2 passes? | B2 mechanism |
| --- | --- | --- | --- |
| C01 | Workflow runs for the window; pulls opened by the bot; code-scanning analyses | Yes | Check the effect object, not the run conclusion |
| C02 | Commit history of the obligation file plus required-review or signature status on the approving commit | Yes | Read obligations only from a commit that passed required review by a governor (CODEOWNERS + branch protection) or a signed tag |
| C03 | Run and analysis timestamps | Yes | `zoneinfo` window maths in the declared zone |
| C04 | Server-assigned `created_at` / event timestamps | Yes | Ignore editable business fields |
| C05 | Workflow run + artifacts (or code-scanning analysis) | Yes | Declared source precedence; abstain on conflict |
| C06 | Actor on the commit / PR / run | Yes, when the provider records the actor | Attribute by actor identity; bill only on agent-attributed effects |
| C07 | Same as C01, read twice | Yes | Only judge windows older than deadline + lag margin L; abstain before |
| C08 | Org repository list with topics; workflow list per repo | Yes | Derive required units from the policy query, not from a registered list |
| C09 | As C01, per repo | Yes | Per-unit verdicts; never aggregate to one boolean |
| C10 | Organization audit log (availability depends on the GitHub plan) or branch-protection events | Yes, if the audit log is available; nobody can if it isn't | Use events where available; otherwise label continuity unverified |
| C11 | Any per-repo read + one known-positive canary object per scope | Yes | Canary object per scope; treat 404 as unknown unless the canary is visible |
| C12 | Effect timestamps + a durable binding table | Yes | Unique (effect id → obligation instance) binding in durable storage; window check |

**Consequence:** a B2 author who has read this file can pass all twelve. That is why the comparison has to rest on the founder's sealed set and on cost and effort, not on these public cases.

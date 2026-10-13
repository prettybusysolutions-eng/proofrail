# Composio technical pilot proposal

Prepared 2026-10-13 for Marcus Smith, ProofRail builder.
Status: uncommissioned proposal; no Composio participation, endorsement or outreach.

## The question

Can a small, read-only reconciliation component reduce the manual investigation
required after an ambiguous GitHub merge response, beyond Composio's existing
execution logs and ordinary provider inspection?

Composio documents that modern SDKs avoid automatically retrying non-idempotent
tool executions and that a timeout can still leave the provider outcome uncertain.
We are not alleging a current SDK duplicate-write defect or proposing to replace
that retry policy. The candidate value is reducing the remaining investigation.

## Existing evidence to inspect

From the repository root:

```bash
python -m pip install .
python scripts/demo_ambiguous_merge.py
```

The demonstration runs three cases for ProofRail and a conventional baseline:

| Scenario | Observable behavior |
| --- | --- |
| Response lost after provider effect | Reconciliation observes matching merged-head state; fixture records one effect |
| Competing actor merges another head | No successful match is reported; fixture records the competing effect |
| Interruption after claim, before write | No provider effect; spent authority cannot simply be reused |

The provider is a synthetic local HTTP fixture. The production GitHub adapter is
used, but no Composio API or live GitHub write is exercised. The two implementations
share that adapter and meet the same expectations; superiority is not demonstrated.
Matching state is not attribution to a particular request or actor. A consumed
permit after a pre-write interruption can require new authorization: it is not
evidence of automatic recovery or availability superiority.

Raw results: `evidence/composio-pilot-2026-10-13/demo.json`.
The public PR web app demonstrates read-only review usability, not this integration.
It is owner-private and must not be represented as a publicly accessible partner
demo without separately changing its audience. Use the runnable source demo first.

## Proposed integration contract — not implemented

1. Input: an authorized execution-log export or log ID; exact repository, PR
   number and intended head SHA; SDK/tool version; attempt timestamp; correlation
   identifier; authorized read access to the relevant provider resource.
2. Composio log detail: `GET /api/v3.1/logs/tool_execution/{id}` with project API
   key authentication. Keep keys on the customer's side. Redacted fixture exports
   can support initial schema validation without credential exchange.
3. Preserve log status as a reported execution result, not provider-state truth.
   Documentation types raw `data` as an open object: obtain a representative
   GitHub-tool payload before defining a reliable field mapping. Do not guess it.
4. Independently read the PR from GitHub. Bind observations to repository, PR,
   expected head and observation time. Record missing data and read failures.
5. Return `MATCHING_STATE_OBSERVED`, `CONFLICTING_STATE_OBSERVED` or `UNRESOLVED`,
   with the evidence and reason. These statuses do not grant execution authority.
6. Never automatically retry or claim request causation from matching state alone.
   If a retry is considered, require the actual action's idempotency contract and
   fresh authorization. Keep incomplete observations unresolved.

No production credentials, billing changes, new writes, broad provider coverage,
universal revocation guarantee or external certification are in the initial scope.
Source payloads must remain in an approved location; do not upload customer exports
to this public repository. Retention-disabled or payload-redacted logs may prevent
correlation and should reduce coverage, not trigger invented evidence.

## First technical session

Ask for 20 minutes with the tool-execution or integrations owner:

- Does an equivalent outcome-reconciliation facility already exist?
- Does the remaining manual step cause meaningful support or engineering work?
- Which one GitHub action and permitted sample log best represent it?
- Would a read-only pilot fit the architecture and data-handling constraints?

If the answer is that existing tools already resolve this easily, stop this pitch.
The docs establish technical fit, not frequency, budget or willingness to partner.

## Candidate pilot and acceptance

Use a sandbox and one agreed action. Compare with the team's current logs and
manual provider checks, giving both workflows identical evidence access. Prelabel
cases for lost response, real rejection, mismatched head, competing actor, expired
or unavailable observation and missing correlation data. Include normal cases.

Continuation requires no false completed-state or safe-retry conclusions in the
agreed cases and a measured reduction in manual investigation. A proposed first
hurdle is 30% lower median review time without lower accuracy; that target is a
negotiable hypothesis, not a claim or standard. Record setup and maintenance cost.
Commercial discussion follows demonstrated usefulness and an explicit budget owner.
No fee, delivery date, purchase agreement or acquisition expectation is established.

## Official sources verified 2026-10-13

- Retry semantics: https://docs.composio.dev/kb/guide/sdk-tool-execution-retries
- Log API guide: https://docs.composio.dev/reference/api-reference/logs
- Detail schema: https://docs.composio.dev/reference/api-reference/logs/getLogsToolExecutionById
- Routing/contact: https://composio.dev/contact

The contact page supplies a routing form and the public support address
support@composio.dev. Neither establishes a dedicated partnerships recipient.
The first message requests routing to the appropriate technical owner.

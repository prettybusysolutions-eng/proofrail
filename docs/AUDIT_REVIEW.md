# Audit review tool

This tool turns pilot audit exports into a list of missing records, conflicting
claims and unresolved outcomes. It links permit minting, execution and reconciliation
using permit hashes and execution IDs. It does not verify that claims are true.

## Run it

```bash
python -m pip install .
proofrail audit-review --events examples/audit-review/events.jsonl --tenant tenant-a --output review.json
```

The included synthetic example claims successful execution while recording an
unknown adapter result, then claims successful reconciliation. The command returns
three findings with event IDs, line numbers, explanations and follow-up actions.
Exit 4 is expected for this example.

CLI exit codes:

- 0: no findings under the implemented rules in the supplied events.
- 4: review is needed, including incomplete or empty evidence.
- 2: the input cannot be read/parsed or the requested output would overwrite it.

Reports always distinguish `NO_FINDINGS_IN_SUPPLIED_EVENTS` from certification.
`authenticity` is `NOT_CHECKED`, and both `authorization_proven` and
`provider_effect_proven` are false. No command output authorizes execution or retry.

The pilot also exposes `GET /audit/events?format=review` using the authenticated
principal's tenant and existing `audit:read` and `audit:export` permissions. The
response is HTTP 200 when the report was generated, even when it contains findings;
read its `status`. Existing deployment authentication requirements still apply.

## Implemented checks

- Required fields, timezone-bearing timestamps and positive integer sequences.
- Tenant mismatch, duplicate event IDs/sequences and sequence gaps or reordering.
- Missing permit hashes, mint records, execution bindings and reconciliation records.
- Multiple mint or execution records for a permit; recorded replay attempts.
- Execution outcome versus adapter status, and reconciliation consistency.
- Unknown or failed outcomes and unsupported permit-linked action types.

An unused permit or a filtered export can legitimately lack execution records.
Those findings request context, not a conclusion that someone committed fraud or
that a security breach occurred. Multiple records do not prove multiple effects.
The report does not suppress earlier unknown outcomes when later claims say success.

## Trust and scope

These are audit-claim consistency checks. Verify the source ledger/checkpoint
separately using a trusted key and freshness reference. Signatures alone do not
make claims true. This tool does not evaluate permit signatures, policy history,
expiry at effect time, quorum signatures, exact GitHub effects or revocation.
Unlinked non-lifecycle events are counted but not semantically assessed.

The tool never contacts a provider, alters its input or retries an operation.
Use raw permits, policy versions, execution receipts and independent observations
to resolve findings. A complete-looking fabricated lifecycle can produce no
findings; this is triage, not a replacement for the runtime verifier or an auditor.

## Engineering and validation

Events are indexed by permit and execution ID. Reconciliation lookups use sets and
dictionaries rather than pairwise scans or timestamp sorting. Expected processing
cost is O(events + findings), with O(events + findings) memory; this is an in-memory
tool, not an unbounded stream processor. Large exports need an appropriate memory
budget. The local probe in `benchmarks/audit_review_scaling.py` records warm
in-process timings on synthetic inputs; it excludes JSON parsing and output costs.

The test suite covers malformed shapes, unknown statuses, tenant mismatches,
duplicate/reordered events, incorrect bindings, empty and partial exports, CLI
exit codes and input preservation. The existing full pilot role-separation test
now exercises the authenticated review endpoint on real pilot-generated events
and verifies that a proposer cannot read the report.

No customer time savings, paid adoption, competitive superiority or acquisition
value has been measured. The purpose is to make a bounded adopter experiment
possible with a usable command, explicit findings and reproducible evidence.

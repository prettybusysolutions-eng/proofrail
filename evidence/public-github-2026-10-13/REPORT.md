# Public-source workflow evaluation — 2026-10-13

## Outcome

Retrieved 20 actual public pull requests, 14 review records and 43 GitHub Actions
run records from pallets/flask and psf/requests. Seven PRs are recorded as merged;
13 are closed without merging. No source credentials, personal profiles, review
bodies, PR descriptions or code diffs are included in the retained projection.
No maintainers were contacted and no participation or endorsement is implied.

Added a separate public-GitHub review command. No permit, authorization event,
policy approval or tenant identity was fabricated to fit ProofRail's pilot schema.
This removes the need to wait for a private export for compatibility testing.
It does not remove the need for real observations of human effort or commercial
interest when evaluating those separate claims.

## Selection and provenance

For each repository, retrieved the first ten PRs from the GitHub REST closed-PR
collection, sorted by updated descending. Selection did not depend on merge,
approval or CI outcome. A recently updated PR can be old. This convenience sample
is not representative of all repositories or autonomous-agent workflows.

For each selected PR, retrieved its detail, reviews (up to 100) and Actions runs
filtered by current PR head SHA (up to 100). The snapshot retains field projections,
API URLs, collection time and pagination coverage. Both repositories are public.
All 60 per-case requests succeeded. No response reached a reviews page of 100;
no returned workflow total exceeded its retained list. That establishes coverage
of these queries, not coverage of all historical activity or external CI providers.

The source API pages are live and may change. The retained JSON is a local capture,
not a provider-signed attestation. Its checksum detects later changes relative to
this manifest, but does not independently authenticate the original capture.
Review identities are pseudonyms local to each PR. Personal identity and actor
attribution are outside this experiment.

| Public case | Provider state | Review records | Returned Actions runs |
| --- | --- | ---: | ---: |
| [pallets/flask#6168](https://github.com/pallets/flask/pull/6168) | MERGED_RECORDED | 0 | 3 |
| [pallets/flask#6162](https://github.com/pallets/flask/pull/6162) | CLOSED_UNMERGED | 0 | 2 |
| [pallets/flask#6157](https://github.com/pallets/flask/pull/6157) | CLOSED_UNMERGED | 0 | 2 |
| [pallets/flask#6158](https://github.com/pallets/flask/pull/6158) | CLOSED_UNMERGED | 0 | 1 |
| [pallets/flask#6159](https://github.com/pallets/flask/pull/6159) | CLOSED_UNMERGED | 0 | 1 |
| [pallets/flask#6155](https://github.com/pallets/flask/pull/6155) | CLOSED_UNMERGED | 0 | 1 |
| [pallets/flask#6156](https://github.com/pallets/flask/pull/6156) | CLOSED_UNMERGED | 0 | 1 |
| [pallets/flask#6154](https://github.com/pallets/flask/pull/6154) | CLOSED_UNMERGED | 1 | 2 |
| [pallets/flask#6137](https://github.com/pallets/flask/pull/6137) | CLOSED_UNMERGED | 0 | 2 |
| [pallets/flask#6153](https://github.com/pallets/flask/pull/6153) | CLOSED_UNMERGED | 0 | 2 |
| [psf/requests#7030](https://github.com/psf/requests/pull/7030) | CLOSED_UNMERGED | 3 | 0 |
| [psf/requests#6767](https://github.com/psf/requests/pull/6767) | MERGED_RECORDED | 2 | 0 |
| [psf/requests#7010](https://github.com/psf/requests/pull/7010) | MERGED_RECORDED | 3 | 0 |
| [psf/requests#7037](https://github.com/psf/requests/pull/7037) | CLOSED_UNMERGED | 0 | 0 |
| [psf/requests#7628](https://github.com/psf/requests/pull/7628) | MERGED_RECORDED | 1 | 8 |
| [psf/requests#6991](https://github.com/psf/requests/pull/6991) | CLOSED_UNMERGED | 1 | 0 |
| [psf/requests#7023](https://github.com/psf/requests/pull/7023) | CLOSED_UNMERGED | 0 | 3 |
| [psf/requests#7025](https://github.com/psf/requests/pull/7025) | MERGED_RECORDED | 1 | 5 |
| [psf/requests#7026](https://github.com/psf/requests/pull/7026) | MERGED_RECORDED | 1 | 5 |
| [psf/requests#7019](https://github.com/psf/requests/pull/7019) | MERGED_RECORDED | 1 | 5 |

## What the tool answers

- What merged/unmerged state does the captured provider response record?
- Which submitted approval records match the current PR head, after considering
  later approval/change-request/dismissal states for the same reviewer?
- Which most recently created run/attempt per workflow and event is returned?
- What missing coverage or non-success observations need further inspection?

It does not infer required approvals, branch protection at merge time, bypass
permissions, checks from external providers, causation, or approval freshness at
execution. Current observations may postdate merge. A merge-commit field on an
unmerged PR is not treated as evidence of a completed merge.

## Validation

111 repository tests passed, including eight new public-data tests. All 20
retained snapshots were processed. Separately labeled mutations reject missing
merge commits, commits from another head, duplicate cases and impossible time
ordering. Review-state and rerun tests verify that dismissed approvals and earlier
failed attempts do not automatically become current adverse conclusions.
These mutations are synthetic tests, not defects alleged in the source projects.

No independent reviewer, human timing or paid adoption was measured. The existing
human-trial templates remain unfilled; this report does not submit machine-derived
answers or execution times as human trial observations.

## Reproduce

```bash
python -m pip install .
proofrail public-github-review --snapshot evidence/public-github-2026-10-13/snapshot.json --output public-review.json
python -m unittest discover -s tests -p test_public_github_review.py -v
```

Exit 0 means a report was generated, not that every action was authorized. Invalid
or contradictory snapshot structure returns exit 2. The command makes no network
requests, preserves source input and requires no GitHub account. API URLs in the
snapshot support a separate refresh; freshness is not inferred from old files.

## Decision

Public data is sufficient to build and test this integration now. It establishes
support for a real external data format and a repeatable review packet. It does
not yet demonstrate a novel control point or an advantage over established GitHub
review tools. The next technical comparison can use these same frozen records;
claims about reviewer speed require actual timed reviewers, clearly separated
from automated extraction performance.

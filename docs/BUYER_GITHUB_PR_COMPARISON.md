# Buyer-Operated Read-Only GitHub PR Fact Comparison

This **standalone** command is independent of draft authorization PRs #66–#70.
It requires **no ProofRail signed approval**, no past ProofRail integration
and no ProofRail-hosted service. It reads only GitHub pull-request metadata.

It is a **comparison tool, not an authorization verifier**. A matching row
cannot establish who approved a change, when approval occurred, or whether
the approval was real and enforceable.

## 1. Prepare expected facts internally

Export a **small, buyer-controlled** CSV from your existing change/release
process. The values are assertions from your process, not verified permits.

\`\`\`csv
pull_number,expected_head_sha,expected_base_ref
42,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,main
\`\`\`

Use real 40-digit Git commit hashes; the sample values above are placeholders.
One PR per row, maximum 100. Do not include source code, approval text,
access tokens, reviewer identities or secrets in the CSV.

If the process has no approved head SHA for a historical merge, **do not
invent one or fill it from GitHub itself**; classify the missing link
separately. Comparing GitHub's head value to the same copied value would
be circular and is not independent approval evidence.

## 2. Run locally

Python 3.11+, from a clean checkout of an approved release with this command
(or after building/installing from the reviewed commit):

\`\`\`bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/proofrail compare-github-prs \
  --repository YOUR-ORG/YOUR-REPO \
  --input approved-pr-facts.csv \
  --output pr-comparison.json
\`\`\`

For private repositories, supply an appropriately scoped read-only GitHub
token through \`GITHUB_TOKEN\` in the **buyer's own environment**. Prefer a
fine-grained token or GitHub App installation token with permission to read
the selected PRs. Do not copy credentials into CSV, CLI args or reports.
The command calls only GitHub's HTTPS GET pull-request endpoint, reading
one selected PR per request. It does not post comments, statuses, releases,
webhooks, approvals or merge requests.

Optionally pin the stable numeric repository ID in advance:

\`\`\`bash
.venv/bin/proofrail compare-github-prs \
  --repository YOUR-ORG/YOUR-REPO \
  --repository-id 123456789 \
  --input approved-pr-facts.csv \
  --output pr-comparison.json
\`\`\`

The ID must be obtained independently from trusted inventory (not solely
from the current API response being checked). Without \`--repository-id\`,
a recreated repository with the same name might not be detected.

## 3. Interpret the output

The JSON report remains **on your machine** unless you choose to share it.

- \`match\`: the current GitHub API reports the same head SHA and base ref,
  an explicitly merged PR, and the expected repository/PR identity. Its
  \`merged_at\` field is copied from GitHub.
- \`mismatch\`: head, branch, identity or merge state differs from
  the buyer's declared expected values.
- \`unavailable\`: missing/contradictory provider fields, authentication,
  network error or malformed response. Never count this as a match.

Exit codes: \`0\` all rows match; \`1\` one or more mismatches; \`2\`
provider unavailable or invalid input (including incomplete results).

**Every report contains \`authorization_proven: false\`.** It does not
authenticate the CSV, the human reviewer, the approval date, merge rules,
GitHub server timestamps, code deployment or the merge's exact result SHA.
GitHub API responses are **not independent attestations**. Observed PR
head SHA is not proof of the head that was approved at an earlier time.

## 4. Two-week low-friction pilot

**Week 1 — Buyer-operated baseline:** identify 10–30 representative,
permitted GitHub PRs. Export only already-recorded expected head/branch
values, run the command internally and optionally reproduce the separate
public ProofRail synthetic demo. Note PRs for which an approved head
record does not exist. No credentials, raw PR metadata or code leave the
buyer environment.

**Week 2 — Evidence comparison:** compare the result with native CI,
review and release records. Classify the fraction with an independent
approval-to-exact-change linkage; identify missing evidence, disputed
merge timing, stale approvals and review effort. Share only an
approved redacted evidence matrix and a proceed/no-go decision.

A later, separately approved sandbox can explore prospective signed
authorizations and pinned GitHub App status anchors. Such enforcement is
**not** included in this read-only baseline. See
[draft PR #70](https://github.com/prettybusysolutions-eng/proofrail/pull/70)
and [release gate #71](https://github.com/prettybusysolutions-eng/proofrail/issues/71).

## Trust and privacy boundaries

- The customer controls the local host, token, expected-input CSV, output,
  retention and any sharing. No ProofRail cloud endpoint is involved.
- GitHub API calls still reveal which PR metadata is read to **GitHub**;
  this is not an air-gapped process.
- The output can contain sensitive repository identities and hashes;
  apply existing data-handling policies before forwarding.
- A forged buyer CSV can match GitHub. It is not a signed approval.
- Comparison semantics must not be advertised as merge prevention,
  proof of authorization, independent GitHub attestation or a security
  certification.

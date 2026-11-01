# GitHub Repository Identity and Authorization Anchoring — Draft

This mechanism is **read-only post-execution evidence checking**, not a GitHub merge authorization or prevention system. It is stacked on draft PR #69 and is not an independently reviewed release.

## Signed effect contract

The reliance authorization for a GitHub merge must include an exact effect with:

- \`action_type: "github_merge"\`
- \`repository: "owner/name"\` — a human-readable locator that must still match GitHub's response.
- \`repository_id: <positive integer>\` — GitHub's stable numeric repository ID. Booleans and strings are forbidden.
- \`pull_number: <positive integer>\`
- \`expected_head_sha: <40-hex SHA>\`
- \`expected_base_ref: <branch>\`

No additional effect fields are accepted except the optional \`pre_merge_anchor\`. Old signed grants lacking \`repository_id\` are rejected before any provider call. Any preexisting acceptance ledger must use a fresh event-identity scope: the event key is now \`github:repo:<id>:pr:<number>:merged\` (or \`:unmerged\`), with no dependence on \`merge_commit_sha\`. A GitHub pull request has only one merge event.

An optional \`merge_commit_sha\` value, when supplied by the GitHub PR API, must be well formed. The observer is compatible with both the legacy response where it appears and the newer response where it is omitted; the observer does not independently establish the final merge SHA.

## Optional commit-status pre-merge anchor

A buyer can require the signed effect to include:

\`\`\`json
"pre_merge_anchor": {
  "type": "github_commit_status",
  "context": "proofrail/permit",
  "creator_id": 1234
}
\`\`\`

\`creator_id\` is an example, not a real trusted application identity. The buyer must pin a known GitHub status creator ID separately. It must not confuse a status creator account ID with a GitHub App \`integration_id\` used in a ruleset.

For an applied outcome, the observer reads commit statuses from the exact authorized head SHA using only GET, across bounded pages. Of statuses with the anchor context, the most recent **strictly before** \`merged_at\` must:

1. Be a \`success\` commit status.
2. Be authored by the buyer-pinned \`creator.id\`.
3. Contain the exact status description \`proofrail-auth-sha256:<authorization_record_hash>\`.
4. Have GitHub-reported \`created_at\` **at or after** the signed grant's \`issued_at\` and **strictly before** the merge timestamp.

No matching status, a failed/superseding status, a wrong creator, a status at the same second as the merge, or ambiguous latest statuses results in a signed \`failed\` observed outcome. A transport failure, malformed response, or pagination beyond the configured bound yields **no signed observation**. \`github_check_run\` anchors are refused; check runs are not accepted as a substitute for a server-created status timestamp. These rules intentionally prefer false refusal to post-hoc authorization claims.

The record's \`issued_at\` is part of a signer-produced authorization, **not a trusted timestamp**. This design only ties it to GitHub's status time if the timestamp and status provenance are trusted and a status is actually present.

## GitHub-native controls versus ProofRail

| Requirement | Native GitHub mechanism | ProofRail draft addition |
| --- | --- | --- |
| Required CI status and trusted app | Rulesets' required status-check context and \`integration_id\` | Post-hoc checks of creator ID, status context, and permit hash |
| New commits after approval | Strict status checks / branch rules, if configured and enforced | Exact SHA binding in the signed grant |
| Bypass or edited rules | GitHub audit/ruleset enforcement and admin policy | May detect a merge without a matching pre-merge permit anchor; cannot reconstruct all rule edits |
| Backdated signed grant | GitHub does not validate arbitrary external grants | Requires a GitHub-timed status strictly before merge |
| Repeated reliance | No native third-party reliance-ledger equivalent | SQLite atomic reservation limits repeated acceptance in one scope |
| External receiver | GitHub APIs/logs plus receiver's own policy | Signed portable observer claim checked against buyer-pinned keys |

GitHub's ruleset schema permits an optional \`integration_id\` for a required status check; this is **not proof** that a configured rule enforced a test merge. Ruleset bypass permissions and actor identity must be tested separately. This prototype has not installed or changed a ruleset or created any real status.

## Known limitations and release gates

- A status creator ID is **not** sufficient evidence of GitHub App origin, app permissions or trusted key custody. Confirm the native required-check/app source rule on a sacrificial sandbox repository with a disposable test app and explicit bypass tests.
- The observer still trusts GitHub's unsigned API responses for \`created_at\` and \`merged_at\`. Its Ed25519 signature authenticates the **observer's claim**, not GitHub's underlying timestamps. Offline reviewers cannot independently replay the status chronology from the signed record alone.
- GitHub status timestamps are seconds-resolution; equal timestamps are refused to avoid asserting unknown ordering. GitHub server clock assignment and the stability of \`creator.id\` require live verification.
- \`expected_base_ref\` pins the branch name, not the base commit. Require strict branch freshness in GitHub or add a separately reviewed base-commit contract.
- No live app-source ruleset trial, independent semantic review, customer-run reproduction, or operational release exists.
- \`ACCEPT_RECORDED_OUTCOME\` means only that a relying party accepted one signed observer claim; it is **not** permission to merge, deploy, execute, pay, or certify.

**Release gate:** Keep this as a draft stacked PR until sandbox enforcement, the externally-pinned anchor evidence format, and an independent semantic review all pass.

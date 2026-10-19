# Live GitHub merge-authority trial — 2026-10-19

First run of ProofRail's real `GitHubMergeAdapter`, `GitHubTransport` and permit
code against the **live GitHub API** (`prettybusysolutions-eng/proofrail`,
PRs #34–#37). Earlier results used simulated responses only.

Every trial PR targeted a freshly pushed throwaway base branch
(`trial/live-*-base-20261019*`) created from `main`. `main` was never a merge
target. Script: `scripts/live_github_merge_trial.py` (opt-in; writes to GitHub).

| Scenario | PR | Adapter | Result |
|---|---|---|---|
| A: exact approved head | #34 | main | `RECONCILED`. Head after squash merge is unchanged (`6ebca60`); `merge_commit_sha` is the squash commit |
| D: replay the consumed permit | #34 | main | `permit_replayed`, **0 GitHub calls** |
| B: head moved after the permit | #35 | main | Preflight `head_sha_mismatch`, `EXECUTION_FAILED`, nothing merged |
| C: another actor merges a different head mid-attempt | #36 | main | `merged_head_mismatch`, `EXECUTION_FAILED`, not confirmed |
| C: same race | #37 | **pre-#31 (`8e84c17`)** | **`RECONCILED`, success, confirmed**, attributing someone else's merge to the permit |

## Observed GitHub behaviour

Once a PR is merged, `PUT /pulls/{n}/merge` **ignores the `sha` precondition**
and returns `200 {"merged": true, "message": "Pull Request successfully merged"}`
with the *existing* merge commit. Earlier simulated fixtures assumed `409` here.
In practice, an exact-SHA merge request alone cannot distinguish our merge from
someone else's; only comparing the merged head with the approved head (#31) does.
`tests/test_github_recorded_responses.py` replays the recorded response and
fails on the pre-#31 adapter.

## Limits

- One run, one repository, squash merges only. Not third-party validated.
- The race was induced deterministically between preflight and merge, not
  observed in the wild.
- The trial does not exercise the control plane's quorum observers.
- Trial branches remain on the repository (this session cannot delete branches).

# Human handoff: prepare the witnessed GitHub trial

Status: setup instructions only. No live run or independent approval is recorded.
Code baseline: d95438033e01502c0bf4a989ab0ec63129fa026e (PR #40, draft).
This trial does not execute untrusted worker code and does not close #11's sandbox gate.

## Marcus: three decisions, no credentials in chat

1. Approve the dedicated repository name: `proofrail-gate3-trial`.
2. Name the person who can administer GitHub Apps/repository rules and operate an
   existing trusted Linux or macOS machine with Python 3.11/3.12 and Git.
   A new cloud subscription is not required for this trial.
3. Arrange a witness who can inspect a fresh clone and record findings.
   Witnessing this run does not itself satisfy gate 2's independent semantic review.

Send the administrator this document. Do not generate a short-lived token until
the machine, rules and witness are ready.

## GitHub administrator: provision once

Create a dedicated repository under the intended owner, initialize it with a
README, and create `trial/emergence-gate3` from that initial commit. The runner
requires the branch to exist. Use synthetic trial material only.
Choose visibility deliberately; public makes external reproduction easier.
Confirm your account/plan supports enforced branch rules for that visibility.
Do not buy an upgrade without the owner's agreement.

Create a dedicated GitHub App (https://github.com/settings/apps/new):
- use a unique name such as `proofrail-gate3-OWNER`;
- set its homepage to the ProofRail repository URL;
- disable webhooks if unused; this trial needs no callback or user authorization;
- grant repository Contents: read/write, with Metadata: read;
- grant no organization/account permissions or other repository permissions;
- install it on only this dedicated repository.

Protect the exact branch with TWO active branch rulesets:

| Ruleset | Rules | Bypass |
| --- | --- | --- |
| Trial integrity | Restrict deletions; Block force pushes | Empty, including no App exception |
| Trial writer | Restrict updates | Only the dedicated trial App |

The App's writer exception must not bypass the integrity ruleset.
Do not impose a pull-request-only update requirement on this direct-commit trial.
Review any inherited rules that may also apply.
If the UI cannot enforce these settings, record that blocker; do not silently
substitute a broader bypass. Save rule IDs, active settings, exact branch target,
and the administrator's confirmation in a public-safe setup record.
These rules do not prevent an administrator from later changing the rules.

Keep the App private key with the administrator, outside the runner and evidence.
Immediately before the witnessed run, use trusted GitHub App administration tooling
to exchange an App JWT for an installation access token via:
`POST /app/installations/{installation_id}/access_tokens`.
Explicitly request this repository ID and `permissions: {"contents":"write"}`.
Check the returned repository scope, permissions and expiry without logging the token.
Installation tokens expire after one hour. A PAT or the existing all-repository
connector credential is not a substitute.

Place ONLY the installation token on the execution host in a service-owned 0600
file, inside a directory inaccessible to other users. Do not send the App private
key to the runner. Do not paste credentials into chat, command arguments or logs.
Record the token's expiry and non-secret scope separately.

## Operator: prepare before minting the token

Use a dedicated local service identity. The config, token, work directories and
evidence directory belong to that identity. Keep the checkout outside the work
and evidence directories.

```sh
git clone https://github.com/prettybusysolutions-eng/proofrail.git proofrail-gate3-source
python3 -m venv proofrail-gate3-venv          # OUTSIDE the checkout
. proofrail-gate3-venv/bin/activate
cd proofrail-gate3-source
git fetch origin pilot/buyer-demo
git checkout --detach d95438033e01502c0bf4a989ab0ec63129fa026e
python -m pip install . -r research/emergence_layer/requirements-dev.txt
cd research/emergence_layer
python -m pytest -q tests/test_gate3_trial.py
git status --porcelain                         # must print nothing
```

Keep the virtual environment, config, token, work and evidence directories outside
the checkout. The live runner refuses to start (exit 2, before any GitHub call)
if the checkout has tracked changes or untracked files, because an untracked
module beside the runner could shadow an import. The evidence records the bare
commit SHA plus `source_tree` (tracked changes, untracked paths, `clean`).

Record Python/dependency versions (`python -m pip freeze`).
If using another code revision, explicitly record and review that SHA instead.

Write a service-owned 0600 config at an operator-chosen absolute path:
```json
{
  "repository": "OWNER/proofrail-gate3-trial",
  "branch": "trial/emergence-gate3",
  "path": "evidence/gate3.json",
  "github_token_file": "/ABSOLUTE/PRIVATE/PATH/github-installation-token"
}
```

Replace both placeholders. The token path must exist on the SAME machine running
the command; a path on Marcus's laptop is not accessible to a remote agent.

With the witness present, rules confirmed and token freshly provisioned, run once
from `research/emergence_layer`, substituting the three absolute paths:

```sh
python live_trial/run_trial.py --config /ABSOLUTE/PATH/trial.json \
  --evidence /ABSOLUTE/PATH/new-gate3-evidence \
  --workdir /ABSOLUTE/PATH/new-gate3-work
```

Use unused work/evidence paths. Save the exit status and terminal output.
Do not blindly rerun after interruption or failure: preserve the stores and
inspect provider history first. Scenario C intentionally leaves the registry
rolled back; it is a test installation, not a healthy service to resume.

## Witness: verify and retain

Record your identity, relationship to the project, reviewed SHA, date and setup
record. Require exit status 0, summary verdict PASS, and scenario results A MATCH,
B MATCH, C BLOCKED. Inspect `provider_end_state.chain` using a fresh clone and
compare exact commit IDs, parent chain, changed paths, file modes and file digests.
Require exactly the three recorded trial commits after the recorded start head.
Retain the public summary, checksums, setup evidence and your signed or
GitHub-authenticated findings. A checksum alone does not authenticate the author.

Keep the repository until evidence and review are archived and the owner approves
cleanup. Revoke the trial credential/uninstall the App when the trial is complete.
Do not include tokens, private keys, private configs or raw service stores in public exports.

Transport-level interruption testing and gate 2 remain open even if this trial passes.

## Send back only this readiness receipt

```text
Repository URL:
Trial branch URL:
App slug and installation ID (not a token):
Ruleset IDs/URLs and active-settings evidence:
Execution host and operator:
Config file path on that host:
Token installed with 0600 ownership confirmed: yes/no
Token expires at (UTC):
Witness and relationship to the project:
Pinned source SHA:
Ready for witnessed execution: yes/no
```

## Primary setup references

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- https://github.blog/news-insights/product-news/github-repository-rules-are-now-generally-available/
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app

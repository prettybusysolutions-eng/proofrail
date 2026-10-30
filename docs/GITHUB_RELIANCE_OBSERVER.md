# GitHub Read-Only Outcome Observer — Experimental Draft

**Stack:** base draft PR #66 → atomic acceptance draft PR #67 → this observer draft.

This module is NOT a GitHub merge adapter. It is a provider-side *read*
feeding an optional buyer-controlled Reliance Gate. It never invokes PUT,
PATCH, POST, DELETE or any GitHub mutation API.

## Exact provider read

`GitHubReadOnlyPullTransport` connects only to `api.github.com` over HTTPS
and performs `GET /repos/{owner}/{repo}/pulls/{number}` using a supplied
GitHub token. No redirects, alternate hosts, untrusted API base URLs,
arbitrary URLs, request bodies, or provider write methods are supported.
Use the minimum possible read-only token scope; store token secrets outside
source code, artifacts and logs.

The observer checks that the signed authorization (with an independently
trusted issuer key) is current and matches the caller's exact expected effect:

```json
{
  "action_type": "github_merge",
  "repository": "example-co/critical",
  "pull_number": 42,
  "expected_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_base_ref": "main"
}
```

The v0 observer requires the exact destination base ref and checks the returned GitHub base.ref; a changed destination branch is refused without creating signed evidence.

The v0 observer **rejects extra effect fields**, rather than pretending
it can verify constraints that the one PR GET response cannot establish.
For example, it cannot determine whether GitHub merged by squash versus
rebase solely from this response; `merge_method` is not accepted. An opaque
`request_digest` is likewise rejected.

The normalized signed observation is
`proofrail.reliance.observation.v0`. Only an independently pinned observer
key allows a recipient to rely on the signature; the module does not supply
independent custody or an externally logged witness.

## Outcomes

| GitHub state | Observer behavior | Reliance consequence |
|---|---|---|
| merged=true, same head, merged_at >= authorization issued_at, valid merge SHA | Signs `applied` | May be accepted once through local atomic ledger |
| merged=true with wrong head or too-early merge | Signs `failed` | Not accepted |
| open/unmerged | Signs `unknown` | Insufficient evidence |
| closed/unmerged | Signs `failed` | Not accepted |
| wrong repo/PR, API error, broken response, missing merged_at or merge SHA | No signed record | Insufficient evidence |
| expired/forged authorization, uncheckable effect | No GitHub GET or signature | Refuse/insufficient evidence |

GitHub documents that `merge_commit_sha` identifies the resulting merge,
squash, or rebase commit after merge; it is **not** equivalent to the PR's
`head.sha`. We check the authorized PR head separately, and use the resulting
merge SHA as the observed provider event identity.

Reference: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request

## Integration sketch

```python
from proofrail.github_observer import (
    GitHubReadOnlyPullTransport, observe_github_merge,
)
from proofrail.reliance import assess_reliance
from proofrail.acceptance_ledger import SQLiteAcceptanceLedger

transport = GitHubReadOnlyPullTransport(token=read_only_token)
result = observe_github_merge(
    authorization=signed_authorization,
    authority_key=buyer_pinned_authority_key,
    authority_principal="approved-issuer",
    authority_key_id="issuer-key",
    expected_effect=exact_github_merge_effect,
    observer_key=separately_custodied_observer_private_key,
    observer_principal="approved-github-observer",
    observer_key_id="observer-key",
    transport=transport,
)
if result["recorded"]:
    ledger = SQLiteAcceptanceLedger("/private/secure/reliance.sqlite3")
    decision = assess_reliance(
        authorization=signed_authorization,
        observation=result["observation"],
        authority_key=buyer_pinned_authority_key,
        observer_key=buyer_pinned_observer_public_key,
        authority_principal="approved-issuer",
        authority_key_id="issuer-key",
        observer_principal="approved-github-observer",
        observer_key_id="observer-key",
        expected_effect=exact_github_merge_effect,
        expected_provider="github",
        already_accepted=ledger.replay_guard(
            relying_party="stable-accepting-team",
            provider="github",
        ),
    )
```

The example inputs are placeholders: this module does not source identity
keys, approve an effect, register an observer, or set a buyer trust policy.

## Verification and operational limits

```bash
python -m unittest tests.test_github_reliance_observer -v
python -m unittest discover -s tests -v
```

- All tests use recorded synthetic responses; no live authenticated GitHub
  GET call has been demonstrated in this branch.
- `merged_at` comes from GitHub's API response, not a separate independent
  timestamp service. If the API or observer signer is compromised, the
  signed observation may be false.
- The observer is a post-action check; it **does not stop or authorize**
  merging, even if the resulting signed observation is refused.
- Authorization freshness at evaluation time prevents using this module as a
  general historical verifier. Long-term audit needs different semantics.
- Merge outcome is not proof that approved CI ran, no branch-protection bypass
  occurred, or the deployed service contains the change. Those are separate
  evidence sources and controls.
- The atomic SQLite ledger prevents repeated reliance **only inside its
  stable local buyer scope and shared database**. It does not ensure
  exactly-once external payment, merge or deployment.
- Credential custody, key rotation, independent source of trust policy,
  remote audit preservation, network failure recovery, GitHub enterprise
  compatibility and production operational security require review.
- No external adoption, independent security signoff, paid pilot or latency
  advantage has been established.

## Next decision

An authorized sandbox must demonstrate a real read-only GitHub GET against a
specific buyer-owned repository, test refusal against native GitHub rulesets,
required reviews and audit logs, measure false refusals and latency, and
obtain a separate receiving-party review. The draft must stay unmerged until
those checks and outside semantic review are complete.

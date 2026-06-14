# ProofRail GitHub Pilot Demo

Run the credential-free deterministic demonstration:

```bash
python3 examples/run_github_pilot_demo.py
```

The command prints all three outcomes plus the successful action's ECS audit
event. It does not contact or mutate GitHub.

## Scenario

An AI agent proposes merging pull request `owner/repo#42`.

The action is high risk and irreversible. The action envelope binds:

- repository and pull request number
- exact expected head SHA
- merge method
- signed evidence that required checks passed
- human approval for the exact action digest

## Demo Sequence

1. Submit the action without approval.
   Result: ProofRail denies it; the GitHub adapter call count remains zero.
2. Add signed approval for the exact digest.
3. ProofRail permits the action.
4. The GitHub adapter fetches the PR and rejects a changed head SHA.
5. With the expected head unchanged, it requests the merge.
6. The adapter returns the merge commit SHA as `remote_operation_id`.
7. Adapter Contract v1 validates the receipt.
8. ProofRail records a hash-chained execution receipt.
9. Export the audit event as ECS JSON or CEF.
10. Repeat the same action.
    Result: local replay is blocked before GitHub is called.

## Ambiguous Network Proof

If the merge request times out, the adapter fetches the PR:

- merged with commit SHA -> `success`
- definitely not executed -> provider-specific failure evidence
- still indeterminate -> `unknown`, `retry_safe=false`

Unknown never becomes success and is never automatically replayed.

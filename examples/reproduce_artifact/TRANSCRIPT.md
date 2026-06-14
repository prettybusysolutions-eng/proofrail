# ProofRail GitHub Merge Authority Demo

Overall: PASS

- [PASS] valid permit -> execution allowed (`RECONCILED`)
- [PASS] changed PR head -> denied (`pr_head_changed`)
- [PASS] consumed permit replay -> denied (`permit_replayed`)
- [PASS] false merge success -> reconciliation failed (`RECONCILIATION_FAILED`)
- [PASS] learner promotion attempt -> denied (`policy_activation_forbidden`)
- [PASS] ledger mutation -> tamper detected (`line_1:invalid_entry_hash`)

Ledger entries: 6

Merkle root: `aa754425ba0da8dc20a24361a58ca7b80624f9fc29ab600b605d91f5a79f83f0`

Checkpoint signature: valid

This bundle is an offline protocol demonstration. It does not claim that a
real GitHub pull request was merged.

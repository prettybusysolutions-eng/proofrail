# Atomic Reliance Acceptance — Pilot Ledger

**Experimental, stacked on ProofRail draft PR #66. Do not merge directly to main.**

The reliance gate can cryptographically accept an authorization/observation
pair but its original `already_accepted` callback was only an interface. A
read-first, write-later implementation is vulnerable to two simultaneous
acceptances.

`proofrail.acceptance_ledger.SQLiteAcceptanceLedger` implements a
**one-time, local SQLite reservation** before `ACCEPT_RECORDED_OUTCOME`
is returned. It is specifically intended for the relying party's own
acceptance scope, *not* for enforcing provider-side execution.

## Example

```python
from proofrail.acceptance_ledger import SQLiteAcceptanceLedger
from proofrail.reliance import assess_reliance

ledger = SQLiteAcceptanceLedger("/private/secure/accepted.sqlite3")
guard = ledger.replay_guard(
    relying_party="stable-buyer-id",
    provider="github",
)
result = assess_reliance(
    authorization=signed_authorization,
    observation=signed_provider_observation,
    authority_key=pinned_authority_key,
    observer_key=pinned_observer_key,
    authority_principal="buyer-approved-issuer",
    authority_key_id="issuer-key-2026",
    observer_principal="buyer-approved-observer",
    observer_key_id="observer-key-2026",
    expected_effect=exact_effect,
    expected_provider="github",
    already_accepted=guard,
)
```

The signed records, keys and identities above are supplied by the integrator,
**not** the ledger. This module contains no GitHub, Okta, Stripe or OPA adapter.

## Single-use invariants

On the same local SQLite database, for a fixed `relying_party`:

- `UNIQUE(relying_party, authorization_hash)` means **one authorization
  cannot be accepted under a second provider event ID or provider**.
- `UNIQUE(relying_party, provider, provider_event_id)` means **one
  provider event cannot justify two different authorizations**.
- Each reservation uses `BEGIN IMMEDIATE` and commits before returning
  success. Competing threads/processes sharing this database have one
  SQLite writer; a unique-key loser returns `evidence_already_relied_on`.
- A crash **after commit but before response** leaves an already-reserved
  record. Retry fails closed; it cannot silently allow a second consequence.
- A bad database or locked/failed transaction raises; the verifier returns
  `INSUFFICIENT_EVIDENCE`, not a fabricated success.
- Two *different relying parties* can separately rely on the same
  evidence. The relying-party identity and scope MUST be stable and
  externally governed, not client-selected per request.
- The ledger holds recorded acceptance reservations, not signed approval
  keys, full receipts or proof of actual provider state.

## Limitations that block payment/deployment usage

1. The database is local SQLite. **No distributed multi-host consistency,
   replicated disaster recovery or NFS/network filesystem guarantee**
   has been established.
2. A unique reservation is not the same as once-only external execution.
   There is no provider idempotency, result delivery, or settlement atomicity.
3. Retried requests cannot automatically recover the original ACCEPT
   response. A separately authenticated readback receipt/status design
   would be required for operational idempotence.
4. Signed record correctness still depends on independently pinned keys and
   a trustworthy observer. The ledger only prevents local duplicate acceptance.
5. Authorization freshness at verification time is unchanged. This remains
   unsuitable for general historical audit without a separate policy.
6. Only source-created, local synthetic concurrency and restart tests exist.
   Process concurrency, power-loss, corruption, filesystem permissions,
   distributed locks, tenant/identity spoofing, and backup/restore remain
   independent release gates.
7. Protect the SQLite file, directory and backups; even minimal event IDs
   and relying-party identities can be sensitive operational metadata.
8. No external buyer or independent reviewer has approved the protocol.

## Test

```sh
python -m unittest tests.test_acceptance_ledger tests.test_reliance_gate -v
python -m unittest discover -s tests -v
```

## Next build gate

Use an **authenticated, read-only GitHub observer** that records the exact
approved repository/PR/head and re-reads the provider's actual merged head
or merge outcome. Compare this optional relying-party ledger against GitHub
rulesets, required reviews, audit events, and existing independently operated
verification services. Measure incremental refusal utility and overhead.

**Do not market this as a universal double-spend prevention protocol.**

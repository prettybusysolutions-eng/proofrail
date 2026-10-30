# ProofRail Reliance Gate — Portable Acceptance Prototype

**Status:** experimental, review-only. Not a new standard, not production security,
not external attestation, and not a guarantee of real-world outcomes.

## The wedge: buyer-side consequence acceptance

Keep identity providers (e.g. Okta), authorization engines (e.g. OPA, Cedar,
Permit.io), agent runtimes, tool servers, and provider APIs in place.

Add a *relying-party* contract to answer a narrower question:
"Do these two separately signed records support treating this exact claimed
action as having been authorized and recorded as applied?"

The `proofrail.reliance.assess_reliance` function verifies ProofRail-style
RFC 8785 canonical JSON/Ed25519 signatures using externally supplied, pinned
public keys. It checks buyer-selected identities, key IDs, intended effect,
expiration, exact authorization digest, claimed provider and event ID,
recorded action outcome, and chronology.

The response `ACCEPT_RECORDED_OUTCOME` proves only that two *externally
pinned signers* signed consistent records of what was authorized and what an
observer claimed. It does not prove the provider event truly occurred,
that the two organizations are operationally independent, or that the
signatures are anchored in an independent transparency service.

## Omnidirectional integration positions

| Position | Existing participant | Potential ProofRail attachment |
|---|---|---|
| **Above** | Buyer, auditor, insurer, marketplace, customer | Accept/refuse supplied evidence before accepting contractual completion |
| **Below** | Protected API gateway, merge endpoint, payment workflow | Enforce a separate single-use ProofRail authority *before* mutation |
| **Between** | Identity engine → agent → tool → provider → buyer | Normalize provider decisions and observed outcomes into bound signed records |
| **Across** | Multiple firms and platforms | Exchange portable records with independently pinned keys and observer identities |

**This prototype only implements the above/between OFFLINE acceptance
decision.** It does not implement adapter ingestion, protected API enforcement,
payment release, agent delegation, independent logging, or production retries.

## Minimal developer example

```python
from datetime import datetime, timezone
from proofrail.reliance import assess_reliance

decision = assess_reliance(
    authorization=signed_grant,      # signed normalized record, not a raw OPA allow boolean
    observation=signed_observation,  # signed by separately pinned provider-side observer
    authority_key=trusted_issuer_public_key,
    observer_key=trusted_observer_public_key,
    authority_principal="issuer-from-external-trust-policy",
    authority_key_id="trusted-issuer-key",
    observer_principal="observer-from-external-trust-policy",
    observer_key_id="trusted-observer-key",
    expected_effect={"action_type": "github_merge",
                     "target": "example-org/service#123",
                     "request_digest": "d" * 64},
    expected_provider="github",
    now=datetime.now(timezone.utc),
)
# decision["accepted"] is false unless both signatures and context match.
```

The illustrative `signed_grant` and `signed_observation` must be genuine
signed records. A vendor's unsigned decision log alone is not an acceptable
authorization and should not be relabeled as one.

## Execute tests

```sh
python -m unittest tests.test_reliance_gate -v
```

Positive and negative test inputs are generated in memory with temporary keys.
No live cloud API, production actor identity, buyer transaction, or external
service is exercised.

## Critical integration barriers

1. **Vendor-neutral does not mean natively integrated.** A partner must
   implement a trusted adapter that authenticates and binds its actual decision
   to the normalized authorization record, rather than self-signing a claim
   without evidence.
2. **A provider observer must be credible.** A mere independently generated
   keypair proves two cryptographic keys exist, not independent operator control.
3. **Trust distribution is out of band.** Import or pin the correct keys,
   identities and key IDs from a source other than the receipt package.
4. **One-time execution is separate.** Do not use this verifier to authorize
   a write; use an enforcing provider adapter with replay protection and
   current-state checks.
5. **Verification is not transaction settlement.** Event IDs here are
   signed claims, not independently fetched provider identifiers.
6. **Reconciliation is time-sensitive.** A receipt may remain valid as
   historical evidence after the grant expires, but the v0 evaluator requires
   the authorization to be current at evaluation time. This strict behavior
   limits retrospective use and must be redesigned for auditing historical actions.
7. **Retention, privacy and anti-equivocation are absent.** SCITT RFC 9943
   and COSE Receipts RFC 9942 offer standards for transparency, but no
   transparency-service registration or signed inclusion proof is implemented.
8. **No commercial adoption is established.** No client, integration partner,
   paid license, independent reviewer, latency benchmark or business valuation.

## Existing specifications and integration context

- [SCITT architecture, RFC 9943](https://datatracker.ietf.org/doc/html/rfc9943)
- [COSE Receipts, RFC 9942](https://datatracker.ietf.org/doc/html/rfc9942)
- [Agent permission receipts (Internet-Draft; October 2026)](https://datatracker.ietf.org/doc/html/draft-izmaylov-agent-permission-receipts-01)
- [AI-agent action receipt SCITT draft](https://datatracker.ietf.org/doc/html/draft-noa-scitt-ai-agent-receipt-01)

These specs are not interchangeable; this module does not claim compliance
with those receipts or wire formats. A future adapter should use their
actual encodings and independently authored conformance tests.

## Commercial experiment

Ask a security, automation, or assurance platform:
"Would you require this exact proof before trusting an external AI-initiated
change or paying for a work outcome?"

The gate is **one documented purchase-order or platform requirement**
where a receiving party agrees to verify pinned evidence and will fund
an implementation, not an aspirational 'global OS' claim.

Do not publish the module as generally trusted, move it to main, or sell it
as an integrated service without independent review and provider-side trials.

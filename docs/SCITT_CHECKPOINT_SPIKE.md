# SCITT compatibility spike — ProofRail checkpoint statements

Status: **offline prototype only**. This is not a transparent statement, a
registration client, a SCITT receipt, or an RFC 9943 conformance certification.

## Architecture decision

Use RFC 9943's SCITT architecture and existing transparency services for
publication and independent retention, rather than creating a ProofRail-only
witness network. Keep ProofRail focused on the controls that signed logging
does not supply: legitimate approval, single-use consumption, provider-side
enforcement and post-execution reconciliation.

SCITT RFC 9943 was published June 2026 and is a standards-track document.
It mandates protected COSE_Sign1 CWT Claims `iss`/`sub`; signed statements
are distinct from transparency-service-issued receipts. A signed statement
authenticates a *claim*, not the accuracy of the claim.

An actively revised individual Internet-Draft,
`draft-noa-scitt-ai-agent-receipt-01` (August 2026), is adjacent and merits
interoperability comparison before designing another action-receipt format.

## What this spike constructs

`proofrail/scitt_checkpoint.py` exports one RFC 9943-style signed statement:
CBOR tag 18 (COSE_Sign1), EdDSA (-8), protected content type
`application/vnd.proofrail.checkpoint+json` (experimental and not a registered
media type), protected key identifier, CWT Claims map 15 with issuer and subject
labels 1 and 2, and an RFC 8785 canonical JSON payload.

The payload binds the ProofRail **signed Merkle checkpoint digest**, and
independent commitments to authority, consumption and reconciliation, an
execution domain, sequence, and expected prior checkpoint digest.

The offline verifier requires externally provisioned issuer signing key,
checkpoint key, issuer/subject identifiers, key identifier and exact expected
claims; it verifies COSE signature, checkpoint signature and checkpoint
commitment against the original ledger. Hash-chain truncation is detected
*only* against the retained checkpoint, and does not prove external retention.

## What is deliberately not built

- No network call or SCITT service registration; no VDS receipt or inclusion
  proof, consistency proof, history query, third-party custody or watcher.
- No representation that digest commitments by themselves prove approvals,
  prevention of replay, or real provider-side effects.
- No assumed interoperability with a particular SCITT registration API,
  transparency-service acceptance policy or registered media type.
- No publication of customer information, keys or incident evidence.

## Exit test

Next, independently deploy the signature and checkpoint verifier in a second
implementation. Then produce a signed statement over a **real, redacted,
permissioned** ProofRail action; submit it to a third-party SCITT transparency
service only with operator approval; obtain and independently verify a genuine
SCITT receipt and a later consistency proof; show that rolling back local
state cannot erase the externally published checkpoint.

Finally, demonstrate that the *separate* ProofRail authority/consumption/
reconciliation evidence is sound under independent review. Notarization does
not make false issuer assertions correct.

References:
- https://www.rfc-editor.org/rfc/rfc9943
- https://www.rfc-editor.org/rfc/rfc9052
- https://datatracker.ietf.org/doc/draft-noa-scitt-ai-agent-receipt/

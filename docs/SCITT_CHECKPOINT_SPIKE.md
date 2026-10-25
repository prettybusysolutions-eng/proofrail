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
CBOR tag 18 (COSE_Sign1), Ed25519 (-19, RFC 9864), protected content type
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

## Algorithm migration and independent COSE interoperability

New statements use the fully specified RFC 9864 **Ed25519 (-19)** identifier.
The verifier can accept deprecated **EdDSA (-8)** only under a configurable
legacy migration policy (allow_legacy_eddsa=True by default; pass False to
reject it). Signing legacy -8 requires an explicit algorithm=-8 argument.
Check the chosen transparency service actually accepts -19 before publishing.

The author-side review found two-way interoperability for the *legacy -8*
form with pycose 1.1.0 in an environment with cbor2 5.6.5. This pycose
version does not recognize -19 and fails to decode *any* COSE message with
cbor2 6.x due to decoded CBOR array representation changes. Keep pycose's
old dependency pins isolated from ProofRail's normal cbor2 5.x/6.x support.

~~~sh
python3.11 -m venv /tmp/proofrail-pycose-interop
/tmp/proofrail-pycose-interop/bin/python -m pip install -e . -r requirements/interop-pycose.txt
/tmp/proofrail-pycose-interop/bin/python scripts/check_scitt_pycose.py
~~~

Independent pycose agreement on legacy encoding does **not** prove a real
SCITT transparency service accepts the newly emitted -19 format.

## Receipts attached after registration (RFC 9942)

The issuer-signed COSE_Sign1 may have exactly one unprotected header
parameter: integer label **394**, containing a nonempty array of
CBOR-encoded COSE receipt bytes. The verifier now accepts bounded receipts
with the expected outer COSE structure; rejects unknown unprotected fields
and malformed attachments; and never promotes receipt presence into proof.

**Important:** verify_scitt_checkpoint_statement is still an **issuer
signature and local checkpoint verifier**, not an RFC 9942 receipt verifier.
Even if a signed statement with attached receipts returns valid=True,
transparency_receipt_verified always remains false. Calling it with
require_transparency_receipt=True fails closed until a real receipt verifier
is implemented. A separate implementation must verify every receipt's
transparency-service signature and VDS/VDP inclusion or consistency proof
against a separately trusted service key. Changing an unprotected receipt
does not invalidate the issuer signature; this is expected.

## Rolled-back statements can have legitimate old receipts

An old statement can be correctly signed and included in a transparency log
despite a later checkpoint being registered. The signature and inclusion
receipt cannot prove which checkpoint is the latest.

For *offline equality with a caller-pinned tip*, pass pinned_latest to the
verification function, containing exactly:

~~~json
{
  "issuer": "urn:proofrail:issuer:example",
  "subject": "urn:proofrail:stream:customer-a",
  "execution_domain": "github:owner/repo",
  "sequence": 2,
  "checkpoint_digest": "<64-character lowercase SHA-256 digest>"
}
~~~

This value must come from an **independently authenticated latest-state
source**, not from the presented statement or its bundle. The routine
refuses mismatched sequence, digest or scope, but intentionally reports
externally_verified_latest_log_state_proven=false: it does not establish
whether the caller's pinned tip is real, consistent or current.

**SCITT does not mandate a general "latest record for issuer+subject"
query.** A real deployment needs an authenticated monitor/index that
tracks the entire relevant registration stream, verifies SCITT receipts and
append-only consistency, and retains monotonic state outside the issuer's
control. Choose a transparency service only after confirming a supported
history query / monitor route. Use a **stable CWT subject for the checkpoint
stream**; changing the subject on every checkpoint breaks that comparison.

The local rollback regression uses an old COSE statement with a *structural,
unverified placeholder receipt* and an independently supplied fixture tip
for the later checkpoint. It proves the expected-value guard works; it
does not demonstrate authentic receipt verification, service "latest" API,
or external checkpoint custody.

## What is deliberately not built

- No network call or SCITT service registration; no **verified** VDS receipt
  or inclusion/consistency proof, authenticated latest-state query,
  third-party custody or watcher.
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

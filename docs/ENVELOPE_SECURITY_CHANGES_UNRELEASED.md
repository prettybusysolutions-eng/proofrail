# Unreleased compatibility note: Action Authority Envelope v1

Status: **proposed security hardening on draft PR #44**. This document is not a release announcement or evidence of independent security certification.

## New verifier behavior

The existing `verify_action_authority_envelope` call remains usable with the original parameters. Three **optional** trusted expectations can additionally be supplied: `expected_issuer`, `expected_subject`, and `expected_key_id`. These must be obtained from an authenticated authorization context; reading them from the untrusted envelope does not create a trust boundary.

Regardless of whether these optional values are provided, verification now rejects:
- an issuer role that is not in `PERMIT_ISSUER_ROLES`;
- an envelope with `issued_at` in the future;
- a validity window with `expires_at <= issued_at`;
- an expired envelope;
- malformed timestamps, timezone-naive timestamps and timestamps outside the enforced RFC3339 form.

Minting an envelope with a timezone-naive string for `expires_at` also fails. Existing valid envelopes produced by `mint_action_authority_envelope` satisfy these constraints, but historically tolerated invalid inputs no longer do. Treat this as an intentional **behavior change**, not a purely opt-in security feature.

## Bundled contract location

The validator reads `proofrail/authority_schemas/action_authority_envelope.schema.json` from package data inside ProofRail. The top-level `schemas/action_authority_envelope.schema.json` remains distributed for existing tooling and publication; a project-authored test asserts the two copies are identical. The installed-wheel CI exercises schema loading outside the checkout to check packaging correctness.

## Not established by this change

Optional identity expectations do **not** authenticate historical signing keys on their own. A caller must independently trust those keys or validate a signed history/rotation path. This change does not independently prove consumption, remote provider authorization, multi-store rollback resistance, physical outcomes, or third-party review.

## Integration/release gates

Before shipping, update consumers to pass externally trusted identity expectations where needed; reconcile the overlapping earlier drafts #42/#43; run both the core and facility-pilot test suites against the *combined* commit; and write the actual changelog/release entry for the version that contains the merge. No release has been created by this PR.

# Provider-owned authorization mode (experimental)

The local work-order simulator has two distinct modes:

- **Default demo/fault mode**: accepts work-order POST requests without
  validating ProofRail signatures. This is intentionally insecure and
  must not be used to claim non-bypassable authorization.
- **Configured enforcement mode**: start with `--enforce-authority PATH`
  where PATH is an operator-provisioned JSON file containing separately
  trusted `issuers` and `gateways` maps. Entries are indexed by
  principal ID and provide `tenant_id`, `key_id`, and the base64-encoded
  Ed25519 `public_key`. Never populate trust from a request header.

The gateway sends the signed Action Authority Envelope and a signed
post-consumption registry attestation as base64 JSON headers. The enforcing
provider validates key bindings, tenant, exact parameters, operation target,
signatures, and the authority time window before creating an order. Provider
storage enforces idempotency on the work-order key.

The simulator's administrative fault/status endpoints are disabled in
enforcement mode. This remains a localhost test provider with unverified
provider-integration semantics and is not a hardened production service.

## Claim limits

A gateway-signed consumption attestation authenticates the gateway's
statement about its locally committed claim. It is **not** an independently
retained replay checkpoint. This mode does not yet prove independent
checkpoint durability, revocation fencing, secure key custody, or
production-grade vendor enforcement. The first implementation is a draft
requiring full provider-side negative tests and an independent review
before any non-bypassability claim.

The default unconfigured simulator remains an intentionally insecure
fault-injection environment. Never treat its green CI results as evidence
of provider-side enforcement.

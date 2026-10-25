# Provider-enforced work-order authorization (pilot)

Status: opt-in **local simulator security mode**, draft PR #55. Not a production
provider integration, independent assurance, replay checkpoint, or proof of a
real-world work order.

## Problem

The original simulated provider checked only an idempotency header and a
client-name header. Another HTTP caller could create a work order without
passing through ProofRail's gateway. Gateway-only admission checks are not a
provider-side trust boundary.

## Enforced simulator mode

Supply `--trusted-gateways trusted-gateways.json` when launching
`provider_simulator.py`. The JSON file must be provisioned through a
**separate, trusted operator channel**; it is not accepted from request headers
or exported bundles.

Example shape (identifiers and key data are placeholders):

```json
{
  "tenant-a": {
    "principal_id": "gateway-a",
    "key_id": "key-gateway-a",
    "public_key": "<independently authenticated Base64 Ed25519 public key>"
  }
}
```

When configured, `POST /v1/tenants/{tenant}/work-orders` requires a signed
`X-ProofRail-Capability` token from the pinned tenant gateway. The provider
checks the Ed25519 signature and signed hash, exact method, path, tenant,
principal, header client identity, idempotency key, canonical request digest,
and a short wall-clock validity interval **before any work-order write**. A
missing, forged, mismatched or expired token is rejected with 403.

The gateway constructs the token after local ProofRail permit consumption and
its gateway-signed consumption receipt have been persisted. Each successful
repeat of an identical signed request returns the *same* idempotent work
order; it never creates a second order. Fault-injection/admin mutation POST
endpoints are disabled when enforcement is enabled.

Startup must select **exactly one mode**. Provide `--trusted-gateways`
for provider authorization, or explicitly supply `--insecure-fault-mode` for
local failure-injection tests. With neither option, the server refuses to
start. The pre-existing synthetic test fixtures explicitly choose the insecure
mode to preserve fault scenarios. **Never deploy that testing mode as an
authorization boundary.**

## What this establishes

Tests cover actual localhost HTTP POST requests with no token, invalid
signatures, cross-tenant requests, changed client identity, idempotency-key
mismatch, changed requested parameters, expiry, and legitimate signed
gateway requests following normal permit consumption.

This narrows the direct caller-bypass problem for a **trusted gateway signer
and configured simulator**. It does **not** prove the gateway honestly checked
or retained the underlying ProofRail permit: a compromised authorized
gateway key could sign a capability without legitimate prior consumption.
External checkpointing and real provider-owned independent permit validation
remain separate gates.

## Remaining deployment requirements

- Authenticated TLS transport and replay-safe operational credentials.
- Independent key custody, provisioning, rotation and revocation procedures.
- Production authorization and tenant ownership model at the real provider.
- Clock-skew policy, rate limits, request size limits, audit retention, secure
  error handling and independent provider observation.
- Atomic and durable rollback-resistant consumption checkpoints retained
  outside both the gateway and its local databases.
- An authenticated admin control plane rather than the intentionally disabled
  simulator's test-only admin routes.
- Third-party review, real provider adapters and external reproduction.

This PR does not send money, access a live provider, or approve production use.

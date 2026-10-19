# Emergence Layer — SMATP v0.1 reference implementation

Hosted as an isolated ProofRail research module. Read
[PROOFRAIL_BOUNDARY.md](PROOFRAIL_BOUNDARY.md) before interpreting its results
or integrating its recovery behavior with ProofRail.

## Counterfactual execution lab extension

The original wire protocol is preserved. `counterfactual_lab.py` adds controlled
execution experiments, not a production worker or a new protocol version.
Read `DISCOVERY.md` for the hypothesis, results, limitations, and next build.

```bash
python -m pip install ../..
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/
python counterfactual_lab.py --output counterfactual_results.json
```

Four execution designs run against six identical failure schedules (24 cells).
Each cell uses separate local execution and destination databases and launches
two real subprocesses. Injected crashes call `os._exit(73)`. Destination
verification reads actual committed fixture state and binds its digest into
the existing signed completion receipt. False acknowledgments and wrong outputs
remain unconfirmed in the verified arm. No external service or AI model is used.

## ProofRail acceptance bridge

`acceptance_bridge.py` now verifies an SMATP handoff against ProofRail's existing
signed Action Authority Envelope and a pinned acceptance contract. It requires
the authority's existing `success_predicate_digest` to commit to that contract.
See [ACCEPTANCE_BRIDGE.md](ACCEPTANCE_BRIDGE.md) for trust inputs, result meanings,
tests, and the execution boundary. This is a read-only verifier, not a dispatcher.

## Execution attribution extension

`execution_binding.py` adds a separate, experimental local consumption ledger,
one-dispatch boundary, and transactional SQLite artifact destination. Its
execution verifier requires destination-recorded run identity and a digest of
the consumed authority record. See [EXECUTION_ATTRIBUTION.md](EXECUTION_ATTRIBUTION.md)
for the reproduced two-run counterexample, mutation control, and crash results.
The follow-up now shares ProofRail's replay-table format and uniqueness boundary
when configured with the same registry file. See [LIVE_GITHUB.md](LIVE_GITHUB.md)
for bidirectional replay tests and a completed real GitHub artifact-write trial.
No deployed registry was migrated. Checkpoint-bearing authority is rejected.

**Status: local prototype, not a production-ready protocol or new standard.**

Replaces the claimed token-interception/vector-bus bootstrap with a concrete, permissioned agent handoff and verifiable receipt ledger. Preserves authorization and continuity *between* agents, not hidden LLM reasoning.

## What is implemented

- Ed25519-signed JSON envelopes; explicit agent/key enrollment (operator controlled)
- Timestamp bounded messages with UUID/nonce and per-sender idempotency keys
- Durable SQLite ledger, WAL, atomic state transitions and repeat-request handling
- Ed25519-signed recipient receipts chained by cryptographic hashes
- Explicit lifecycle: `RECEIVED → ACCEPTED → COMPLETED|FAILED|REJECTED`, or `RECEIVED → REJECTED`
- Replay/tampering/unauthorized actor checks
- Loopback-only HTTP transport (`/v1/messages`, `/v1/receipts`, `/v1/messages/{id}`)
- Offline regression tests for persistence, signature failures, replay, concurrent duplicates, corruption, state machine and actual loopback HTTP handoff

## Run

Python 3.11+:

```bash
pip install -r requirements.txt
python demo.py
python -m pytest -q tests/
python server.py --db ./emergence.sqlite3 --port 8765
```

`demo.py` enrolls two temporary identities, sends and acknowledges a message, signs a completion receipt with the recipient key, closes the database, reopens it and verifies the persisted evidence chain.

`server.py` is a developer-only loopback HTTP service. Keys must be enrolled via the local `Store.register_agent()` operator interface before sending. `GET /v1/messages/{id}` is **not authenticated**, so **do not deploy it on a public network**. For testing local HTTP, create envelopes/receipts using the SDK and POST as JSON. This is not an MCP/A2A replacement; an A2A adapter would be the next interoperability step.

## Core schema

Envelope signed fields:

```json
{"version":"smatp/0.1","message_id":"uuid","sender":"agent-id","recipient":"agent-id","sender_key_id":"fingerprint","capability":"name","payload":{},"created_at":0,"expires_at":0,"nonce":"random","idempotency_key":"client-key"}
```

The `signature` (base64 Ed25519) is computed over canonical JSON of all fields above. A receipt similarly signs the `message_id`, `actor`, `decision`, `result`, `previous_receipt_hash`, and timestamp. Receipts assert **what the recipient signed**, not independently proven real-world execution.

## Production gates — NOT complete

1. Mutual TLS or authenticated transport with authorization and per-tenant isolation, including authenticated reads.
2. Trust-store lifecycle: enrollment approvals, key rotation, revocation, and historical verification.
3. Postgres/event-log scalability, retention/export, metrics, rate limiting and malicious payload handling.
4. Bind `COMPLETED` to independently checked external side effects and ProofRail-style attestations; avoid equating a self-reported result with ground truth.
5. Signed capabilities and policy enforcement, actor-to-resource mapping and explicit approval gates for hazardous side effects.
6. Native A2A/MCP integration and cross-organizational interoperability testing.
7. Worker leases, distributed execution recovery, timeouts, dead-letter queues and outbox pattern for exactly-once **effect** claims. Current idempotency ensures one accepted record, not exactly-once external execution.
8. Performance/load testing across hosts and multiple organizations; no sub-millisecond or scale claims validated.

## Commercial positioning

The candidate differentiator is a neutral *verified handoff and recovery* layer, not a semantic monopoly. Pilot on one paid workflow where agent actions cross a trust boundary. Demonstrate receipt validation, recovery after restart, latency added, avoided errors and a verifiable customer saving before setting revenue expectations.

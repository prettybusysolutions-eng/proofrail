# ProofRail MCP Authority Profile v1

This profile places a consequential MCP tool call behind a ProofRail Action
Authority Envelope without making MCP transport or discovery part of the
authority root.

## Call Binding

An authorized MCP call uses:

- `action_type`: `mcp.tool_call`
- `target`: `mcp://<server_id>/<tool_name>`, binding the authority to one MCP
  server as well as one tool (`mcp_target()`)
- `parameters`: the complete MCP arguments object
- `effect_digest`: the canonical digest of those three fields

The tool adapter receives the envelope digest as its idempotency key.

## Trusted State

The middleware is constructed with its `server_id` and a `trusted_state`
provider: a server-side function that returns the current roots and approval
digest for the effect the server computes from its own target and the frozen
arguments. Callers of `invoke()` cannot supply roots or approvals; an envelope's
own roots are never accepted as current. The middleware verifies the envelope
against that state, then calls the provider again inside the consumption
store's atomic section: a revocation, policy change or withdrawn approval
committed after verification denies the call
(`state_changed_before_consumption`, `approval_changed_before_consumption`)
before the tool runs. A provider that fails or returns malformed state denies
the call (`trusted_state_unavailable`).

## Consumption

Authority is spent atomically by digest and nonce in a `ConsumptionStore`
before the tool is called. `SQLiteConsumptionStore` is the default. Every
replica of one server must use the same store: separate stores make authority
single-use per replica rather than per server. Different servers are already
separated by the `server_id` in the target.

## Result Binding

Adapter execution must return `proofrail.adapter-receipt.v1`. Independent
observation must return:

```json
{
  "contract": "proofrail.observation-receipt.v1",
  "effect_digest": "<authorized effect digest>",
  "status": "success|failed|unknown",
  "confirmations": 1,
  "evidence": {}
}
```

Success is established only when the observation contract confirms the exact
effect. A tool timeout, unknown adapter outcome, failed observation, or adapter
success contradicted by observation becomes `reconciliation_failed`. Spent
authority is never restored.

## Reference Middleware

`integrations/mcp/middleware.py` is provider-neutral. It demonstrates:

- exact tool and argument binding;
- server binding in the effect target;
- identity, evidence, policy, state and approval roots from trusted
  server-side state, rechecked inside the consumption transaction;
- atomic single-use consumption before execution, shareable across replicas;
- adapter receipt validation;
- observation before success;
- replay, stale-state, parameter expansion, timeout ambiguity, and false
  success denial.

## Portable Artifact

The committed `examples/mcp-reference-artifact/` bundle contains deterministic,
signed verdicts for the six reference scenarios.

```bash
python scripts/generate_mcp_reference_artifact.py \
  --verify examples/mcp-reference-artifact
```

Exit `0` means the signature and regenerated scenario verdicts match. Exit `4`
means the artifact differs.

This artifact is independently reproducible, but it is not evidence that an
outside evaluator has reproduced it. That remains Gate 2's external exit
condition.

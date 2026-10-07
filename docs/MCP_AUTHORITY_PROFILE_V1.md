# ProofRail MCP Authority Profile v1

This profile places a consequential MCP tool call behind a ProofRail Action
Authority Envelope without making MCP transport or discovery part of the
authority root.

## Call Binding

An authorized MCP call uses:

- `action_type`: `mcp.tool_call`
- `target`: the exact MCP tool name
- `parameters`: the complete MCP arguments object
- `effect_digest`: the canonical digest of those three fields

The tool adapter receives the envelope digest as its idempotency key. The
middleware verifies the signed envelope and current roots, then atomically
spends its digest and nonce before calling the tool.

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
- current identity, evidence, policy, state, and approval roots;
- atomic single-use consumption before execution;
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

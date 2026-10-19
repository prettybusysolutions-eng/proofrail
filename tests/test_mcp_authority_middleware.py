import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrations.mcp.middleware import MCPAuthorityMiddleware
from proofrail.envelope import mint_action_authority_envelope


ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL = "5" * 64


class ToolAdapter:
    def __init__(self, status="success", timeout=False):
        self.calls = 0
        self.status = status
        self.timeout = timeout

    def execute(self, tool_name, arguments, *, idempotency_key):
        self.calls += 1
        if self.timeout:
            raise TimeoutError("tool boundary timed out")
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "provider:operation-1",
            "status": self.status,
            "side_effect_confirmed": self.status == "success",
            "retry_safe": False,
            "receipt_evidence": {"provider_request_id": "request-1"},
        }


class InvalidAdapter:
    def execute(self, tool_name, arguments, *, idempotency_key):
        return {"status": "success"}


class Observer:
    def __init__(self, status="success"):
        self.status = status

    def observe(self, tool_name, arguments, *, adapter_receipt, effect_digest):
        return {
            "contract": "proofrail.observation-receipt.v1",
            "effect_digest": effect_digest,
            "status": self.status,
            "confirmations": 1,
            "evidence": {"provider_state_digest": "6" * 64},
        }


class MCPAuthorityMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.arguments = {"ticket_id": "INC-42", "state": "closed"}

    def envelope(self):
        return mint_action_authority_envelope(
            roots=ROOTS,
            approval_digest=APPROVAL,
            action_type="mcp.tool_call",
            target="support.close_ticket",
            parameters=self.arguments,
            subject_principal_id="agent:operator",
            subject_role="executor",
            issuer_principal_id="verifier:primary",
            issuer_role="verifier",
            adapter_contract={
                "name": "proofrail.adapter-receipt",
                "version": "v1",
                "idempotency_required": True,
            },
            observation_contract={
                "name": "proofrail.provider-observation",
                "version": "v1",
                "minimum_confirmations": 1,
                "success_predicate_digest": "7" * 64,
            },
            nonce="mcp-authority-nonce-0001",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            private_key=self.private_key,
            key_id="verifier-key",
        )

    def middleware(self, directory, adapter=None, observer=None):
        return MCPAuthorityMiddleware(
            state_db=Path(directory) / "mcp-authority.sqlite3",
            adapter=adapter or ToolAdapter(),
            observer=observer or Observer(),
            issuer_public_key=self.public_key,
        )

    def invoke(self, middleware, envelope, arguments=None, roots=None):
        return middleware.invoke(
            tool_name="support.close_ticket",
            arguments=arguments or self.arguments,
            envelope=envelope,
            expected_roots=roots or ROOTS,
            expected_approval_digest=APPROVAL,
        )

    def test_success_requires_valid_authority_consumption_and_observation(self):
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory), self.envelope())
        self.assertEqual(result.status, "success")
        self.assertEqual(result.reason, "observed_success")

    def test_mutated_parameters_are_denied_before_tool_execution(self):
        adapter = ToolAdapter()
        with TemporaryDirectory() as directory:
            result = self.invoke(
                self.middleware(directory, adapter=adapter),
                self.envelope(),
                arguments={**self.arguments, "notify_customer": True},
            )
        self.assertEqual(result.reason, "parameters_changed")
        self.assertEqual(adapter.calls, 0)

    def test_stale_state_is_denied_before_tool_execution(self):
        adapter = ToolAdapter()
        with TemporaryDirectory() as directory:
            result = self.invoke(
                self.middleware(directory, adapter=adapter),
                self.envelope(),
                roots={**ROOTS, "state": "8" * 64},
            )
        self.assertEqual(result.reason, "state_root_changed")
        self.assertEqual(adapter.calls, 0)

    def test_replay_is_denied_after_single_execution(self):
        adapter = ToolAdapter()
        with TemporaryDirectory() as directory:
            middleware = self.middleware(directory, adapter=adapter)
            envelope = self.envelope()
            first = self.invoke(middleware, envelope)
            second = self.invoke(middleware, envelope)
        self.assertEqual(first.status, "success")
        self.assertEqual(second.reason, "authority_already_consumed")
        self.assertEqual(adapter.calls, 1)

    def test_timeout_is_ambiguous_and_authority_remains_spent(self):
        adapter = ToolAdapter(timeout=True)
        with TemporaryDirectory() as directory:
            middleware = self.middleware(directory, adapter=adapter)
            envelope = self.envelope()
            first = self.invoke(middleware, envelope)
            second = self.invoke(middleware, envelope)
        self.assertEqual(first.reason, "ambiguous_tool_timeout")
        self.assertEqual(second.reason, "authority_already_consumed")
        self.assertEqual(adapter.calls, 1)

    def test_false_success_is_denied_by_independent_observation(self):
        with TemporaryDirectory() as directory:
            result = self.invoke(
                self.middleware(directory, observer=Observer(status="failed")),
                self.envelope(),
            )
        self.assertEqual(result.status, "reconciliation_failed")
        self.assertEqual(result.reason, "false_success_denied")

    def test_unknown_observation_is_ambiguous(self):
        with TemporaryDirectory() as directory:
            result = self.invoke(
                self.middleware(directory, observer=Observer(status="unknown")),
                self.envelope(),
            )
        self.assertEqual(result.status, "reconciliation_failed")
        self.assertEqual(result.reason, "ambiguous_observed_outcome")

    def test_invalid_adapter_receipt_is_ambiguous_and_spent(self):
        with TemporaryDirectory() as directory:
            middleware = self.middleware(directory, adapter=InvalidAdapter())
            envelope = self.envelope()
            first = self.invoke(middleware, envelope)
            second = self.invoke(middleware, envelope)
        self.assertEqual(first.status, "reconciliation_failed")
        self.assertEqual(first.reason, "adapter_error_ambiguous:ProofRailError")
        self.assertEqual(second.reason, "authority_already_consumed")

    def test_signed_envelope_mutation_is_denied(self):
        envelope = copy.deepcopy(self.envelope())
        envelope["effect"]["target"] = "support.delete_ticket"
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory), envelope)
        self.assertEqual(result.reason, "invalid_envelope")

    def test_mapping_that_changes_between_reads_cannot_swap_the_effect(self):
        # Review of #1: verification read INC-42/closed, execution read INC-1/deleted.
        from collections.abc import Mapping

        authorized, swapped = dict(self.arguments), {"ticket_id": "INC-1", "state": "deleted"}

        class Shifting(Mapping):
            """Consistent within each full pass; swaps contents after the first pass."""

            def __init__(self):
                self.passes = 0
                self.view = authorized

            def __iter__(self):
                self.view = authorized if self.passes == 0 else swapped
                self.passes += 1
                return iter(self.view)

            def __getitem__(self, key):
                return self.view[key]

            def __len__(self):
                return len(self.view)

        recorder = RecordingAdapter()
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory, adapter=recorder),
                                 self.envelope(), arguments=Shifting())
        # Authorized once, then executed exactly as authorized.
        self.assertEqual(result.status, "success")
        self.assertEqual(recorder.seen, [authorized])

    def test_nested_mutation_after_verification_does_not_reach_the_tool(self):
        self.arguments = {"ticket_id": "INC-42", "state": "closed", "recipients": ["a@x"]}
        envelope = self.envelope()
        arguments = copy.deepcopy(self.arguments)

        class MutateAfterVerify(ToolAdapter):
            def execute(inner, tool_name, args, *, idempotency_key):
                arguments["recipients"].append("attacker@evil")  # caller-held object
                inner.seen = copy.deepcopy(args)
                return super().execute(tool_name, args, idempotency_key=idempotency_key)

        adapter = MutateAfterVerify()
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory, adapter=adapter), envelope,
                                 arguments=arguments)
        self.assertEqual(result.status, "success")
        self.assertEqual(adapter.seen["recipients"], ["a@x"])

    def test_adapter_mutating_its_copy_cannot_change_what_the_observer_checks(self):
        class Mutating(ToolAdapter):
            def execute(inner, tool_name, args, *, idempotency_key):
                args["state"] = "deleted"
                return super().execute(tool_name, args, idempotency_key=idempotency_key)

        class Watching(Observer):
            def observe(inner, tool_name, args, **kwargs):
                inner.seen = dict(args)
                return super().observe(tool_name, args, **kwargs)

        authorized = copy.deepcopy(self.arguments)
        observer = Watching()
        with TemporaryDirectory() as directory:
            self.invoke(self.middleware(directory, adapter=Mutating(), observer=observer),
                        self.envelope(), arguments=copy.deepcopy(self.arguments))
        self.assertEqual(observer.seen, authorized)

    def test_non_mapping_envelope_is_denied_not_raised(self):
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory), "not-an-envelope")
        self.assertEqual((result.status, result.reason), ("denied", "invalid_envelope"))


    # Second review of #1: inputs the canonical snapshot must handle.

    def test_cyclic_arguments_are_denied_not_raised(self):
        cyclic = {"ticket_id": "INC-42"}
        cyclic["self"] = cyclic
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory), self.envelope(), arguments=cyclic)
        self.assertEqual((result.status, result.reason), ("denied", "non_canonical_input"))

    def test_signed_large_float_round_trips_and_executes(self):
        # Previously denied as invalid_envelope: 1.2345678901234568e20 is written
        # canonically as 123456789012345680000 and decoded back as an int.
        self.arguments = {"ticket_id": "INC-42", "amount": 1.2345678901234568e20}
        recorder = RecordingAdapter()
        with TemporaryDirectory() as directory:
            result = self.invoke(self.middleware(directory, adapter=recorder), self.envelope())
        self.assertEqual(result.status, "success", result.reason)
        self.assertEqual(recorder.seen, [self.arguments])


class RecordingAdapter(ToolAdapter):
    def __init__(self):
        super().__init__()
        self.seen = []

    def execute(self, tool_name, arguments, *, idempotency_key):
        self.seen.append(copy.deepcopy(dict(arguments)))
        return super().execute(tool_name, arguments, idempotency_key=idempotency_key)


if __name__ == "__main__":
    unittest.main()

"""SubprocessAdapter against real child processes, through the real bridge.

Each test runs an actual program with an observable side effect (a file on
disk), so outcomes are checked against what the process really did.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from integrations.openclaw.bridge import AdapterRegistry, OpenClawProofRailBridge, SubprocessAdapter
from tests.test_openclaw_bridge import (
    APPROVAL_SECRET,
    DECISION_SECRET,
    EVIDENCE_SECRET,
    POLICY,
    InvalidAdapter,
    action,
    evidence,
)

LOW_RISK_POLICY = {**POLICY, "approval_required_for_risks": [], "require_observed_for_risks": []}
SH = "/bin/sh"


class SubprocessAdapterRealProcessTests(unittest.TestCase):
    def bridge(self, directory, adapter):
        registry = AdapterRegistry()
        registry.register("external_message", adapter)
        return OpenClawProofRailBridge(
            state_db=Path(directory) / "state.sqlite3",
            ledger_path=Path(directory) / "ledger.jsonl",
            registry=registry,
            evidence_secret=EVIDENCE_SECRET,
            approval_secret=APPROVAL_SECRET,
            decision_secret=DECISION_SECRET,
        )

    def run_action(self, bridge, program, args):
        candidate = action(risk="low")
        candidate["execution"] = {"program": program, "args": args}
        return candidate, bridge.run(action=candidate, evidence=[evidence()],
                                     policy=LOW_RISK_POLICY, approval=None, actor="agent:test")

    def ledger(self, directory):
        return [json.loads(line) for line in (Path(directory) / "ledger.jsonl").read_text().splitlines()]

    def test_allowlisted_program_runs_and_effect_is_recorded(self):
        with TemporaryDirectory() as d:
            adapter = SubprocessAdapter(allowed_programs={SH}, cwd=d)
            _, result = self.run_action(self.bridge(d, adapter), SH, ["-c", "echo ok > effect"])
            self.assertEqual(result.status, "success")
            self.assertTrue((Path(d) / "effect").exists())

    def test_shell_metacharacters_are_not_interpreted(self):
        with TemporaryDirectory() as d:
            adapter = SubprocessAdapter(allowed_programs={"/usr/bin/printf"}, cwd=d)
            _, result = self.run_action(self.bridge(d, adapter), "/usr/bin/printf",
                                        ["%s", "; touch pwned"])
            self.assertEqual(result.status, "success")
            self.assertFalse((Path(d) / "pwned").exists())

    def test_non_allowlisted_program_never_runs(self):
        with TemporaryDirectory() as d:
            adapter = SubprocessAdapter(allowed_programs={SH}, cwd=d)
            with self.assertRaisesRegex(Exception, "not allowlisted"):
                self.run_action(self.bridge(d, adapter), "/usr/bin/touch", [str(Path(d) / "x")])
            self.assertFalse((Path(d) / "x").exists())

    def test_invalid_utf8_output_after_effect_still_yields_a_receipt(self):
        # Previously: UnicodeDecodeError raised after the effect, recorded "failed".
        with TemporaryDirectory() as d:
            adapter = SubprocessAdapter(allowed_programs={SH}, cwd=d)
            _, result = self.run_action(self.bridge(d, adapter), SH,
                                        ["-c", "touch effect; printf '\\377\\376'"])
            self.assertTrue((Path(d) / "effect").exists())
            self.assertEqual(result.status, "success")
            evidence_ = result.execution["receipt_evidence"]
            self.assertEqual(len(evidence_["stdout_sha256"]), 64)

    def test_timeout_after_effect_is_unknown_and_blocks_replay(self):
        # Previously: TimeoutExpired raised after the effect, recorded "failed".
        with TemporaryDirectory() as d:
            adapter = SubprocessAdapter(allowed_programs={SH}, timeout_seconds=1, cwd=d)
            bridge = self.bridge(d, adapter)
            candidate, first = self.run_action(bridge, SH, ["-c", "touch effect; sleep 5"])
            self.assertTrue((Path(d) / "effect").exists())
            self.assertEqual(first.status, "unknown")
            self.assertFalse(first.execution["retry_safe"])
            second = bridge.run(action=candidate, evidence=[evidence()], policy=LOW_RISK_POLICY,
                                approval=None, actor="agent:test")
            self.assertEqual(second.status, "replay_blocked")

    def test_adapter_exception_after_invocation_is_unknown_and_ledgered(self):
        # Previously: recorded "failed" and absent from the tamper-evident ledger.
        with TemporaryDirectory() as d:
            bridge = self.bridge(d, InvalidAdapter())
            candidate = action(risk="low")
            with self.assertRaisesRegex(Exception, "missing fields"):
                bridge.run(action=candidate, evidence=[evidence()], policy=LOW_RISK_POLICY,
                           approval=None, actor="agent:test")
            entries = self.ledger(d)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["outcome"], "unknown")
            from proofrail.core import digest_document
            audit = bridge.export_audit(digest_document(candidate))
            self.assertEqual(audit["status"], "unknown")
            self.assertTrue(audit["ledger"]["valid"])


if __name__ == "__main__":
    unittest.main()

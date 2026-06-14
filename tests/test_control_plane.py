import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from integrations.siem import to_cef, to_ecs_event
from proofrail.control_plane import ControlPlane
from proofrail.core import ProofRailError


POLICY = {
    "allowed_action_types": ["external_message"],
    "approval_required_for_risks": ["high"],
}


class ControlPlaneTests(unittest.TestCase):
    def test_policy_versions_are_immutable_and_tenant_scoped(self):
        with TemporaryDirectory() as directory:
            control = ControlPlane(Path(directory) / "control.sqlite3")
            tenant_a = control.create_tenant("Tenant A")
            tenant_b = control.create_tenant("Tenant B")
            control.grant_role(tenant_a, "alice", "admin")
            control.grant_role(tenant_b, "bob", "admin")
            first = control.publish_policy(
                tenant_id=tenant_a,
                principal_id="alice",
                policy_name="default",
                document=POLICY,
            )
            second = control.publish_policy(
                tenant_id=tenant_a,
                principal_id="alice",
                policy_name="default",
                document={**POLICY, "max_evidence_age_seconds": 300},
            )
            control.activate_policy(
                tenant_id=tenant_a,
                principal_id="alice",
                policy_name="default",
                version=second.version,
            )
            active = control.get_active_policy(
                tenant_id=tenant_a,
                principal_id="alice",
                policy_name="default",
            )
            self.assertEqual(first.version, 1)
            self.assertEqual(active.version, 2)
            with self.assertRaises(ProofRailError):
                control.get_active_policy(
                    tenant_id=tenant_a,
                    principal_id="bob",
                    policy_name="default",
                )

    def test_rbac_denies_operator_policy_publication(self):
        with TemporaryDirectory() as directory:
            control = ControlPlane(Path(directory) / "control.sqlite3")
            tenant = control.create_tenant("Tenant")
            control.grant_role(tenant, "operator", "operator")
            with self.assertRaises(ProofRailError):
                control.publish_policy(
                    tenant_id=tenant,
                    principal_id="operator",
                    policy_name="default",
                    document=POLICY,
                )

    def test_siem_exports_preserve_status_and_ledger_truth(self):
        audit = {
            "action_digest": "abc",
            "action_id": "action-1",
            "status": "unknown",
            "result": {"reason": "provider timeout"},
            "ledger": {"valid": True, "entries": 1, "errors": []},
        }
        ecs = to_ecs_event(audit, tenant_id="tenant-1")
        cef = to_cef(audit, tenant_id="tenant-1")
        self.assertEqual(ecs["proofrail.status"], "unknown")
        self.assertTrue(ecs["proofrail.ledger_valid"])
        self.assertIn("outcome=unknown", cef)


if __name__ == "__main__":
    unittest.main()

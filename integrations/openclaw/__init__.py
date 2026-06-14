"""OpenClaw orchestration bridge for the ProofRail kernel."""

from .bridge import AdapterRegistry, OpenClawProofRailBridge, SubprocessAdapter

__all__ = ["AdapterRegistry", "OpenClawProofRailBridge", "SubprocessAdapter"]

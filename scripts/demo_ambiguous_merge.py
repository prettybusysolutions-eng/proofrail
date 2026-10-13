"""Partner demo: synthetic provider effects, real HTTP, no Composio credentials.

Both paths deliberately share the production adapter. This demonstrates behavior,
not a competitive advantage, Composio integration or independent verification.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from benchmarks.comparative_github import Provider, ProofRailGate, ConventionalGate, attempt
from integrations.openclaw.github_adapter import GitHubMergeAdapter, GitHubTransport


class InterruptedBeforeWrite:
    def execute(self, *args, **kwargs):
        raise RuntimeError('Synthetic interruption after local claim, before provider write')


def demo():
    rows = []
    with TemporaryDirectory() as directory:
        root = Path(directory)
        provider = Provider(root)
        try:
            adapter = GitHubMergeAdapter(GitHubTransport(token='synthetic-only', api_base=provider.url))
            for name, cls in [('conventional', ConventionalGate), ('proofrail', ProofRailGate)]:
                folder = root / name
                folder.mkdir()
                gate = cls(folder, Ed25519PrivateKey.generate(), adapter)
                for case, mode in [('response_lost_after_effect', 'lost_response'),
                                   ('competing_actor_changes_head', 'competing_head'),
                                   ('interrupted_before_provider_write', 'normal')]:
                    number = provider.new(mode)
                    permit = gate.mint(number, f'{name}-{case}-00000001')
                    first = attempt(gate, permit, adapter=InterruptedBeforeWrite() if case.startswith('interrupted') else None)
                    repeated = attempt(gate, permit)
                    head, merged, effects, _ = provider.observe(number)
                    expected = ((first['status'] == 'success' and effects == 1) if mode == 'lost_response'
                                else (first['status'] != 'success' and effects == (1 if mode == 'competing_head' else 0)))
                    expected &= repeated['status'] == 'error'
                    rows.append({'path': name, 'case': case, 'first_attempt': first,
                                 'repeated_authority': repeated, 'fixture_provider_effects': effects,
                                 'fixture_head': head, 'fixture_merged': bool(merged),
                                 'expected_behavior_observed': expected,
                                 'claim_boundary': 'Matched provider state does not identify which actor caused it.'})
        finally:
            provider.close()
    return {'scope': __doc__, 'valid': all(r['expected_behavior_observed'] for r in rows),
            'results': rows, 'composio_integration_tested': False, 'independent_review': False,
            'automatic_retry_authorized': False, 'competitive_superiority_demonstrated': False}


if __name__ == '__main__':
    result = demo()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['valid'] else 1)

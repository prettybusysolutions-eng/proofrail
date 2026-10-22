"""Offline consistency of the actual captured provider trial, not a live call."""
import base64
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from proofrail.crypto import verify_signature
from acceptance_bridge import Trust, full_digest, verify_handoff


def test_captured_live_trial_signatures_and_provider_bytes():
    root = Path(__file__).resolve().parents[1] / 'evidence/github-live-20261019'
    evidence = json.loads((root / 'public-evidence.json').read_text())
    readback = json.loads((root / 'provider-readback.json').read_text())
    result = json.loads((root / 'result.json').read_text())
    public = {name: Ed25519PublicKey.from_public_bytes(base64.b64decode(value))
              for name, value in evidence['public_keys'].items()}
    authority = evidence['handoff']['payload']['authority']
    trust = Trust(evidence['public_keys']['sender'], public['issuer'], 'issuer-key',
                  full_digest(authority), authority['issuer'], public['observer'], 'observer-key',
                  authority['roots'], authority['approval_digest'])
    consumption = evidence['consumption']
    verify_signature(consumption, public['consumer'])
    binding = verify_handoff(evidence['handoff'], evidence['contract'], trust, now=consumption['consumed_at'])
    assert binding['authority_digest'] == consumption['authority_digest']
    assert full_digest(consumption) == result['consumption_digest']
    assert readback['file_content'] == evidence['request']['content']
    assert hashlib.sha256(readback['file_content'].encode()).hexdigest() == result['file_sha256']
    content = json.loads(readback['file_content'])
    assert content['execution_id'] == consumption['execution_id'] == result['execution_id']
    assert content['consumption_digest'] == full_digest(consumption)
    assert readback['commit']['sha'] == readback['branch_head'] == result['commit_sha']
    assert [p['sha'] for p in readback['commit']['parents']] == [evidence['request']['parent_sha']]

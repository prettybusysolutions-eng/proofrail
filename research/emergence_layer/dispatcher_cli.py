"""Service-account CLI. Config and key paths are trusted operator inputs.

No network listener: invoke from a trusted local worker. Callers submit only the
handoff file, never the service config, trust roots, token, or consumer key.
"""
import argparse
import base64
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from acceptance_bridge import Trust, require
from execution_binding import ExecutionLedger
from enforcing_dispatcher import Dispatcher, GitHubAPI, Journal


def private_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'private_file_required')
    require(path.stat().st_mode & 0o077 == 0, 'private_file_permissions')
    return path.read_text()


def load_service(config_path):
    config = json.loads(private_file(config_path))
    trust = dict(config['trust'])
    for key in ('authority_public', 'observer_public'):
        trust[key] = Ed25519PublicKey.from_public_bytes(base64.b64decode(trust[key], validate=True))
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_file(config['consumer_key_file']).strip()))
    # Startup never creates the retained journal. Only an explicit installation
    # step can initialize it. Existing registry may be recreated but replay
    # admissions then fail against the independently retained journal.
    journal = Journal(config['journal_path'])
    ledger = ExecutionLedger(config['registry_path'], key, config['consumer_key_id'])
    journal.verify_recovery_state(ledger)
    return Dispatcher(ledger, journal, GitHubAPI(config['github_token_file']),
        repository=config['repository'], branch=config['branch'], path=config['path'], trust=Trust(**trust))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['dispatch', 'recover', 'check'])
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--handoff', type=Path)
    args = parser.parse_args()
    try:
        dispatcher = load_service(args.config)
        if args.mode == 'check':
            print(json.dumps({'local_state': 'consistent', 'provider_credentials_verified': False}))
            return
        require(args.handoff is not None, 'handoff_required')
        require(args.handoff.stat().st_size <= 1024 * 1024, 'handoff_too_large')
        handoff = json.loads(args.handoff.read_text())
        result = getattr(dispatcher, args.mode)(handoff, handoff['payload']['contract'])
        print(json.dumps(result))
    except Exception:
        # Unknown provider outcome may include a successful write. Never retry
        # dispatch from an exit code; use read-only recovery for this authority.
        print(json.dumps({'outcome': 'BLOCKED_OR_UNCONFIRMED', 'retry_dispatch': False,
                          'next_action': 'operator inspection and read-only recovery'}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()

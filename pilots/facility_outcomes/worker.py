"""One admission in its own process (concurrency and crash tests).

    python worker.py --world W --provider URL --tenant T --envelope E --out O [--timeout S]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import load_world  # noqa: E402
from records import PilotError  # noqa: E402

parser = argparse.ArgumentParser()
for flag in ('--world', '--provider', '--tenant', '--envelope', '--out'):
    parser.add_argument(flag, required=True)
parser.add_argument('--timeout', type=float, default=None)
parser.add_argument('--test-crash-after', choices=['registry-commit', 'authority-record'],
                    default=None, help=argparse.SUPPRESS)
args = parser.parse_args()
world = load_world(Path(args.world), args.provider, provider_timeout=args.timeout)

# Deliberate process exits for isolated crash-window regression testing only.
# They fire at deterministic hooks BEFORE any provider create call.
if args.test_crash_after:
    import os
    gateway = world.pilot.gateways[args.tenant]
    if args.test_crash_after == 'registry-commit':
        gateway._reference = lambda *a, **kw: os._exit(72)
    elif args.test_crash_after == 'authority-record':
        gateway._attest_consumption = lambda *a, **kw: os._exit(73)

try:
    result = {'outcome': 'admitted', **{k: v for k, v in world.pilot.admit(
        args.tenant, json.loads(Path(args.envelope).read_text())).items() if k != 'reference'}}
except PilotError as exc:
    result = {'outcome': 'refused', 'reason': exc.reason}
Path(args.out).write_text(json.dumps(result))

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
args = parser.parse_args()
world = load_world(Path(args.world), args.provider, provider_timeout=args.timeout)
try:
    result = {'outcome': 'admitted', **{k: v for k, v in world.pilot.admit(
        args.tenant, json.loads(Path(args.envelope).read_text())).items() if k != 'reference'}}
except PilotError as exc:
    result = {'outcome': 'refused', 'reason': exc.reason}
Path(args.out).write_text(json.dumps(result))

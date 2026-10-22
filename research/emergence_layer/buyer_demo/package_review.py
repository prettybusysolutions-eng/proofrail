"""Build the independent-review package for the buyer demonstration at one exact commit.

    python buyer_demo/package_review.py --output /tmp/proofrail-review [--commit SHA]

The source is taken from `git archive <commit>`, not the working tree, and the
demonstration is run from that extracted copy (its `proofrail` package first on
PYTHONPATH). The package holds the source archive, a fresh evidence run, the
verifier's report, the environment, the review instructions and SHA256SUMS.
Producing a package is not a review; the status stays REVIEW_OPEN.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = ['research/emergence_layer/buyer_demo/README.md',
        'research/emergence_layer/buyer_demo/REVIEW_PACKAGE.md',
        'research/emergence_layer/DISPATCHER_PILOT.md',
        'research/emergence_layer/INDEPENDENT_DISPATCH_REVIEW.md']


def sh(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', default='HEAD')
    args = parser.parse_args()
    top = Path(sh('git', '-C', str(HERE), 'rev-parse', '--show-toplevel').strip())
    commit = sh('git', '-C', str(top), 'rev-parse', '--verify', args.commit + '^{commit}').strip()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    archive = out / f'proofrail-{commit[:12]}.tar'
    sh('git', '-C', str(top), 'archive', '--format=tar', '--prefix=proofrail/', '-o', str(archive), commit)
    for doc in DOCS:
        target = out / 'docs' / Path(doc).name
        target.parent.mkdir(exist_ok=True)
        target.write_text(sh('git', '-C', str(top), 'show', f'{commit}:{doc}'))

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        with tarfile.open(archive) as tar:
            tar.extractall(scratch, filter='data')
        source = scratch / 'proofrail'
        demo = source / 'research' / 'emergence_layer' / 'buyer_demo'
        env = {**os.environ, 'PYTHONPATH': str(source)}
        run = subprocess.run([sys.executable, str(demo / 'run_demo.py'), '--workdir', str(scratch / 'work'),
                              '--evidence', str(out / 'evidence')], capture_output=True, text=True,
                             env=env, cwd=demo.parent)
        (out / 'demo-output.txt').write_text(run.stdout + run.stderr)
        if run.returncode != 0:
            raise SystemExit('demonstration failed; see demo-output.txt')
        check = subprocess.run([sys.executable, str(demo / 'verify_evidence.py'), str(out / 'evidence'),
                                '--json'], capture_output=True, text=True, env=env, cwd=demo.parent)
        (out / 'verifier-report.json').write_text(check.stdout)
        imported = subprocess.run([sys.executable, '-c', 'import proofrail; print(proofrail.__file__)'],
                                  capture_output=True, text=True, env=env, cwd=demo.parent).stdout.strip()
        proofrail_from_archive = Path(imported).resolve().is_relative_to(source)

    verdict = json.loads(check.stdout)['verdict']
    (out / 'environment.json').write_text(json.dumps({
        'reviewed_commit': commit,
        'python': platform.python_version(), 'platform': platform.platform(),
        'git': sh('git', 'version').strip(),
        'proofrail_imported_from_archive': proofrail_from_archive,
        'pip_freeze': sh(sys.executable, '-m', 'pip', 'freeze').splitlines(),
    }, indent=2) + '\n')
    files = sorted(p for p in out.rglob('*') if p.is_file())
    (out / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in files))
    status = 'PACKAGE_READY_REVIEW_OPEN' if verdict == 'PASS' and proofrail_from_archive else 'PACKAGE_INVALID'
    print(json.dumps({'status': status, 'commit': commit, 'author_verifier_verdict': verdict,
                      'output': str(out)}))
    return 0 if status == 'PACKAGE_READY_REVIEW_OPEN' else 1


if __name__ == '__main__':
    sys.exit(main())

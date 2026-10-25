"""Disable each enforcement check in the pilot, one at a time, and run the pilot suite.

    python review_tools/mutate_checks.py OUT.json [WORKERS]

Five check shapes are mutated in a disposable copy of the pilot directory:
  require(COND, reason)          -> COND replaced by True
  if COND: return 'reason'       -> COND replaced by False   (outcome qualification)
  if COND: reasons.append(...)   -> COND replaced by False   (settlement rules)
  r.check(dim, name, COND, ...)  -> COND replaced by True    (offline bundle verifier)
  raise PilotError(...)          -> pass                     (offline bundle verifier)
Each mutant is classified as survived, killed_valid (with the exact failing test and
its reason, re-confirmed on the mutant and passing on the unmutated copy), or invalid
(syntax error, collection/usage/internal error, setup error, timeout, unreproduced or
environment failure). Invalid outcomes are reported, never counted as kills.

The copy keeps the repository layout (pilots/facility_outcomes next to docs/),
because some tests read docs/. An unmutated copy must pass before any mutant is
counted: without that baseline, a test that fails for an environmental reason
"kills" every mutant and the sweep reports 0 survivors regardless of coverage.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
DOCS = PILOT.parents[1] / 'docs'
VERIFIER = 'verify_bundle.py'
TARGETS = ['proofrail_gateway.py', 'policy.py', 'outcome_verifier.py', 'settlement_simulator.py', 'records.py',
           'pilot.py', 'store.py', 'evidence_export.py', 'lifecycle.py']


def spans(text):
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    def at(node, end=False):
        line, col = (node.end_lineno, node.end_col_offset) if end else (node.lineno, node.col_offset)
        return offsets[line - 1] + len(lines[line - 1].encode()[:col].decode())
    return at


def mutants():
    for name in TARGETS:
        text = (PILOT / name).read_text()
        at = spans(text)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'require' and node.args:
                arg = node.args[0]
                label = ast.unparse(node.args[1]) if len(node.args) > 1 else '?'
                yield name, node.lineno, 'require ' + label, text[:at(arg)] + '(True)' + text[at(arg, True):]
            elif isinstance(node, ast.If) and len(node.body) == 1:
                stmt = node.body[0]
                is_reason = (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant)
                             and isinstance(stmt.value.value, str))
                is_append = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                             and ast.unparse(stmt.value.func) == 'reasons.append')
                if is_reason or is_append:
                    label = ast.unparse(stmt.value if is_reason else stmt.value.args[0])
                    yield name, node.lineno, 'if ' + label, text[:at(node.test)] + '(False)' + text[at(node.test, True):]
    text = (PILOT / VERIFIER).read_text()
    at = spans(text)
    for node in ast.walk(ast.parse(text)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'check'
                and len(node.args) >= 3 and not (isinstance(node.args[2], ast.Constant) and node.args[2].value is True)):
            arg = node.args[2]
            yield VERIFIER, node.lineno, 'check ' + ast.unparse(node.args[1]), text[:at(arg)] + '(True)' + text[at(arg, True):]
        elif isinstance(node, ast.Raise) and node.exc is not None and 'PilotError' in ast.unparse(node.exc):
            yield VERIFIER, node.lineno, 'raise ' + ast.unparse(node.exc), text[:at(node)] + 'pass' + text[at(node, True):]


PYTEST = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-rfE']
ENV = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'COLUMNS': '1000'}
TIMEOUT = 600


def make_copy(d, name=None, mutated=None):
    copy = Path(d) / 'pilots' / 'facility_outcomes'
    shutil.copytree(PILOT, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'review_tools'))
    shutil.copytree(DOCS, Path(d) / 'docs')
    if name is not None:
        (copy / name).write_text(mutated)
    return copy


def pytest(copy, *args):
    """Return (exit code or 'timeout', FAILED nodeids with messages, ERROR nodeids, output tail)."""
    try:
        r = subprocess.run(PYTEST + list(args), cwd=copy, capture_output=True, text=True,
                           timeout=TIMEOUT, env=ENV)
    except subprocess.TimeoutExpired:
        return 'timeout', [], [], ''
    failed, errors = [], []
    for line in r.stdout.splitlines():
        if line.startswith('FAILED '):
            nodeid, _, message = line[len('FAILED '):].partition(' - ')
            failed.append({'test': nodeid, 'reason': message[:300]})
        elif line.startswith('ERROR '):
            errors.append(line[len('ERROR '):][:300])
    return r.returncode, failed, errors, '\n'.join((r.stdout + r.stderr).splitlines()[-8:])


def run(m, baseline_copy):
    """Classify one mutant as survived, killed_valid, or invalid (never counted as a kill).

    killed_valid requires all of: the mutated file compiles; pytest exits 1 (test failures,
    not collection/usage/internal errors); at least one FAILED test and no ERROR (setup)
    entries; that exact test fails again when re-run alone on the mutant; and the same
    test passes alone on the unmutated copy. Anything else is invalid with its cause.
    """
    name, line, label, mutated = m
    result = {'file': name, 'line': line, 'check': label}
    try:
        compile(mutated, name, 'exec')
    except SyntaxError as exc:
        return {**result, 'outcome': 'invalid', 'cause': f'syntax_error: {exc}'}
    with tempfile.TemporaryDirectory() as d:
        copy = make_copy(d, name, mutated)
        code, failed, errors, tail = pytest(copy, '-x', 'tests/')
        if code == 0:
            return {**result, 'outcome': 'survived'}
        if code == 'timeout':
            return {**result, 'outcome': 'invalid', 'cause': 'timeout'}
        if code != 1:
            return {**result, 'outcome': 'invalid', 'cause': f'pytest_exit_{code} (collection, usage or internal error)',
                    'output': tail}
        if errors or not failed:
            return {**result, 'outcome': 'invalid', 'cause': 'test_setup_error' if errors else 'no_failed_test_reported',
                    'errors': errors, 'output': tail}
        killer = failed[0]
        again, _, _, _ = pytest(copy, killer['test'])
    clean, _, _, _ = pytest(baseline_copy, killer['test'])
    if again != 1:
        return {**result, 'outcome': 'invalid', 'cause': f'failure_not_reproduced_on_mutant (exit {again})', **killer}
    if clean != 0:
        return {**result, 'outcome': 'invalid', 'cause': f'test_also_fails_unmutated (exit {clean})', **killer}
    return {**result, 'outcome': 'killed_valid', **killer}


def commit():
    try:
        sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=PILOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', '.', str(DOCS)], cwd=PILOT,
                               capture_output=True, text=True).stdout.strip()
        return sha, bool(dirty)
    except OSError:
        return 'unknown', True


if __name__ == '__main__':
    out = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    sha, dirty = commit()
    with tempfile.TemporaryDirectory() as base:
        baseline_copy = make_copy(base)
        code, failed, errors, tail = pytest(baseline_copy, 'tests/')
        if code != 0:
            sys.exit(f'unmutated copy fails (exit {code}), so no mutant can be counted: {failed or errors or tail}')
        print('baseline: unmutated copy passes', flush=True)
        ms = list(mutants())
        print('checks:', len(ms), flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda m: run(m, baseline_copy), ms))
    counts = {k: sum(r['outcome'] == k for r in results) for k in ('survived', 'killed_valid', 'invalid')}
    out.write_text(json.dumps({'commit': sha, 'tree_dirty': dirty, 'python': sys.version.split()[0],
                               'baseline': 'unmutated copy passes', 'counts': counts, 'results': results}, indent=1))
    print('commit:', sha, '(dirty)' if dirty else '')
    print('counts:', counts)
    for kind in ('survived', 'invalid'):
        for r in results:
            if r['outcome'] == kind:
                print(f"  {kind.upper()} {r['file']}:{r['line']}  {r['check']}  {r.get('cause', '')}")

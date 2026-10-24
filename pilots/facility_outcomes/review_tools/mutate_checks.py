"""Disable each enforcement check in the pilot, one at a time, and run the pilot suite.

    python review_tools/mutate_checks.py OUT.json [WORKERS]

Five check shapes are mutated in a disposable copy of the pilot directory:
  require(COND, reason)          -> COND replaced by True
  if COND: return 'reason'       -> COND replaced by False   (outcome qualification)
  if COND: reasons.append(...)   -> COND replaced by False   (settlement rules)
  r.check(dim, name, COND, ...)  -> COND replaced by True    (offline bundle verifier)
  raise PilotError(...)          -> pass                     (offline bundle verifier)
A check whose removal leaves the suite green is reported as a survivor.

The copy keeps the repository layout (pilots/facility_outcomes next to docs/),
because some tests read docs/. An unmutated copy must pass before any mutant is
counted: without that baseline, a test that fails for an environmental reason
"kills" every mutant and the sweep reports 0 survivors regardless of coverage.
"""
import ast
import json
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


def run(m):
    name, line, label, mutated = m
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / 'pilots' / 'facility_outcomes'
        shutil.copytree(PILOT, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'review_tools'))
        shutil.copytree(DOCS, Path(d) / 'docs')
        if name is not None:
            (copy / name).write_text(mutated)
        try:
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', 'tests/'],
                               cwd=copy, capture_output=True, text=True, timeout=600)
            survived = r.returncode == 0
            killer = next((l for l in r.stdout.splitlines() if l.startswith('FAILED')), '')[:160]
        except subprocess.TimeoutExpired:
            survived, killer = False, 'timeout'
    return {'file': name, 'line': line, 'check': label, 'survived': survived, 'killed_by': killer}


if __name__ == '__main__':
    out = Path(sys.argv[1])
    baseline = run((None, 0, 'baseline', None))
    if not baseline['survived']:
        sys.exit('unmutated copy fails, so no mutant can be counted: ' + baseline['killed_by'])
    print('baseline: unmutated copy passes', flush=True)
    ms = list(mutants())
    print('checks:', len(ms), flush=True)
    with ThreadPoolExecutor(max_workers=int(sys.argv[2]) if len(sys.argv) > 2 else 4) as pool:
        results = list(pool.map(run, ms))
    out.write_text(json.dumps(results, indent=1))
    survivors = [r for r in results if r['survived']]
    print('survived:', len(survivors), 'of', len(results))
    for r in survivors:
        print(f"  {r['file']}:{r['line']}  {r['check']}")

"""Disable each enforcement check in the pilot, one at a time, and run the pilot suite.

    python review_tools/mutate_checks.py OUT.json [WORKERS]

Three check shapes are mutated in a disposable copy of the pilot directory:
  require(COND, reason)          -> COND replaced by True
  if COND: return 'reason'       -> COND replaced by False   (outcome qualification)
  if COND: reasons.append(...)   -> COND replaced by False   (settlement rules)
A check whose removal leaves the suite green is reported as a survivor.
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


def run(m):
    name, line, label, mutated = m
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / 'facility_outcomes'
        shutil.copytree(PILOT, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'review_tools'))
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
    ms = list(mutants())
    print('checks:', len(ms), flush=True)
    with ThreadPoolExecutor(max_workers=int(sys.argv[2]) if len(sys.argv) > 2 else 4) as pool:
        results = list(pool.map(run, ms))
    out.write_text(json.dumps(results, indent=1))
    survivors = [r for r in results if r['survived']]
    print('survived:', len(survivors), 'of', len(results))
    for r in survivors:
        print(f"  {r['file']}:{r['line']}  {r['check']}")

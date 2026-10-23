"""Author self-review tool (see SELF_REVIEW.md). Disable one require(...) at a time (condition -> True) in a disposable copy; run tests."""
import ast, json, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()            # research/emergence_layer
OUT = Path(sys.argv[2])
TARGETS = ['enforcing_dispatcher.py', 'github_artifact.py', 'acceptance_bridge.py', 'execution_binding.py']
PY = sys.executable

def mutants():
    for name in TARGETS:
        text = (SRC / name).read_text()
        lines = text.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        for node in ast.walk(ast.parse(text)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'require' and node.args):
                arg = node.args[0]
                a = offsets[arg.lineno - 1] + len(lines[arg.lineno - 1].encode()[:arg.col_offset].decode())
                b = offsets[arg.end_lineno - 1] + len(lines[arg.end_lineno - 1].encode()[:arg.end_col_offset].decode())
                reason = ast.unparse(node.args[1]) if len(node.args) > 1 else '?'
                yield name, node.lineno, reason, text[:a] + '(True)' + text[b:]

def run(m):
    name, line, reason, mutated = m
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / 'emergence_layer'
        shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        (copy / name).write_text(mutated)
        r = subprocess.run([PY, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', 'tests/'],
                           cwd=copy, capture_output=True, text=True, timeout=600)
        killer = next((l for l in r.stdout.splitlines() if l.startswith('FAILED')), '')
        return {'file': name, 'line': line, 'reason': reason,
                'survived': r.returncode == 0, 'killed_by': killer[:160]}

ms = list(mutants())
print('mutants:', len(ms), flush=True)
with ThreadPoolExecutor(max_workers=int(sys.argv[3]) if len(sys.argv) > 3 else 2) as pool:
    results = list(pool.map(run, ms))
OUT.write_text(json.dumps(results, indent=1))
surv = [r for r in results if r['survived']]
print('survived:', len(surv), 'of', len(results))
for r in surv:
    print(f"  {r['file']}:{r['line']}  {r['reason']}")

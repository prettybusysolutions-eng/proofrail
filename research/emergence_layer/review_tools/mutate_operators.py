"""Author self-review tool (see SELF_REVIEW.md). Operator mutations in decision code: comparisons, boolean ops, `not`, True/False, ints."""
import ast, json, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])
TARGETS = ['enforcing_dispatcher.py', 'github_artifact.py']
FLIP = {ast.Eq: '!=', ast.NotEq: '==', ast.Is: 'is not', ast.IsNot: 'is', ast.In: 'not in',
        ast.NotIn: 'in', ast.Lt: '>=', ast.LtE: '>', ast.Gt: '<=', ast.GtE: '<'}

def span(text, lines, offsets, node):
    a = offsets[node.lineno - 1] + len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
    b = offsets[node.end_lineno - 1] + len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
    return a, b

def mutants():
    for name in TARGETS:
        text = (SRC / name).read_text()
        lines = text.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        tree = ast.parse(text)
        skip = set()
        for node in ast.walk(tree):  # docstrings and require() reason strings are not logic
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'require' and len(node.args) > 1:
                skip |= {id(n) for n in ast.walk(node.args[1])}
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)) and node.body and \
                    isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                skip.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in FLIP:
                new = ast.unparse(node.left) + ' ' + FLIP[type(node.ops[0])] + ' ' + ast.unparse(node.comparators[0])
                a, b = span(text, lines, offsets, node)
                yield name, node.lineno, 'compare ' + ast.unparse(node)[:60], text[:a] + '(' + new + ')' + text[b:]
            elif isinstance(node, ast.BoolOp):
                op = ' or ' if isinstance(node.op, ast.And) else ' and '
                a, b = span(text, lines, offsets, node)
                new = op.join('(' + ast.unparse(v) + ')' for v in node.values)
                yield name, node.lineno, 'boolop ' + ast.unparse(node)[:60], text[:a] + '(' + new + ')' + text[b:]
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                a, b = span(text, lines, offsets, node)
                yield name, node.lineno, 'drop-not ' + ast.unparse(node)[:60], text[:a] + '(' + ast.unparse(node.operand) + ')' + text[b:]
            elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
                a, b = span(text, lines, offsets, node)
                yield name, node.lineno, 'bool ' + repr(node.value), text[:a] + repr(not node.value) + text[b:]
            elif isinstance(node, ast.Constant) and type(node.value) is int:
                a, b = span(text, lines, offsets, node)
                yield name, node.lineno, 'int %d' % node.value, text[:a] + repr(node.value + 1) + text[b:]

def run(m):
    name, line, desc, mutated = m
    try:
        compile(mutated, name, 'exec')
    except SyntaxError:
        return {'file': name, 'line': line, 'mutation': desc, 'survived': False, 'killed_by': 'syntax'}
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / 'emergence_layer'
        shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        (copy / name).write_text(mutated)
        try:
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', 'tests/'],
                               cwd=copy, capture_output=True, text=True, timeout=300)
            survived, killer = r.returncode == 0, next((l for l in r.stdout.splitlines() if l.startswith('FAILED')), '')
        except subprocess.TimeoutExpired:
            survived, killer = False, 'timeout'
        return {'file': name, 'line': line, 'mutation': desc, 'survived': survived, 'killed_by': killer[:160]}

ms = list(mutants())
print('mutants:', len(ms), flush=True)
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run, ms))
OUT.write_text(json.dumps(results, indent=1))
surv = [r for r in results if r['survived']]
print('survived:', len(surv), 'of', len(results))
for r in surv:
    print(f"  {r['file']}:{r['line']}  {r['mutation']}")

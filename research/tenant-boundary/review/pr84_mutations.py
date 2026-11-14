"""Mutation check for PR #84's detector (Claude's review, Issue #82).

Usage: python3 -I research/tenant-boundary/review/pr84_mutations.py <path-to-independent-probes.mjs> <out-dir>
Writes one mutated copy per mutation (hard assertions removed so verdicts are visible), then run
`node <out-dir>/<name>.mjs`. Each mutation changes one planted row; expected labels are GPT-6's own
frozen spec (GPT6_INDEPENDENT_CASES.md at 1f77f369).
"""
import os
import sys

MUTATIONS = {
    # H01 spec: VIOLATION. Secret embedded in a longer string instead of equal to it.
    'M1-embedded-secret': (
        "s.telemetry.push({ scope: B, text: SECRET, readableBy: B }); break;",
        "s.telemetry.push({ scope: B, text: 'note: '+SECRET, readableBy: B }); break;"),
    # H04 spec (direction-agnostic): VIOLATION. Leak flows B -> A instead of A -> B.
    'M2-reverse-direction': (
        "s.artifacts.push({ scope: B, path: '/shared/notes.txt', text: SECRET, readableBy: B }); break;",
        "s.artifacts.push({ scope: A, path: '/shared/notes.txt', text: 'synthetic-private-globex-1', readableBy: A }); break;"),
    # H01 spec note: a central operator log with no B access must NOT be classed a B leak (SAFE control).
    'M3-operator-only-log': (
        "case 'C0-safe': break;",
        "case 'C0-safe': s.telemetry.push({ scope: B, text: SECRET, readableBy: 'operator-only' }); break;"),
}
STRIP = [
    "assert.equal(before.verdict, expected, id+' planted ground truth');",
    "assert.equal(conventional.verdict, expected, id+' ordinary privileged baseline');",
    "assert.equal(harness.verdict, expected, id+' candidate');",
]

def main(src_path: str, out_dir: str) -> None:
    src = open(src_path, encoding='utf-8').read()
    os.makedirs(out_dir, exist_ok=True)
    for name, (old, new) in MUTATIONS.items():
        if src.count(old) != 1:
            raise SystemExit(f'{name}: anchor matched {src.count(old)} times')
        out = src.replace(old, new)
        for s in STRIP:
            out = out.replace(s, '')
        with open(os.path.join(out_dir, name + '.mjs'), 'w', encoding='utf-8') as f:
            f.write(out)
        print(os.path.join(out_dir, name + '.mjs'))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

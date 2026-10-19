"""Local resource probe; no claim of human savings or competitor superiority."""
import copy
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proofrail.audit_review import review_events

base = [json.loads(line) for line in
        (Path(__file__).resolve().parents[1] / 'examples/audit-review/events.jsonl').read_text().splitlines()]
results = []
for permits in (100, 1000, 10000):
    events = []
    for i in range(permits):
        for j, source in enumerate(base):
            e = copy.deepcopy(source)
            e.update(sequence=i * 3 + j + 1, event_id=f'{i}:{j}', permit_hash=f'{i:064x}', object_id=f'{i}:{j}')
            if j == 2:
                e['metadata']['execution_id'] = f'{i}:1'
            events.append(e)
    review_events(events, tenant_id='tenant-a')
    samples = []
    for _ in range(5):
        start = perf_counter()
        result = review_events(events, tenant_id='tenant-a')
        samples.append((perf_counter() - start) * 1000)
    assert result['permit_count'] == permits
    assert len(result['findings']) == permits * 3
    results.append({'events': len(events), 'findings': len(result['findings']),
                    'raw_ms': samples, 'median_ms': statistics.median(samples)})
print(json.dumps({'python': platform.python_version(), 'runs': results,
                  'scope': 'Single shared host, warm in-process triage; excludes file parsing, serialization and human review.'}, indent=2))

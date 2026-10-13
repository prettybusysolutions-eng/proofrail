"""Score completed, counterbalanced human triage observations; never invent results."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
from statistics import median

LABELS = {'needs_review', 'no_findings'}
ARMS = {'baseline', 'assisted'}


def score(manifest, observations):
    for field in ('workflow', 'baseline_tools', 'assisted_version', 'label_approver'):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f'Complete preregistered field: {field}')
    cases = manifest.get('cases', [])
    if len(cases) < 20:
        raise ValueError('At least 20 distinct labeled cases are required')
    truth = {}
    for case in cases:
        case_id = case.get('case_id')
        if not isinstance(case_id, str) or not case_id or case_id in truth:
            raise ValueError('Case IDs must be distinct nonempty strings')
        if case.get('expected_label') not in LABELS or type(case.get('critical')) is not bool:
            raise ValueError('Every case needs an approved label and Boolean critical flag')
        if case['critical'] and case['expected_label'] != 'needs_review':
            raise ValueError('Critical cases must require review')
        truth[case_id] = case
    if len({c['expected_label'] for c in cases}) != 2 or sum(c['critical'] for c in cases) < 5:
        raise ValueError('Include both labels and at least five critical review cases')
    pairs, reviewers, seen = defaultdict(dict), defaultdict(Counter), set()
    for row in observations:
        case_id, arm, reviewer = row['case_id'], row['arm'], row['reviewer_id'].strip()
        if case_id not in truth or arm not in ARMS or not reviewer:
            raise ValueError('Unknown case/arm or missing reviewer')
        if arm in pairs[case_id] or (reviewer, case_id) in seen:
            raise ValueError('Duplicate result or reviewer saw the same case twice')
        if row['observed_label'] not in LABELS:
            raise ValueError('Missing or unsupported observed label')
        seconds = float(row['elapsed_seconds'])
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Elapsed time must be a finite positive measurement')
        seen.add((reviewer, case_id))
        reviewers[reviewer][arm] += 1
        pairs[case_id][arm] = {**row, 'seconds': seconds}
    if set(pairs) != set(truth) or any(set(p) != ARMS for p in pairs.values()):
        raise ValueError('Each case needs one measured result in each arm')
    if len(reviewers) < 2 or any(set(counts) != ARMS or abs(counts['baseline'] - counts['assisted']) > 1
                                 for counts in reviewers.values()):
        raise ValueError('Use at least two reviewers, each balanced across both arms')
    metrics = {}
    for arm in sorted(ARMS):
        correct = sum(pairs[c][arm]['observed_label'] == truth[c]['expected_label'] for c in truth)
        critical_misses = sum(truth[c]['critical'] and pairs[c][arm]['observed_label'] == 'no_findings' for c in truth)
        metrics[arm] = {'accuracy': correct / len(truth), 'critical_misses': critical_misses,
                        'median_seconds': median(pairs[c][arm]['seconds'] for c in truth)}
    reduction = median(1 - pair['assisted']['seconds'] / pair['baseline']['seconds'] for pair in pairs.values())
    gate = reduction >= 0.30 and metrics['assisted']['critical_misses'] == 0 and metrics['assisted']['accuracy'] >= metrics['baseline']['accuracy']
    return {'status': 'MEASURED', 'cases': len(truth), 'metrics': metrics,
            'median_paired_time_reduction': reduction, 'proposed_technical_gate_met': gate,
            'commercial_validation': 'NOT_ESTABLISHED', 'independent_review': 'NOT_ESTABLISHED',
            'limits': ['Self-reported observations; scorer cannot authenticate people, labels or times.',
                       'Descriptive small pilot, not a statistical guarantee or causal proof.',
                       'Setup, maintenance and payment willingness must be evaluated separately.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--observations', required=True)
    args = parser.parse_args()
    try:
        with open(args.observations, newline='') as handle:
            result = score(json.loads(Path(args.manifest).read_text()), list(csv.DictReader(handle)))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'INCOMPLETE_OR_INVALID', 'reason': str(exc)}))
        raise SystemExit(2)
    print(json.dumps(result, indent=2))

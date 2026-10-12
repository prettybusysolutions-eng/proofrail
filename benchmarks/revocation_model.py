"""Finite schedule enumeration, NOT a proof about the production implementation.

Two actions hold grants for epoch zero. Each checks and attempts an effect once.
One revocation increments the authority epoch. Provider fencing, when enabled,
compares that epoch atomically with committing the effect. Every operation is
atomic in this model; no crash, rollback, compromised actor, or partition exists.
"""
import itertools
import json


def run():
    schedules = [p for p in itertools.permutations(('check_a', 'effect_a',
                                                   'check_b', 'effect_b', 'revoke'))
                 if p.index('check_a') < p.index('effect_a')
                 and p.index('check_b') < p.index('effect_b')]
    results = {}
    for fenced in (False, True):
        violations = []
        commits = 0
        for schedule in schedules:
            epoch = 0
            allowed = {}
            bad = False
            for event in schedule:
                if event == 'revoke':
                    epoch += 1
                    continue
                kind, actor = event.split('_')
                if kind == 'check':
                    allowed[actor] = epoch == 0
                elif allowed[actor] and (not fenced or epoch == 0):
                    commits += 1
                    bad |= epoch != 0
            if bad:
                violations.append(list(schedule))
        results['provider_atomic_fence' if fenced else 'local_check_only'] = {
            'schedules': len(schedules), 'violating_schedules': len(violations),
            'total_commits': commits, 'counterexample': violations[0] if violations else None}
    assert results['local_check_only']['violating_schedules'] > 0
    assert results['provider_atomic_fence']['violating_schedules'] == 0
    assert results['provider_atomic_fence']['total_commits'] > 0
    return {'scope': __doc__, 'results': results,
            'implementation_verified': False, 'independent_review': False}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))

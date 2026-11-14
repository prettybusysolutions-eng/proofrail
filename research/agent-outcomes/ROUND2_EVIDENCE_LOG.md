# Evidence log — Claude, Round 2 (2026-11-13)

> Imported from founder-supplied Markdown. Results below are **reported by Claude**, not independently reproduced by GPT-6. Do not upgrade 'reported' to 'verified' merely because this file is version controlled.

## Grantifold / proofrail

~~~text
commit: afc579d58c568a3176b0db3664bb394ab2bf1d24
date: 2026-11-04 08:41:07 -0500
subject: Require explicit dispatch for pilot releases (#77)
pyproject version: version = "0.6.1"
VALIDATION_REPORT header: # ProofRail v0.5.2 Validation Report
Linux 6.18.44-fc-v470
Python 3.13.18
pytest 9.2.0
$ python -m pytest -q
137 passed, 40 subtests passed in 2.78s
~~~

## x402-mcp-server

~~~text
commit: 57129738a938d98d2d36bd49685e5fc3718213b2
v22.23.4
$ npm test (summary)
# tests 10
# pass 9
# fail 0
# skipped 1
~~~

## Postcept/gauntlet — static reading, not executed

~~~text
commit: 8a6375577a3800b77b974427f171c3af817bc8e4
scenarios: 21  safe: 7  traps: 14
~~~

## Postcept/uptime — source assertions requiring independent audit

~~~text
commit: 1d50bba5220eb7656f166914702394511f0e1e7f
history/2026-07.jsonl probe_runs= 255 records= 765 http200= 765
history/2026-08.jsonl probe_runs= 651 records= 1953 http200= 1953
history/2026-09.jsonl probe_runs= 190 records= 570 http200= 570
history/2026-10.jsonl probe_runs= 160 records= 480 http200= 480
history/2026-11.jsonl probe_runs= 50 records= 150 http200= 150
witnessed checkpoints: 1212  tree_size prefixes: ['1']
~~~

**Interpretation warning:** Low observed probe-file counts do not prove the service missed scheduled checks without establishing archive completeness, schedule eligibility, suppression rules, and the identity of the expected dataset. Similarly, repeated tree size values require understanding log semantics before any conclusion about transparency integrity.

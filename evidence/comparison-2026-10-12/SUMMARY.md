# Comparative integration results — 2026-10-12

## Decision

No technical advantage over the conventional reference baseline was demonstrated
in this narrow integration. Both paths met the same 11 safety/functionality
expectations in each of three runs. Both also reproduced the late-revocation
counterexample: revocation after local admission did not stop the provider write.
That twelfth expected result is a known limitation, not a security pass.

ProofRail had higher median and p95 latency in all three local runs. These results
do not establish production performance, overall inferiority, commercial demand,
universal revocation protection, or acquisition value. ProofRail's additional
proof/checkpoint features were outside this base-mode comparison.

## Measurements

100 timed actions per path per run, after five warmups. Milliseconds:

| Run | Conventional p50 | ProofRail p50 | Conventional p95 | ProofRail p95 |
| --- | ---: | ---: | ---: | ---: |
| run-1 | 7.357 | 9.231 | 14.089 | 16.199 |
| run-2 | 5.308 | 8.075 | 11.440 | 15.016 |
| run-3 | 4.816 | 7.685 | 10.904 | 11.566 |

Seeds: 20261012, 20261013, 20261014. Serial runs on one shared host, with randomized
pair order. Earlier calibration runs were superseded; no test-suite invocation
was launched concurrently with this retained batch. Host scheduling remains
uncontrolled. Raw samples and case results are retained in run-1.json through
run-3.json. All three runs report valid=true and no benchmark errors.

A separate unit-suite execution passed 83 tests; see unit-suite.log. This is
assistant-authored verification, not independent review.

## Exact source and reproduction

The raw files record local tested commit
`93b9b21c2362040edcdaacbe263486c7891c6dd1`.
The remote equivalent code commit is
`7f3f255147e477b339e5c08c56c6d1051c667b84`.
Both have identical Git tree `af572d3a423c3b017eecfa12a5843b83db4fc173`.
The harness SHA-256 is
`d268f2307e0efb3f1d85d1efbef2674592d219658a297dac45c2f904d3b7f223`.
Commit metadata differs because the remote commit was created through the GitHub
connector; source contents match. This evidence commit adds results afterward.

```bash
python -m pip install .
python benchmarks/comparative_github.py --samples 100 --seed 20261012 --output run-1.json
python benchmarks/comparative_github.py --samples 100 --seed 20261013 --output run-2.json
python benchmarks/comparative_github.py --samples 100 --seed 20261014 --output run-3.json
python -m unittest discover -s tests -v
```

## Limits and next decision

This is a local HTTP integration with a SQLite-backed provider fixture, synthetic
credentials, a shared production adapter, and an assistant-authored conventional
baseline. It is not a live GitHub integration or independent replication. Both
implementations can share adapter or fixture errors. An injected exception tests
interruption; it is not a process-kill test. Permit minting and fixture setup are
excluded from timing. See docs/COMPARATIVE_INTEGRATION_REVIEW.md for full scope.

The next gate is an independent reviewer checking this exact source, baseline
fairness, provider-state attribution and revocation boundaries on another machine,
with independently authored adversarial cases. No reviewer has been engaged and
no fee is authorized. The separate frozen Gate 1B semantic review remains open.

Continue only if review identifies a defensible, useful distinction worth testing
with a real adopter. These results alone do not justify forming a company or
claiming acquisition value.

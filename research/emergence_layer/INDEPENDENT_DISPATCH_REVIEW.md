# Independent dispatcher review request

Status: OPEN. Author-run tests and CI are not independent semantic review.

Author self-review (2026-10-22): SELF_REVIEW.md records mutation sweeps and fault
matrices run by the authors, with the tools to rerun them. It narrows what a
reviewer should expect to find; it does not replace this review.

Target note (2026-10-22): `recover` changed after 73d7d48 (the SHA named in
issue #30) to confirm the whole commit tree, not only the file bytes; see
buyer_demo/README.md. Review the current head of the branch under review, not
73d7d48. Add to the counterexamples: a look-alike commit on the approved parent
serving the approved bytes.
This target extends PR #29; it does not close existing ProofRail review gates.

Review the exact PR head SHA, record reviewer identity, independence from authors,
OS, Python version, dependency freeze and command output. Reproduce in a clean
checkout with no production credentials:

```sh
python -m venv /tmp/proofrail-review-venv
. /tmp/proofrail-review-venv/bin/activate
python -m pip install . -r research/emergence_layer/requirements-dev.txt
python -m unittest discover -s tests -q
cd research/emergence_layer
python -m pytest -q tests/ --junitxml=review-results.xml
python counterfactual_lab.py --output /tmp/reproduced-emergence.json
diff -u counterfactual_results.json /tmp/reproduced-emergence.json
python -m pip freeze
```

Examine enforcing_dispatcher.py, dispatcher_cli.py, github_artifact.py,
execution_binding.py, acceptance_bridge.py, core authority verification and tests.
Try to produce these counterexamples and report evidence even when none is found:

- Invalid sender or issuer; authorized sender replacing payload, scope or authority.
- Wrong base tree changing unrelated files despite the expected artifact matching.
- Concurrent dispatches using one nonce or a restored registry.
- Kill after reserve, consume, admission, tree creation, commit creation and ref update.
- Provider accepts ref update and response is lost. Recovery must issue zero writes.
- Branch divergence or administrative rewind between head read and ref update.
- Expired credentials, redirect, substituted transport origin and malformed responses.
- Deleted claims, reset dispatch flag, missing journal, rollback of both stores.
- Requester influence over service config, token, trust keys or provider client.

The tests intentionally expose the joint-rollback and privileged-operator boundary;
do not certify either as solved. Checkpoint epoch/counter integration remains rejected.
The new HTTP transport has not been validated against GitHub using a service-owned
token. Earlier connector evidence is not evidence for that transport.

Required output: reviewed SHA, reproducible commands, PASS/FAIL per invariant,
severity and exploit trace for each finding, exact scope/limits and a signed or
GitHub-authenticated review. Do not approve based solely on green CI. No reviewer
has yet been assigned or returned this report.

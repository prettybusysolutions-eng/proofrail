| Variant | Boundary | Ground-truth leak | Oracle violations (at rest / final) | V1 settings+auth | V2a static scanner (new findings vs correct) | V2b black-box probes | Own-tenant recall works | ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0-correct | — | no | 0 / 0 | no | YES | no (-, probes 36) | YES | 65 |
| D1-global-memory | memory | YES | 2 / 5 | no | no | YES (probe:acme:same-user:recall, probes 1) | YES | 17.6 |
| D2-pinned-provider-client | memory | YES | 1 / 4 | no | no | YES (probe:acme:same-user:recall, probes 1) | YES | 15.4 |
| D3-session-key-collision | session state | YES | 4 / 6 | no | no | YES (probe:acme:same-user:history, probes 2) | YES | 6.8 |
| D4-shared-cache-key | cache / retrieval | YES | 3 / 4 | no | no | YES (workload:summarize, probes 0) | YES | 6.4 |
| D5-model-supplied-tenant | tool call | YES | 2 / 3 | no | no | YES (workload:get_record, probes 0) | YES | 8.4 |
| D6-handoff-drops-tenant | delegation / handoff | YES | 8 / 12 | no | no | YES (probe:acme:same-user:delegate, probes 5) | YES | 15.1 |
| D7-shared-log | logs | YES | 2 / 5 | no | no | YES (probe:acme:same-user:read_logs, probes 7) | YES | 7.1 |
| D8-pinned-artifact-path | artifacts / persistence | YES | 1 / 4 | no | no | YES (probe:acme:same-user:list_artifacts, probes 6) | YES | 6.8 |
| D9-shared-consolidation-buffer | memory (latent, via consolidation) | YES | 2 / 5 | no | no | YES (probe:acme:same-user:recall, probes 9) | YES | 6.7 |

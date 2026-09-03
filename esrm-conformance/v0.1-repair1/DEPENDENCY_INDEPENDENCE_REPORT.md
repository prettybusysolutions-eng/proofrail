# Dependency Independence Report - Repair 1

No Rust or Go implementation code exists in this phase. This report freezes the independence contract for future implementation.

| Concern | Rust track | Go track | Shared implementation allowed |
| --- | --- | --- | --- |
| Raw-byte intake | Rust-owned code/crate only | Go-owned code/module only | No |
| JSON parsing | Rust parser selected in implementation phase | Go parser selected in implementation phase | No |
| Duplicate-member detection | Rust-native implementation | Go-native implementation | No |
| RFC 8785 JCS | Rust implementation/library | Go implementation/library | No |
| Base64url | Rust implementation/library | Go implementation/library | No |
| Ed25519 verification | Rust implementation/library | Go implementation/library | No |
| JSON Schema Draft 2020-12 | Rust validator | Go validator | No |
| SHA-256/commitment | Rust implementation/library | Go implementation/library | No |

Shared artifacts allowed: normative source, schemas, registries, risk register, manifests, and vector bytes.

Forbidden: FFI bridges, subprocess delegation between tracks, generated shared validators, copied source logic, or one language invoking the other for conformance decisions.

NO CLAIM OF CONFORMANCE.

# ESRM Repair 2 Dependency-Independence Report

No Rust or Go implementation exists in this phase. Future tracks are gated as follows.

| Capability | Rust track | Go track | Shared implementation allowed |
| --- | --- | --- | --- |
| Raw-byte parsing | Rust-native only | Go-native only | No |
| JSON parsing | Independent Rust crate or implementation | Independent Go package or implementation | No |
| RFC 8785 JCS | Independent Rust implementation | Independent Go implementation | No |
| Base64url | Independent Rust implementation | Independent Go implementation | No |
| SHA-256 / commitment | Rust crypto implementation | Go crypto implementation | No |
| Ed25519 verification | Rust Ed25519 verifier | Go Ed25519 verifier | No |
| JSON Schema | Rust validator | Go validator | No |

Shared binary vectors and manifests may be read by both tracks after audit, but neither track may shell out to the other for conformance decisions.

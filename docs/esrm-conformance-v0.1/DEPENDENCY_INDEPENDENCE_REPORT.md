# ESRM v0.1 Dependency-Independence Report

Status: pre-implementation constraint report. No Rust or Go implementation code exists in this phase.

Required independence matrix:

| Concern | Rust track requirement | Go track requirement | Shared implementation allowed |
| --- | --- | --- | --- |
| Raw-byte intake | Rust standard/file byte APIs or Rust crate selected later | Go standard/file byte APIs or Go module selected later | No |
| JSON parsing | Rust parser selected later | Go parser selected later | No |
| Duplicate-key detection | Rust-native detection selected later | Go-native detection selected later | No |
| Canonicalization | Stopped until ESRM canonicalization text is authoritative | Stopped until ESRM canonicalization text is authoritative | No |
| Base64 | Rust codec selected later | Go codec selected later | No |
| Signature verification | Rust crypto crate selected later | Go crypto package/module selected later | No |
| JSON Schema | Rust validator selected later | Go validator selected later | No |
| SHA-256/commitment | Rust implementation selected later | Go implementation selected later | No |

Allowed sharing: raw vector files, expected-result manifests, registry JSON, and prose specifications.

Forbidden sharing: generated validators, canonicalization functions, parser wrappers, Base64 adapters, signature adapters, schema validators, digest/commitment code, FFI bridges, subprocess calls into the other language track, or copied source files across tracks.

Result: dependency independence is constrained by policy, not yet demonstrated by implementation. Demonstration is blocked until ChatGPT audits these artifacts and implementation begins.

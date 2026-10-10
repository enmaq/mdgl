# mdgl (Rust - subset, NOT conformant)

A tiny **subset** checker for [MDGL](https://github.com/enmaq/mdgl). It is not an
MDGL parser and does not pass the conformance suite. The Go module is the reference.

## Scope

Checked (mirrors the Go reference on these rules only): input <= 256 KiB, each
line <= 16 KiB, a single `scene` header with `width` (1..200), `height` (1..60)
and `fallback`, no unknown/duplicate scene keys, optional leading `mdgl 0.1`,
scene before actors before actions, <= 64 actors, <= 1024 actions.

NOT checked: full grammar, actor/action bodies, references, timing, arguments,
`period`/`repeat`/`fps`/`fallback` values, string limits, rendering, frames.
Rust `&str` is always UTF-8, so raw-byte UTF-8 validation is not applicable.

An empty result means "no limit/header problems found", **not** "valid MDGL".

```rust
assert!(mdgl::check("scene width=8 height=1 fallback=end\n").is_empty());
assert!(!mdgl::check("scene width=8 height=1\n").is_empty());
```

## Install and versions

```
cargo add mdgl
```

```rust
let diags = mdgl::check(source); // Vec<mdgl::Diag> {line, col, message}; empty = no limit/header problems
```

Versions track the shared MDGL release (`VERSION`). The package will be published with the 0.2.0 cohort; see [RELEASING.md](../RELEASING.md).

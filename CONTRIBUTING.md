# Contributing to MDGL

MDGL is a language first and a library second. The specification (`SPEC.md`) and the conformance
suite (`conformance/`) are the product; implementations come and go. Second and third
implementations (Rust, JavaScript/WebGL, ...) are very welcome.

## Ground rules
- **Conformance must pass.** `go test ./...` (from `go/`) runs every file in `conformance/`. A change that alters
  a frame or a diagnostic must change the matching `.expect` / `.err` file in the same commit and
  explain why in the PR.
- **Syntax changes go through an RFC.** Open a short document in `rfcs/NNNN-title.md` (problem,
  proposal, alternatives, effect on LLM authoring, conformance cases) before sending code. Small
  fixes (typos, error messages, bugs) need no RFC.
- **Keep it small and deterministic.** A frame is a pure function of (scene, time, size). No clocks,
  randomness or host state in `parse`, `check`, `eval` or `render`.
- **LLM-first.** Every action keeps one obvious spelling, and every error names the valid options.
  New syntax must be explainable in the primer (`MDGL.md`) in a line or two.
- **No new dependencies** without a discussion; the core stays dependency-light.

## Checks before a PR
```
cd go
go vet ./...
go test ./...
go test ./parse -run '^$' -fuzz FuzzParse -fuzztime 20s
```

## Licensing
Code is dual-licensed MIT OR Apache-2.0; the specification text (`SPEC.md`) is CC BY 4.0 and the
conformance suite follows the code licence. By contributing you agree your work is available under
those terms. Contributions carry no copyright assignment.

## Releasing
Registry packages (npm, crates.io, PyPI), the first-claim procedure and the Go/C notes are in
[RELEASING.md](RELEASING.md). Bump the language's manifest version to release it.

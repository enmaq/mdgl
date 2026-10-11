# MDGL — MarkdownGL

![A rotating wire cube, rendered as terminal braille cells](docs/media/cube-rotate.gif)

*A rotating wire cube, rendered as terminal braille cells. [Full video](docs/media/cube-rotate.mp4).*

Why does it exist? More and more engineering now happens over SSH, in terminals, side by side
with coding agents. Sooner or later you need more than static text there: animated 2D and 3D
graphics that live right inside your Markdown. MDGL is our answer to that.

**MDGL is a small, line-based animation language that lives inside a Markdown fence.**
A scene is a few lines of text that a person or an LLM can write correctly the first time, and
that renders as terminal cells (the only shipped renderer, in Go; a browser renderer is planned, not available). It is modelled on WebGL/three.js (actors, a
transform stack, Euler rotation, CSS easing), not on a drawing API.

> Status: **0.x, unstable.** Syntax may change between minor versions; the
> [specification](SPEC.md) and the [conformance suite](conformance/) are the contract.

## Example

Put a scene in a fence labelled `mdgl`; renderers that know MDGL play it, everyone else sees the text:

```mdgl
scene width=40 height=10 period=4 repeat=infinite fallback=end
actor title = text("Build complete") at (2,1) color=green
actor box = cube(size=6,style=wire) at (26,2) color=cyan
@0: title.fade(in,dur=1,ease=ease-out)
@0: box.rotate(y=360,dur=4,ease=linear)
```

Times are absolute seconds. Names are explicit, a typo is an error with a suggestion, and the
last value of every action freezes. `fallback=end` picks the still frame for plain Markdown viewers
and reduced-motion users.

## Videos

- [Writing a scene: type and fade](docs/media/type-fade.mp4) ([GIF](docs/media/type-fade.gif)).
- [Wire cube rotation](docs/media/cube-rotate.mp4) ([GIF](docs/media/cube-rotate.gif)) — the lead demo above.
- [Token moving along arrows](docs/media/move-path.mp4) ([GIF](docs/media/move-path.gif)).

## Install and use

```
# Published: the Go module github.com/enmaq/mdgl/go is tagged v0.2.0 (nested tag go/v0.2.0).
# The source tree is the 0.3.0 release candidate (not yet tagged or published):
go install github.com/enmaq/mdgl/go/cmd/mdgl@v0.2.0

# Historical: the old root-module CLI (v0.1.1) predates the move and is superseded:
# go install github.com/enmaq/mdgl/cmd/mdgl@v0.1.1

# From source (0.3.0 release candidate), in this monorepo:
cd v/mdgl/go
go install ./cmd/mdgl

mdgl check scene.mdgl                   # line:col errors, or "OK MDGL 0.1"
mdgl frames scene.mdgl --at 0,1.5,3     # print frames as text
mdgl play scene.mdgl                    # animate in the terminal (Ctrl+C stops)
```

The npm package `@enmaq/mdgl` (`npm install @enmaq/mdgl`), the crates.io crate `mdgl`
(`cargo add mdgl`) and the PyPI package `mdgl` (`pip install mdgl`) are published at `0.2.0`.
Go is imported from the module path `github.com/enmaq/mdgl/go`, tagged `v0.2.0` (nested tag
`go/v0.2.0`); install its CLI with `go install github.com/enmaq/mdgl/go/cmd/mdgl@v0.2.0`.

Ready-made scenes are in [`examples/`](examples/). `MDGL.md` is a one-page primer for LLMs.

## Embedding (Go)

```go
scene, diags := mdgl.Parse(source)          // diags carry line, column and a message
if len(diags) > 0 { return diags[0] }
cells := scene.Frame(1.5, 80, 24)           // pure function of (scene, time, size)
for _, line := range cells.Lines() { fmt.Println(line) }
fmt.Println(scene.FallbackFrame(80, 24).Lines()) // the still frame for readers that cannot animate
```

A frame is deterministic: the same scene, time and size always give the same cells.

## What is here

| Path | What |
| --- | --- |
| `SPEC.md` | the language, timing rules, GL conventions, limits |
| `conformance/` | `.mdgl` inputs with expected frames (`.expect`) or exact diagnostics (`.err`) |
| `go/parse/`, `go/check/`, `go/eval/`, `go/render/cells/` | the reference implementation |
| `go/cmd/mdgl` | the CLI |
| `MDGL.md` | primer for LLMs (argument lists generated from the checker) |

## Implementations

The Go library here is the reference. A second, independent implementation passing the same
conformance suite is what makes MDGL a standard: see [CONTRIBUTING.md](CONTRIBUTING.md), the
[adopter guide](docs/ADOPTER-GUIDE.md), the [adoption roadmap](docs/ADOPTION-ROADMAP.md) and the project draft
[RFC 0001](rfcs/0001-mdgl-interoperability-and-registration-roadmap.md) (not an IETF document; no media type is registered).

## Licence

Code: MIT OR Apache-2.0, at your option ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)).
Specification text (`SPEC.md`): CC BY 4.0. Conformance suite: same as the code.
Created and maintained by Victor Brunko; see [AUTHORS](AUTHORS).

## Language packages (subset)

`rust/`, `ts/` (the single npm package `@enmaq/mdgl`, serving JS and TypeScript; `js/` is only a marker), `python/` and `c/` (source tarball only) are, as **published at 0.2.0**, early **subset** packages (the source tree, the 0.3.0 release candidate, goes further, see [Release candidate in source](#release-candidate-in-source-030); versions track the shared `VERSION`, currently 0.3.0). Each offers only a resource-limit and scene-header check (input/line size, `width`/`height`/`fallback`, actor and action counts). They are not conformant, do not parse MDGL or render, and a clean result means "no limit/header problems found", not "valid MDGL". The Go module is the reference implementation.

## Language support (0.3.0 release candidate in source)

This table describes what the source tree contains (VERSION and manifests say 0.3.0). It is **not** what is published: see Distribution below and [Release candidate in source](#release-candidate-in-source-030).

| Capability (in source) | Go | Rust | C | JS/TS (npm `@enmaq/mdgl`) | Python |
| --- | --- | --- | --- | --- | --- |
| Full parser, checker, evaluator, renderer | YES | YES | YES | YES | YES |
| Conformance adapter ([`conformance/`](conformance/)) | YES | YES | YES | YES | YES |
| Terminal player (`mdgl play FILE`) | YES | YES | YES | YES | YES |
| Install from source (0.3.0 release candidate) | `cd go && go install ./cmd/mdgl` | `cargo install --path . --root "$PWD/.local"` (in `rust/`) | `cmake -S c -B c/build && cmake --build c/build` | `npm --prefix ts run build` | `pip install -e .` (in `python/`) |

### Distribution (what is published today)

| | Go | Rust | C | JS/TS (npm `@enmaq/mdgl`) | Python |
| --- | --- | --- | --- | --- | --- |
| Published today | 0.2.0 full (tag `go/v0.2.0`) | 0.2.0 seed (limited) | 0.2.0 seed tarball (limited) | 0.2.0 seed (limited) | 0.2.0 seed (limited) |
| Registry install | `go install github.com/enmaq/mdgl/go/cmd/mdgl@v0.2.0` | `cargo add mdgl` | source tarball, no registry | `npm install @enmaq/mdgl` | `pip install mdgl` |

0.3.0 is a release candidate in source until it is actually published; it is on no registry and has no tag.

Any all-language source edit (including Go) triggers full cohort validation; the Go tag is a separate release step from the registries, and a registry-only success is not a complete release.

The non-Go packages are published at 0.2.0 (npm `@enmaq/mdgl`, crates.io `mdgl`, PyPI `mdgl`) as
limited seed checks (header/resource checks, not the full Go parser and renderer). The Go module is
`github.com/enmaq/mdgl/go`, tagged `go/v0.2.0`. At 0.x only the latest
minor is supported and nothing is promised stable before 1.0. See [RELEASING.md](RELEASING.md).

The package version (`VERSION`, 0.3.0 release candidate) is not the grammar version: the `mdgl 0.1` header is defined
by [SPEC.md](SPEC.md) and does not change with `VERSION`. Before 1.0 there is no ABI or API
stability promise; supported builds are the ones in CI.

## Release candidate in source (0.3.0)

Everything in this section exists only in the source tree, the 0.3.0 release candidate (`VERSION` and manifests say 0.3.0). It is **not** in the published
0.2.0 packages (those remain the seed checks above), and none of it is
published or tagged. In the final integration (2026-10-10 UTC) all five adapters (Go, Rust, C, TypeScript/JS, Python) pass the
83-fixture corpus (63 normative + 20 non-normative) under the bounded protocol-v1 profile; the current corpus is 86 fixtures (64 normative + 22 non-normative): the 3 later `obs_circle_*` fixtures were matched by all five adapters in a targeted run, and the current 86-fixture corpus (64 normative + 22 non-normative) passed on all five adapters in an independent verification on 2026-10-10 UTC (accepted by the coordinator); verification of the new 0.3 integration (players, version bump, packages) is still pending; all fixture
expectations are hand-derived from SPEC. That is bounded evidence, not a universal SPEC certification, and no
full-conformance claim is made for any implementation. C note: the library builds with `_GNU_SOURCE` and its
locale-dependent test is skipped when `de_DE.UTF-8` is not installed.

Each language folder now contains a parser, a checker, an evaluator and a terminal-cell renderer
(as stated by that folder's sources and README), plus an adapter for the
[observable conformance protocol v1](conformance/PROTOCOL.md). JavaScript is the compiled
TypeScript in the same npm package (`@enmaq/mdgl`), not an independent implementation.

| Language | Capability in source | Adapter command (build first; run from the `v/mdgl` checkout, paths absolute for the runner) | Own tests that read the shared fixtures |
| --- | --- | --- | --- |
| Go | published full implementation, plus adapter | `cd go && go build -o <out>/mdgl-conformance ./cmd/conformance`, then `<out>/mdgl-conformance` | `go/conformance_test.go` (legacy fixtures); `go/cmd/conformance/main_test.go` is transport only |
| Rust | parse, check, evaluate, render, adapter | `cargo build --release --manifest-path rust/Cargo.toml --bin mdgl-adapter`, then `rust/target/release/mdgl-adapter` | `rust/tests/conformance.rs`, `rust/tests/frames.rs` (legacy and observable fixtures), `rust/tests/adapter.rs` |
| C | parse, check, evaluate, render, adapter | `cmake -S c -B c/build && cmake --build c/build`, then `c/build/mdgl_adapter` | `c/test_adapter.py` (transport); `c/test_render.c` derives from SPEC and protocol examples |
| TypeScript / JS | parse, check, evaluate, render, adapter | `npm --prefix ts run build`, then `node ts/bin/mdgl-adapter.js` | `ts/test/corpus.test.js`, `ts/test/expect.test.js`; `ts/test/adapter.test.js` |
| Python | parse, check, evaluate, render, adapter | `env PYTHONPATH=<checkout>/python python3 -m mdgl.adapter` | `python/tests/test_parse_check.py`, `python/tests/test_render.py` (legacy fixtures); `python/tests/test_adapter.py` |

Run the shared runner against any adapter:

```
python3 scripts/conformance-runner.py --adapter '<cmd>'
```

The fixture inventory (86 fixtures: 64 normative, 22 non-normative) and known open gaps are in
[`conformance/README.md`](conformance/README.md).

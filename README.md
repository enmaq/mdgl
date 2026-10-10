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
# Until the first shared release, the published CLI remains the old root module:
go install github.com/enmaq/mdgl/cmd/mdgl@v0.1.1

# For local development in this monorepo, install from the moved module:
cd v/mdgl/go
go install ./cmd/mdgl

mdgl check scene.mdgl                   # line:col errors, or "OK MDGL 0.1"
mdgl frames scene.mdgl --at 0,1.5,3     # print frames as text
mdgl play scene.mdgl                    # animate in the terminal (Ctrl+C stops)
```

The npm package `@enmaq/mdgl` (`npm install @enmaq/mdgl`), the crates.io crate `mdgl`
(`cargo add mdgl`) and the PyPI package `mdgl` (`pip install mdgl`) are published at `0.2.0`.
Go is imported from the module path `github.com/enmaq/mdgl/go`; its release tag is a separate
step. Once tagged, install the nested module with
`go install github.com/enmaq/mdgl/go/cmd/mdgl@v0.2.0`.

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
conformance suite is what makes MDGL a standard: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Code: MIT OR Apache-2.0, at your option ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)).
Specification text (`SPEC.md`): CC BY 4.0. Conformance suite: same as the code.
Created and maintained by Victor Brunko; see [AUTHORS](AUTHORS).

## Language packages (subset)

`rust/`, `ts/` (the single npm package `@enmaq/mdgl`, serving JS and TypeScript; `js/` is only a marker), `python/` and `c/` (source tarball only) are early **subset** packages (versions track the shared `VERSION`, currently 0.2.0). Each offers only a resource-limit and scene-header check (input/line size, `width`/`height`/`fallback`, actor and action counts). They are not conformant, do not parse MDGL or render, and a clean result means "no limit/header problems found", not "valid MDGL". The Go module is the reference implementation.

## Language support

| Capability | Go | Rust | C | JS/TS (npm `@enmaq/mdgl`) | Python |
| --- | --- | --- | --- | --- | --- |
| Full parser, checker, evaluator, renderer | YES | NO | NO | NO | NO |
| Header and resource-limit seed check | YES | YES | YES | YES | YES |
| Conformance suite ([`conformance/`](conformance/)) | runs it | not claimed | not claimed | not claimed | not claimed |
| Terminal player (`mdgl play`) | YES | NO | NO | NO | NO |
| Install | `go install ./cmd/mdgl` from `go/` (see above) | `cargo add mdgl` | source tarball, no registry | `npm install @enmaq/mdgl` | `pip install mdgl` |
| Status | reference | seed (limited) | seed (limited) | seed (limited) | seed (limited) |

Any all-language source edit (including Go) triggers full cohort validation; the Go tag itself is released separately and a registry-only success is not a complete release.

The non-Go packages are published at 0.2.0 (npm `@enmaq/mdgl`, crates.io `mdgl`, PyPI `mdgl`) as
limited seed checks (header/resource checks, not the full Go parser and renderer). The Go module is
`github.com/enmaq/mdgl/go`; its release tag `go/v0.2.0` is a separate step. At 0.x only the latest
minor is supported and nothing is promised stable before 1.0. See [RELEASING.md](RELEASING.md).

The package version (`VERSION`, 0.2.0) is not the grammar version: the `mdgl 0.1` header is defined
by [SPEC.md](SPEC.md) and does not change with `VERSION`. Before 1.0 there is no ABI or API
stability promise; supported builds are the ones in CI.

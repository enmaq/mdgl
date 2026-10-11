# Changelog

All notable changes to MDGL. The format follows [Keep a Changelog](https://keepachangelog.com/);
0.x versions are unstable and may change the syntax between minor versions.

## [Unreleased]

- Documentation only: the README now leads with the neon cube preview and lists the neon-cube, Kubernetes and LLM videos; no code, API or version change.

## [0.3.1] - 2026-10-11

### Added
- Showcase example scenes `examples/neon-cube.mdgl`, `examples/kubernetes.mdgl` and `examples/llm.mdgl` (current 0.1 grammar), with preview GIFs and README adopter docs.
- Launcher `scripts/example-media.py` (default `play`, unchanged: plays the three demos in a UTF-8 terminal with the Go adapter) gains `verify` and `export`, implemented in `scripts/example_media_export.py`: both build all five adapters in an isolated temp stage, check each scene through each adapter and compare every frame exactly (rune, fg, bg, `done`; the fallback frame separately), stopping at the first difference with a precise report and a non-zero exit; `export` then rasterises and encodes GIF/MP4 only if all five agree and writes a manifest of cell and sequence hashes plus tool and font versions. Encoded bytes are only reproducible with the same ffmpeg and font versions.
- CI job `example-media-e2e` runs `export` and uploads the media, manifest and failure report as artifacts (read-only permissions, no commits).

### Fixed
- Opacity/fade colour blending now composites source-over onto the cell's current colour (the glyph colour already in the cell, else the background). The TypeScript adapter previously blended onto the background only and produced different `fg` values at fade frames (for example `neon-cube` at `time_ns` 33333333); found by the all-five frame comparison.
- The timeline is evaluated on integer nanoseconds before elapsed/progress arithmetic: time, action begin and duration are quantized first, elapsed is an integer difference, then one floating-point division feeds the easing, so exact midpoints (progress 0.5) agree across implementations. Changed in Go (`go/eval`), Rust (`rust/src/eval.rs`), C (`c/mdgl_render.c`) and Python (`python/mdgl/evaluate.py`); clarified in `conformance/PROTOCOL.md` section 2.1. New regression tests cover this in Go, Rust, C, TypeScript and Python.

## [0.3.0] - 2026-10-10

Provenance: the registry packages for 0.3.0 (npm `@enmaq/mdgl`, crates.io `mdgl`, PyPI `mdgl`, C source tarball) carry corrected package-facing metadata and README text (version-neutral descriptions and READMEs) relative to the public 0.3.0 git tags, which retain the original source tree. Code, API, version and tag-covered files (`go/`, `conformance/`, `SPEC.md`, `VERSION`) are unchanged.

Full parser, checker, evaluator and terminal-cell renderer, plus a conformance adapter, for Rust, C, TypeScript/JavaScript (one npm package, `@enmaq/mdgl`) and Python; Go was already full. The shared corpus has 86 fixtures (64 normative + 22 non-normative); all five adapters pass it under the bounded protocol-v1 profile: bounded evidence, not a universal SPEC certification.

### Added
- Shared observable conformance protocol v1 (`conformance/PROTOCOL.md`, `conformance/protocol.schema.json`; status: wire v1 accepted, field set unchanged, implementation evidence gates still open) and a language-neutral runner (`scripts/conformance-runner.py`) with its self-tests (`scripts/test_conformance_runner.py`, using a test-double adapter).
- Observable fixtures in `conformance/observable/` (`.obs.json`: colours, `done`, fallback frames, a hand-derived `derivation`), added to the legacy fixtures to make the 86-fixture corpus (64 normative, 22 non-normative). All expectations are hand-derived from SPEC.
- Non-normative reference geometry profile (`conformance/REFERENCE_PROFILE.md`) and `obs_ref_*` fixtures (rect, circle, coloured cube) that exist only under that profile, which differs from SPEC in the rect/circle dot offset.
- Go: headless conformance adapter `go/cmd/conformance`.
- Rust: parser, checker, evaluator, terminal-cell renderer and the `mdgl-adapter` binary; tests read the shared fixtures directly (`rust/tests/conformance.rs`, `rust/tests/frames.rs`), not through the runner.
- C: parser, checker, evaluator, terminal-cell renderer (`mdgl_render.c`) and the `mdgl_adapter` executable with transport tests.
- TypeScript/JavaScript: parser, checker, evaluator, terminal-cell renderer and the adapter (`bin/mdgl-adapter.js`), compiled by `tsc` to the JavaScript in the same npm package (not an independent implementation); tests read the shared fixtures directly.
- Python: parser, checker, evaluator, terminal-cell renderer and the adapter (`python3 -m mdgl.adapter`); tests read legacy fixtures directly.
- Terminal players: `mdgl play FILE` in Rust, C, TypeScript/JavaScript (`bin/mdgl.js`) and Python (`mdgl.cli`), alongside the existing Go one. Each animates the scene in the terminal and Ctrl+C stops it (exit 130 for Rust, C, TypeScript/JavaScript and Python; exit 0 for Go, which handles SIGINT and returns normally). When stdout is not a terminal, or `MDGL_REDUCED_MOTION` is set and non-empty (`NO_COLOR` too in Rust, C and Python), the fallback frame is printed once as plain text, without escapes or timers.
- Documentation: project draft `rfcs/0001-mdgl-interoperability-and-registration-roadmap.md` (not an IETF document; no media type registered), `docs/ADOPTER-GUIDE.md` and `docs/ADOPTION-ROADMAP.md`.

### Changed
- The rect, circle and coloured-cube observable cases are non-normative; normative rect/circle observables remain an open gap.

## [0.2.0] - 2026-10-10

One shared version for every language, starting here.

### Naming
- npm: unscoped `mdgl` was refused (E403, name similarity). `@wildneuro/mdgl` 0.2.0 was published first under the maintainer's personal scope and is superseded by the canonical `@enmaq/mdgl`.

### Added
- Rust, C, TypeScript/JavaScript (one npm package, `@enmaq/mdgl`) and Python packages. These are limited header/resource seed checks, not full parsers or renderers. Each checks: input size, line length, scene header width/height/fallback, key rules, statement order, and actor and action counts.
- Root `VERSION` file as the single release version source, and `check-version.sh` to verify every package matches it and the newest changelog heading.

### Changed
- The Go module moved to `go/`; the import path is now `github.com/enmaq/mdgl/go`. Versions v0.1.0 and v0.1.1 at the old root path remain.
- Go, Rust, C, JavaScript, TypeScript and Python share one version from 0.2.0.

## [0.1.1] - 2026-10-09

### Fixed
- README: removed leftover placeholder lines (playground / demo GIF); the demo videos are in the Videos section.

## [0.1.0] - 2026-10-09

First public release.

### Added
- **Language 0.1** (`SPEC.md`): `scene`, `actor`, timed actions (`@seconds: name.action(...)`),
  SMIL timing rules (absolute times, explicit `period`, end values freeze, overlap on one property
  is an error), CSS easing names, parent-relative coordinates and a WebGL-style transform order.
- **Actors:** `text`, `rect`, `circle`, wire `cube` (Euler XYZ like three.js, degrees or `rad`).
- **Actions:** `fade`, `move`, `scale`, `color`, `type`, `blink`, `wipe`, `slide`, `rotate` (cube).
- **Go library** (`github.com/enmaq/mdgl`): `Parse`, `Scene.Frame`, `FallbackFrame`, `Active`,
  `Signatures`; packages `parse`, `check`, `eval`, `render/cells` (braille and half-block terminal cells).
- **CLI** `mdgl`: `check FILE`, `frames FILE --at t1,t2`, `play FILE`.
- **Conformance suite** (`conformance/`): `.mdgl` inputs with expected frames (`.expect`) or exact
  diagnostics (`.err`); any implementation that passes it is MDGL 0.1 conformant.
- **Primer** `MDGL.md`: one page for LLMs, with exact argument lists generated from the checker.
- Examples in `examples/` (cubes, text, scene graph, UI motion).

### Not in 0.1 (reserved)
Camera, lights, meshes, materials, three.js scene import, solid faces, `def`/`seq`, images, paths,
`#rrggbb` colours, a depth buffer.

# mdgl (Rust - development)

Parser, checker, evaluator and terminal-cell renderer for [MDGL](https://github.com/enmaq/mdgl) 0.1,
developed from `SPEC.md` and the shared `conformance/` corpus. Development tree only: the
published 0.2.0 crate (a limited header/resource seed check, immutable) does not contain this code.
Everything below is unreleased. In the final integration (2026-10-10 UTC) it passed, together with the four other adapters, the 83-fixture corpus (63 normative + 20 non-normative) under the bounded protocol-v1 profile; that is bounded evidence, not a universal SPEC certification.

## Implemented

- `parse(&str) -> Result<Scene, Diag>`: lexer + statement parser, Go-style quoted escapes,
  UTF-8 byte columns, finite non-exponent decimals, scene-before-actor-before-action,
  input/line/actor/action limits.
- `check_scene(&mut Scene) -> Result<(), Diag>`: scene keys/limits, period/repeat/fps/fallback,
  duplicate/unknown names with did-you-mean (edit distance <= 2), parent references (forward
  allowed, cycles rejected), all shape and action argument types, overlapping properties,
  nanosecond rounding, period/60 s bounds, grapheme limits.
- `parse_checked(&str) -> Result<Scene, Diag>` and `check(&str) -> Vec<Diag>` (empty = valid;
  at most the first diagnostic, `line:col: message`).

## Quick start

From a checkout, in the `rust/` directory (needs a Rust toolchain, edition 2021):

```
cargo run --example render                         # shared ../examples/text.mdgl at t=5s
cargo run --example render -- --at 1.0             # a frame at 1.0 seconds
cargo run --example render -- --fallback           # the scene's fallback frame
cargo run --example render -- path/to/scene.mdgl   # your own scene
```

`examples/render.rs` is the whole program: `mdgl::parse_checked(&source)` then `scene.frame(t, w, h)` or
`scene.fallback_frame(w, h)`, printing `frame.lines()`. Exit code 0 on success, 1 for an invalid scene
(first diagnostic `PATH:line:col: message` on stderr), 2 for usage errors or an unreadable file.

## Frames

```rust
let scene = mdgl::parse_checked("scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n").unwrap();
let f = scene.frame(1.0, 8, 1);          // absolute seconds; pure, any seek order
assert!(!f.done);                         // Frame { width, height, cells: [[Cell { rune, fg, bg }]], done }
let _ = scene.frame_ns(2_000_000_000, 8, 1); // integer nanoseconds (wire-protocol unit)
let _ = scene.fallback_frame(8, 1);       // start | end | @t, ignoring repeat
```

Text, rect, circle and cube; braille 2x4 dots; RGB source-over blending (`#rrggbb`, background
empty = default black); easing; move/fade/scale/color/type/blink/wipe/slide/rotate; parents and
integer `z` paint order; period/repeat/done and fallback. Cluster width and glyph choice follow
Go uniseg v0.4.7 (Unicode 15.0.0; generated tables in `src/width_tables.rs`, MIT notice in its header).

## Known gaps

- Grapheme clusters: UAX #29 extended clusters from `unicode-segmentation` =1.10.1 (Unicode 15.0.0, the reference profile of Go uniseg v0.4.7; not declared a universal MDGL norm).
- `\xNN` escapes producing invalid UTF-8 are rejected as `invalid string escape`.
- No CLI. The NDJSON adapter source `src/bin/mdgl-adapter.rs` (`cargo build --release --bin mdgl-adapter`) implements protocol v1 (see `conformance/PROTOCOL.md`); run it with `scripts/conformance-runner.py --adapter <path>`. In the final integration (2026-10-10 UTC) it passed, together with the four other adapters, the 83-fixture corpus (63 normative + 20 non-normative) under the bounded protocol-v1 profile; that is bounded evidence, not a universal SPEC certification.
- Evaluator and renderer follow SPEC but were cross-read against the Go reference; normative coverage of cube glyphs is glyph-level only; rect, circle and cube colour exist only as non-normative reference-profile fixtures (`obs_ref_*`), and normative rect/circle coverage remains an open gap (protocol G7). All expectations are hand-derived.

```
cargo test   # unit tests + shared .err/.expect corpus
```

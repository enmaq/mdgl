# mdgl (Rust)

Full parser, checker, evaluator, terminal-cell renderer and terminal player for [MDGL](https://github.com/enmaq/mdgl) 0.1,
developed from `SPEC.md` and the shared `conformance/` corpus, with a protocol-v1 conformance adapter (`mdgl-adapter`).
The 0.2.0 crate was an earlier limited header/resource check.

The current shared corpus has 86 fixtures (64 normative + 22 non-normative or profile-assumption); all five adapters (Go, Rust, C, TypeScript/JavaScript, Python) passed it in an independent verification on 2026-10-10 UTC, accepted by the coordinator. That is bounded evidence under conformance protocol v1, not a universal SPEC certification.

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

## Command line

```
cargo install mdgl                               # from crates.io (installs the mdgl and mdgl-adapter binaries)
# or from a checkout, in rust/: cargo install --path . --root "$PWD/.local"   (then use .local/bin/mdgl)
mdgl check ../examples/text.mdgl
mdgl frames ../examples/text.mdgl --at 0,2.5
mdgl play ../examples/text.mdgl       # Ctrl+C stops
```

`mdgl play` takes absolute elapsed time from a monotonic clock (frames are never advanced by counting
ticks), redraws only changed cells at the scene fps inside DEC synchronized output (mode 2026), hides the
cursor and always restores it: on normal end of a finite scene, on Ctrl+C and on a write error. Glyphs
that are control characters are never sent as escapes. If stdout is not a terminal, or `NO_COLOR` or
`MDGL_REDUCED_MOTION` is set and non-empty, it prints the fallback frame once as plain text with no timers
and no escape sequences. Exit codes: 0 ok, 1 invalid scene or write error, 2 usage or unreadable file,
130 interrupted. On Windows Ctrl+C uses the default handler and the cursor is not restored (untested there).

From code: `mdgl::play(&scene, &mut writer, &mut clock, &stop)` with any `Clock`, writer and stop callback
(`mdgl::SystemClock` is the wall-clock implementation); `mdgl::diff` and `mdgl::plain` give the pieces.
`scripts/pty_proof.py PATH_TO_MDGL` exercises the binary on a real pseudo-terminal.

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
- Terminal player: Unix only is verified. The NDJSON adapter source `src/bin/mdgl-adapter.rs` (`cargo build --release --bin mdgl-adapter`) implements protocol v1 (see `conformance/PROTOCOL.md`); run it with `scripts/conformance-runner.py --adapter <path>`. See the evidence statement at the top.
- Evaluator and renderer follow SPEC but were cross-read against the Go reference; normative coverage of cube glyphs is glyph-level only; rect, circle and cube colour exist only as non-normative reference-profile fixtures (`obs_ref_*`), and normative rect/circle coverage remains an open gap (protocol G7). All expectations are hand-derived.

```
cargo test   # unit tests + shared .err/.expect corpus
```

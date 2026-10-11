# MDGL conformance suite

Legacy fixtures: `NAME.mdgl` with `NAME.expect` (glyph rows per `@seconds`) or `NAME.err` (first diagnostic,
`line:col: message`). Observable fixtures (`conformance/observable/obs_*.obs.json` plus the sibling `.mdgl` named by `source_file`; kept in a subdirectory because the Go legacy test globs `conformance/*.mdgl` at the top level and requires `.err` or `.expect` for each) add colours,
`done`, fallback frames and a mandatory hand-derived `derivation`. Every non-fallback observable frame carries an explicit boolean `done`.

Provenance: wire protocol [PROTOCOL.md](PROTOCOL.md) (inventory in its Appendix A), schema [protocol.schema.json](protocol.schema.json), reference geometry profile [REFERENCE_PROFILE.md](REFERENCE_PROFILE.md).

## Fixture inventory

The runner computes the tallies from the files: 46 legacy + 40 observable = **86 fixtures**, of which **64 are normative** (46 legacy + 14 original observable + 3 cube + 1 `obs_circle_r100_accept`) and **22 are non-normative** (14 assumption-based originals + 3 fallback-cube + 3 reference-profile `obs_ref_*` + 2 circle-reject `obs_circle_r101_reject/_r0_reject`).

| Group | Fixtures | Status |
| --- | --- | --- |
| (i) Normative, SPEC-derived | 46 legacy (glyph rows or first diagnostic) and 14 original observable (colours, `done`, repeat, seek purity) | normative |
| (ii) Glyph-only legacy and cube fixtures | legacy `cube_*` and the 3 observable `obs_shape_cube_*`: glyphs only, no colour or background claim (the 3 `obs_shape_cube_*_fb` fallback variants are non-normative, G1) | normative (fallback variants non-normative) |
| (iii) Reference-profile cases | `obs_ref_rect_2x1_red`, `obs_ref_circle_r05_green`, `obs_ref_cube_x_30_red`: rect, circle and cube colour under an explicit [reference profile](REFERENCE_PROFILE.md) that differs from SPEC in the rect/circle dot offset | NON-NORMATIVE |
| (iv) Assumption-labelled | fixtures marked `ASSUMES` G1, G2, G4, G5 or A1-A4 (see PROTOCOL.md section 9 and Appendix A) | non-normative |
| (v) Circle bound (SPEC clarification: radius <= 100) | `obs_circle_r100_accept` (static, off-stage placement, normative); `obs_circle_r101_reject`, `obs_circle_r0_reject` (diagnostic, wording differs between adapters, G4/G10) | accept normative, rejects non-normative; five adapters agree (targeted run), wording agreement observed, not SPEC |

Known open gaps: title epsilon, reveal/transform, rasterization extents and the offset mismatch with SPEC (normative rect/circle observables are still missing, G7), easing curves, remaining stage limits, reserved-vocabulary diagnostics.

All expectations are hand-derived from SPEC (not generated from any implementation). In the final integration (2026-10-10 UTC) all five adapters (Go, Rust, C, TypeScript/JS, Python) passed the earlier 83-fixture corpus (historical result) (63 normative + 20 non-normative) under the bounded protocol-v1 profile; the 3 later `obs_circle_*` fixtures were matched by all five adapters in a targeted run; the current corpus is 86 fixtures (64 normative + 22 non-normative); the current 86-fixture corpus (64 normative + 22 non-normative) passed on all five adapters in an independent verification on 2026-10-10 UTC (accepted by the coordinator). This is bounded evidence, not a universal SPEC certification, and no full-conformance claim is made for any implementation. The normative rect/circle/cube-colour raster extents remain open SPEC gaps covered only by the non-normative reference-profile fixtures.

Language-neutral runs go through an adapter speaking the newline-delimited JSON protocol in
[PROTOCOL.md](PROTOCOL.md) (schema: [protocol.schema.json](protocol.schema.json)).

Run (from `v/mdgl`; the adapter is started once with the suite directory as its working directory):

    python3 scripts/conformance-runner.py --adapter './my-adapter' [--class diagnostic,static,timed,repeat,cube] [--json] [--timeout 10]

Exit 0 all pass, 1 a fixture failed, 2 usage error, transport failure, malformed fixture or zero fixtures selected.
Classes without fixtures are printed as `no fixtures`, never as passes. The report counts normative and
non-normative fixtures separately; non-normative passes are `assumption-based pass (not certification)`, and the
last line reads `ALL NORMATIVE FIXTURES PASSED` only if no normative fixture failed, at least one ran, and every class with normative
fixtures ran (a `--class` subset prints `NOT CERTIFIED: ...` instead; no normative fixture at all prints `NOT CERTIFIED: no normative fixtures ran`).
The adapter must answer every request with one LF-terminated line and exit 0 within `--shutdown-timeout` (default 5 s) after stdin EOF; extra output, an unterminated line, a hang or a non-zero exit is a transport failure (exit 2). Fixture times (`.expect` headers, `frames[].time`)
accept `1`, `1.0`, `.5`, `+2`, `1e-3`; negatives (including `-0`), `s` suffixes and NaN/inf are fixture errors.

Runner self-tests (they use `scripts/mock_adapter.py`, a test double that is not an MDGL implementation) and a
self-check of the `.obs.json` files in `observable/`:

    python3 -I scripts/test_conformance_runner.py -v

The Go test `go/conformance_test.go` remains the reference check for the legacy fixtures.

Reference compatibility profile (NON-NORMATIVE, rect/circle/coloured-cube `obs_ref_*` fixtures): [REFERENCE_PROFILE.md](REFERENCE_PROFILE.md).

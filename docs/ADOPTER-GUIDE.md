# MDGL adopter guide

Status: project documentation, informative, 0.x. Not an IETF or RFC Editor document, not 1.0. Reviewed for factual consistency (independent review and a maintainer review pass); remains an unadopted project proposal; not an IETF, RFC Editor or IANA document or endorsement; SPEC.md remains authoritative; no normative adoption is implied by the reviews. The circle clarification is a SPEC.md change made by the project maintainers, not by the review. The normative text is
[SPEC.md](../SPEC.md); this guide never overrides it. Evidence status is stated in
[RFC 0001](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md).

## 1. What MDGL is, and who this is for

MDGL (MarkdownGL) is a small, line-based animation language that lives in a Markdown fence labelled `mdgl`
([README.md](../README.md)). A scene declares a stage, actors (`text`, `rect`, `circle`, wire `cube`) and timed
actions. A frame is a pure function of (scene, time, size).

- **Implementers** writing a parser, checker, evaluator and renderer in another language.
- **Embedders** (terminals, docs tools, chat or agent UIs) that show a scene or its still frame.
- **Doc authors**, people and LLMs, writing scenes ([MDGL.md](../MDGL.md) is a one-page primer).

The only renderer profile is terminal cells (braille dots, 2x4 per cell), available in all five languages. A browser/WebGL renderer is not shipped.

## 2. Current state (2026-10-10 UTC)

| Item | State |
|---|---|
| Go module `github.com/enmaq/mdgl/go`, tags `v0.3.1` and `go/v0.3.1` | Full implementation (parser, checker, evaluator, renderer, adapter, player). |
| npm `@enmaq/mdgl`, crates.io `mdgl`, PyPI `mdgl` at 0.3.1 | Full implementations with adapters and terminal players; JS and TypeScript are one implementation. |
| C | Full implementation with adapter and player; source build via cmake, no registry (see [`c/README.md`](../c/README.md)). |

The git tags retain the original source tree; the registry packages carry corrected version-neutral metadata and README text (see [CHANGELOG.md](../CHANGELOG.md)); code, API and version are unchanged.

All five adapters (Go, Rust, C, TypeScript/JS, Python) pass the current 86-fixture corpus (64 normative + 22 non-normative) under the bounded protocol-v1 profile, in an independent verification on 2026-10-10 UTC (accepted by the coordinator). History: the earlier final-integration result was 83/83 = 63 normative + 20 non-normative; the 3 later circle fixtures were matched by all five adapters in a targeted run. That is **bounded evidence, not a
universal SPEC certification**. See section 8 for what it does not cover.

## 3. Implementing MDGL, in order

Follow [SPEC.md](../SPEC.md) for every rule; this is only an order of work.

1. **Parse.** UTF-8, one statement per line, blank and `#` lines ignored, strict grammar (the `ebnf` block in
   SPEC). Keep source locations: diagnostics are `line:column: message` with one-based UTF-8 **byte** columns.
2. **Check.** References, parents and cycles, arguments, scene keys, duplicates, limits (256 KiB input, 16 KiB line,
   200x60 stage, 64 actors, 1024 actions, 1024 graphemes, 60 s, fps 1..30, repeat 1..1000 or infinite) and
   overlapping actions on one property. Unknown names get a did-you-mean suggestion at edit distance <= 2.
3. **Evaluate at time t.** A pure function of (checked scene, time): nanosecond rounding, half-open intervals,
   freeze, repeat reset, easing, transform stack, opacity, `done` and the fallback frame.
4. **Render cells.** One grapheme per cell, braille shapes, wire-cube projection and clipping, RGB source-over blending
   as `#rrggbb`. No terminal control sequences in cell content.
5. **Adapter.** Wrap it in the newline-delimited JSON process of protocol v1 (section 5).

Where SPEC is silent (section 8), do not treat another implementation's behaviour as normative; report the gap.
Reference adapters for comparison (each builds from the source tree, see the table in
[README.md](../README.md#adapters)): `go/cmd/conformance`, `rust/src/bin/mdgl-adapter.rs`,
`c/mdgl_adapter.c`, `ts/bin/mdgl-adapter.js`, `python/mdgl/adapter.py`.

## 4. Running the conformance suite

From the MDGL project directory (the adapter is started once, with the suite directory as its working directory):

```
python3 scripts/conformance-runner.py --adapter '<cmd>' [--class diagnostic,static,timed,repeat,cube] [--json] [--timeout 10]
```

`--adapter` is split with shlex and run without a shell. `--shutdown-timeout` (default 5 s) bounds adapter exit after
stdin closes. Exit codes: `0` all selected fixtures pass; `1` a fixture failed; `2` usage error, transport failure,
malformed fixture or zero fixtures selected. Read the last line, not only the exit code:

- `ALL NORMATIVE FIXTURES PASSED` only if at least one normative fixture ran, none failed, and every class with
  normative fixtures ran. A `--class` subset prints `NOT CERTIFIED: ...`.
- Non-normative passes print `assumption-based pass (not certification)`.
- Classes without fixtures print `no fixtures`, never a pass.

Runner self-tests use a test double that is not an MDGL implementation:
`python3 -I scripts/test_conformance_runner.py -v`.
Corpus: 86 fixtures = 46 legacy + 40 observable; 64 normative, 22 non-normative (passed on all five adapters in an independent
verification on 2026-10-10 UTC, accepted by the coordinator)
([conformance/README.md](../conformance/README.md)). The 64 normative fixtures are derived from SPEC; the 22 non-normative fixtures rest on documented profile assumptions and provenance (`conformance/REFERENCE_PROFILE.md`, `conformance/PROTOCOL.md`).

## 5. Adapter protocol v1 in short

One JSON request per line on stdin; exactly one LF-terminated JSON response per request on stdout; stderr is for
logs. Requests are sequential, stateless and deterministic. Ops: `check` and `frame`. The request line limit is
2 097 152 bytes. Failure codes: `bad_request`, `unsupported_version`, `invalid_source`, `internal`. A `frame`
success has `cells` (rows of `{"r","fg","bg"}`) and boolean `done` (omitted for `fallback:true`). Invalid UTF-8 in a
request is rejected. Full rules: [PROTOCOL.md](../conformance/PROTOCOL.md),
[schema](../conformance/protocol.schema.json). Examples from PROTOCOL.md section 4 (the three below were also
syntax-checked against the Python adapter; error message wording differs between adapters and is illustrative):

```json
{"v":1,"id":"e2","op":"check","source":"scene width=8 height=1 fallback=end\nactor a = text(\"é\") $\n"}
{"v":1,"id":"e2","ok":true,"diagnostics":[{"line":2,"col":22,"message":"unexpected character \"$\""}]}
```
```json
{"v":1,"id":"e7","op":"frame","source":"scene width=8 height=1 fallback=end\n","time_ns":1.5,"width":8,"height":1}
{"v":1,"id":"e7","ok":false,"error":{"code":"bad_request","message":"time_ns must be an integer in 0..2^53-1"}}
```
```json
{"v":2,"id":"e8","op":"check","source":""}
{"v":1,"id":"e8","ok":false,"error":{"code":"unsupported_version","message":"protocol version 2 is not supported"}}
```

Try one yourself, from any scratch directory (the Python adapter, from source):

```
printf '%s\n' '{"v":2,"id":"e8","op":"check","source":""}' | env PYTHONPATH=<checkout>/python python3 -m mdgl.adapter
```

## 6. Adding fixtures and provenance

- **Legacy:** `NAME.mdgl` plus `NAME.expect` (`@seconds`, then exactly height rows) or `NAME.err` (exact first
  diagnostic), at the top of `conformance/`.
- **Observable:** `conformance/observable/NAME.obs.json` plus the sibling `.mdgl` named by `source_file`, with
  `cols`, `rows`, `class`, a mandatory `derivation` naming the SPEC rule, and `frames`.
- Derive expectations by hand from SPEC, never from an implementation's output. If a derivation depends on
  something SPEC does not fix, write `ASSUMES` and the gap id and set `"normative": false`.
- A change that alters a frame or diagnostic changes the matching fixture in the same commit
  ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## 7. Reporting an ambiguity

Syntax changes go through a short RFC in [`rfcs/NNNN-title.md`](../rfcs/) (problem, proposal, alternatives, effect on
LLM authoring, conformance cases). For an ambiguity, give the SPEC sentence, two readings, a minimal `.mdgl` input,
the time and size, and the output each reading gives. Typos, messages and bugs need no RFC. Gap ids are in
[PROTOCOL.md](../conformance/PROTOCOL.md) section 9.

## 8. Honest limitations

- The 86-fixture (64 + 22) result across five adapters (earlier 83/83 = 63 + 20, historical) is bounded evidence under protocol v1; it is not a universal SPEC certification, and
  the 64 normative fixtures are derived from SPEC and the 22 non-normative ones rest on documented profile assumptions.
- Normative rect, circle and cube-colour raster extents are open SPEC gaps. They are covered only by non-normative
  reference-profile fixtures, whose rect/circle dot offset differs from SPEC.
- The circle size bound is resolved by a project maintainers' decision (SPEC.md clarification, not an IETF or
  standards-body decision): radius <= 100, equivalently diameter <= 200; r > 100 is an error. The Go, Rust, C and
  Python adapters reject a radius above 100, and the TypeScript adapter has been corrected to match. This is
  confirmed by the five adapters on the three circle boundary fixtures (targeted run); independent verification on
  2026-10-10 UTC (accepted by the coordinator) passed the full 86-fixture corpus. The wording agreement of the diagnostic is observed, not a SPEC rule.
- Other open questions (proposals, not rules): title epsilon wording and semantics, reveal and transform, easing
  curves, stage limits beyond 200x60, reserved-vocabulary diagnostics, diagnostic wording beyond `.err`, fallback
  `done`, viewport clamp, blend rounding, extension namespacing, Unicode version. See
  [RFC 0001](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md) section 10.
- The adapters use Unicode 15.0.0 grapheme and width data (the reference profile). A separate, non-normative
  proposal would define "wide" as East Asian Width W/F only. These are two different things.
- Dated finding, 2026-10-10 UTC: the TypeScript adapter once accepted a request with invalid UTF-8 where protocol v1
  requires rejection; it was fixed and independently verified by the final retry.
- C: builds with `_GNU_SOURCE`; its locale-dependent test is skipped when `de_DE.UTF-8` is not installed.
  Windows/MSVC is untested.
- No browser renderer. At 0.x only the latest minor is supported and nothing is stable before 1.0. The package
  `VERSION` (0.3.1) is not the grammar version (`mdgl 0.1`).
- No media type is registered, and nothing here is endorsed by a standards body.

## 9. Checklists

**Implementer**
- [ ] Read SPEC.md, PROTOCOL.md and REFERENCE_PROFILE.md.
- [ ] Implement parse, check, evaluate, render with pure frames.
- [ ] Write an adapter; run all classes; read the verdict line.
- [ ] Do not copy another implementation where SPEC is silent; report the gap.
- [ ] State which suite revision and gaps you pass; claim nothing beyond the verdict.

**Embedder**
- [ ] Use a 0.3.1 package or a later validated release (see the table above).
- [ ] Check untrusted input first; honour the limits; never play rejected input.
- [ ] Honour both `Color` and `Background`.
- [ ] Use the fallback frame for redirected output and reduced motion, with no timer.
- [ ] Pin the exact version; anything may change between 0.x minors.

**Doc author**
- [ ] Put scenes in a fence labelled `mdgl`; unaware renderers show the text.
- [ ] Choose a meaningful `fallback` still frame.
- [ ] Run `mdgl check` before publishing; follow [MDGL.md](../MDGL.md); avoid reserved vocabulary.

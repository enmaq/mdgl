# MDGL observable conformance protocol, v1

Status: **Wire v1 accepted (field set unchanged); implementation evidence gates still open** (2026-10-10). Open gates:
(1) the runner received an independent bounded review and the five-adapter verification of the 86-fixture corpus passed (2026-10-10 UTC, accepted by the coordinator), which is bounded evidence, not certification; (2) the `obs_ref_*` reference-profile cases are non-normative
([`REFERENCE_PROFILE.md`](REFERENCE_PROFILE.md)); (3) all expectations are hand-derived from SPEC; five adapters (Go, Rust, C, TypeScript, Python) independently passed the 83-fixture corpus under this bounded protocol-v1 profile (final integration, 2026-10-10 UTC; the 3 later `obs_circle_*` fixtures were then matched by all five adapters in a targeted run, and the current 86-fixture corpus (64 normative + 22 non-normative) passed on all five adapters in an independent verification on 2026-10-10 UTC (accepted by the coordinator)), which is bounded evidence and not a universal SPEC certification. No full-conformance claim is made. This document defines how a language-neutral
runner observes an MDGL implementation. It clarifies the observable output of
[`SPEC.md`](../SPEC.md) and does not change normative semantics. Where SPEC is silent and only the Go
reference (`go/`) decides a behaviour, it is marked **implementation-defined / gap** (section 9), not
silently normative. Machine-readable shape: [`protocol.schema.json`](protocol.schema.json).

## 1. Transport

An **adapter** is an executable that reads newline-delimited JSON requests on stdin and writes
exactly one newline-terminated JSON response per request on stdout. stderr is for logs only.

- One request per line, UTF-8, terminated by `\n` (a preceding `\r` is JSON whitespace).
- Max request line: 2 097 152 bytes excluding the newline (256 KiB source can reach about 1.5 MiB escaped).
  A longer line gets `bad_request` (id `null`); the adapter discards through the next `\n` and continues.
- Requests are processed strictly sequentially; responses are in request order. No concurrency, no batching.
- A blank (or whitespace-only) line is a malformed request: `bad_request`, id `null`. The empty final segment after the
  last `\n` is NOT a request and gets no response.
- A final non-empty request line that is not newline-terminated at EOF is still a request: the adapter processes it,
  writes its newline-terminated response, then exits 0. On stdin EOF (after any such line) the adapter exits 0.
  After a response the adapter must flush stdout.
- Responses are single-line JSON (no embedded raw newlines), key order is irrelevant, non-ASCII may be raw or `\u`-escaped.
- No wall clock, no randomness, no environment dependence (`NO_COLOR` etc. are ignored). Every request is a pure
  function of its fields: the same request twice yields identical responses (seeking is pure; SPEC "Dropped frames
  and seeking cannot alter state"). No state is carried between requests.

## 2. Requests

```
{"v":1,"id":<string>,"op":"check"|"frame","source":<string>,"time_ns":<int>,"width":<int>,"height":<int>,"fallback":<bool>}
```

| field | check | frame | type / rule |
|---|---|---|---|
| `v` | required | required | integer, must be `1` |
| `id` | required | required | string, echoed verbatim; the runner uses unique ids |
| `op` | required | required | `"check"` or `"frame"` |
| `source` | required | required | the full `.mdgl` text (UTF-8; JSON escapes decode to it) |
| `time_ns` | ignored | required unless `fallback` is true | JSON number that is a mathematical integer in `0..2^53-1` (nanoseconds); `1.0` and `1e9` qualify (see below) |
| `width`, `height` | ignored | required | integers, `1..200` and `1..60` (SPEC stage limits) |
| `fallback` | ignored | optional, default false | boolean; true requests the fallback frame, `time_ns` is then ignored |

Unknown fields are **ignored** (forward compatibility). Fields marked "ignored" for an op are not validated.
Required fields of the wrong type or out of range are `bad_request`. For `time_ns` the JSON number must be a
mathematical integer in the finite range `0..2^53-1`; this INCLUDES the literal forms `1.0` and `1e9` (the integers 1
and 1 000 000 000). A nonzero fractional part (`1.5`), NaN/Infinity, a negative value or a value above `2^53-1` is
`bad_request`. Adapters must accept these integer-valued forms; languages that parse JSON numbers as floats must check
integrality and range exactly. The RUNNER always emits plain integers. Validation order: line size, JSON syntax (top level must be an object), `v`, `op`, other
fields; the first failure decides the code. `source` containing a lone surrogate escape is `bad_request`.

### 2.1 Decimal seconds to nanoseconds (runner side)

Adapters never parse decimals; the wire field is only the integer `time_ns`. The runner converts the decimal seconds
written in legacy `.expect` headers (`@seconds`), `.mdgl` times and `.obs.json` `frames[].time` strings.

**Acceptance rule (does not narrow SPEC).** The runner accepts every form SPEC accepts (SPEC.md:96-97 "finite decimal
literals, optionally signed (no exponent); times optionally end in `s`"; grammar SPEC.md:122-125):

```
seconds = [ "+" | "-" ] unsigned [ "s" ]
unsigned = digit { digit } [ "." { digit } ] | "." digit { digit }
```

The MDGL SOURCE grammar for times stays exactly as SPEC states (no exponent; `.mdgl` times take no sign, SPEC.md:122).
The runner does not expand it.

**Fixture-time rule (`.expect` headers and `.obs.json` `frames[].time` strings only).** The value is a finite
non-negative decimal or exponent form that Go's `ParseFloat` accepts, with `+` allowed: `1`, `1.0`, `0.50`, `.5`,
`+2`, `1e-3`. NaN/Inf, an `s` suffix in these fields, and anything else are a fixture error. NEGATIVE values are
rejected BEFORE rounding, so `-0.0000000001` is a fixture error even though it would round to 0; `-0` is rejected too.
Conversion uses exact decimal arithmetic (Python `decimal`, not floats), rounds to the nearest nanosecond, ties away
from zero, and the result is capped at `2^53-1` ns (above that is a fixture error). More than 9 fractional digits
(`0.1234567891`) are accepted. The sign, exponent and `s` forms of `.mdgl` source times follow SPEC only.

**Rounding rule.** SPEC.md:179 "Time is absolute seconds, nonnegative and finite, rounded to nanoseconds": the exact
decimal value is rounded to the nearest nanosecond (the 9th fractional digit), ties away from zero (half up for
nonnegative values), using exact decimal arithmetic. Observed Go behaviour (`model.Time`, go/model/model.go:89-94):
`math.Round(value*1e9)/1e9` on a float64, the same rule up to binary representation of exact ties. Positive durations
and periods must not round to zero (SPEC.md:180). Then `time_ns = rounded nanoseconds`, required `<= 2^53-1`
(about 9.007e6 s; G3).

Worked example: `"1.0"` -> 1 000 000 000; `".5"` -> 500 000 000; `"+0.50"` -> 500 000 000; `"1e-3"` -> 1 000 000;
`"1e0"` -> 1 000 000 000; `"-0"` and `"-0.0000000001"` -> fixture error; `"0.0000000015"` (1.5 ns) -> 2 ns; `"1.2345678904"` -> 1 234 567 890 (10th digit 4 rounds down); `"1.2345678905"` -> 1 234 567 891.

**Canonical short form is output only.** The runner EMITS decimals in its own JSON reports and examples in a canonical
short form (no sign, no `s`, no leading zeros, no trailing fractional zeros: `"0.5"`, `"1"`). That is not a restriction
on fixture input: the same fixture-time rule above applies to every legacy `.expect` and `.obs.json` time.
Adapters turn `time_ns` into their evaluator's time using exact integer arithmetic or `float64(time_ns)/1e9`.

## 3. Responses

Every response has `"v":1`, `"id"` (echo; `null` only if the id could not be read) and `"ok"`.

### 3.1 `check` success (`ok:true`)

`{"v":1,"id":"c1","ok":true,"diagnostics":[...]}`. Empty array means the source is valid per SPEC grammar plus checker.
Each diagnostic: `{"line":N,"col":N,"message":"..."}`, one-based, `col` counted in **UTF-8 bytes** (SPEC).
Comparison rule: conformance compares **line, col and exact message of the FIRST diagnostic** (this equals the legacy
`.err` text `line:col: message`). Additional diagnostics are **allowed** but not compared; at least one is required when
the source is invalid. A source that is valid must give an empty array. The Go reference reports exactly one.

### 3.2 `frame` success (`ok:true`)

`{"v":1,"id":..,"ok":true,"width":W,"height":H,"cells":[row,...],"done":bool}`.

- `W = min(request.width, scene width)`, `H = min(request.height, scene height)`; `cells` has H rows of W cells.
  The runner asks for 200x60 to learn the scene size, or the scene size itself. **PROTOCOL POLICY (not SPEC)**, see G2.
- A cell is `{"r":"<one Unicode scalar>","fg":"<color>","bg":"<color or empty>"}`. `r` is the single rune of the
  SPEC Cells model (never a multi-rune cluster; wide glyphs are `U+FFFD`, blank is `" "`). A verbose object per cell
  was chosen over packed strings so that colours, multi-byte runes and later fields stay unambiguous; the size cost
  (at most 12 000 cells) is irrelevant.
- `fg`: `normal` (initial/default, rendered white), a SPEC colour name (`black red green yellow blue magenta cyan white
  accent`), or a blended `#rrggbb` (lowercase hex) produced by partial opacity. Fully opaque paint keeps the
  actor's named colour (SPEC "Cells preserve named Color at full opacity"). `accent` is kept as written by the
  scene; it is equivalent to cyan but is **not** normalised in `fg` (G5).
- `bg`: `""` means default black (SPEC "empty means the defined default black"). In 0.1 actors have transparent
  backgrounds, so `bg` is always `""` in practice; the field is part of the protocol because SPEC says hosts honor it.
- `done`: the SPEC completion state ("Done") at `time_ns`, for `fallback:false`. With simple duration `P`
  (explicit period, else greatest action end, 0 if static) and repeat `R` (`infinite` = unbounded):
  `done = (P == 0) or (R finite and time >= P*R)`; infinite repeat is never done; static scenes are immediately done
  (SPEC "Static scenes are immediately done"). Comparison is at nanosecond resolution; the half-open boundary
  `time == P*R` is already done and shows the last cycle's end held. Before that, interior exact period boundaries
  belong to the next cycle's start.
- **Response branch bound to the request.** The success shape is determined by the request's `fallback` field: if the
  request had `fallback:true` the response MUST be the fallback shape (no `done`); otherwise it MUST contain boolean
  `done`. The runner treats a mismatch as a transport failure.
- `fallback:true`: the frame is the SPEC fallback sample (`start`, `end`, or `@t` on the simple timeline, no
  repeat; `end` is the exact end state even for infinite scenes). `done` is **omitted** (G1). A response to a `fallback:true` request has no `done` field; a response to a
  `fallback:false`/absent frame request always has one (schema: `frameOk` requires `done`, `frameFallbackOk` forbids it).

**Paired schema.** JSON Schema cannot see the request, so `protocol.schema.json` provides two named definitions and
the rule is: validate a frame success response against `#/$defs/frameFallbackOk` iff `request.fallback` is true, else
against `#/$defs/frameOk` (the top-level `response` union accepts either and so cannot catch a mismatch alone).

### 3.3 Failures (`ok:false`)

`{"v":1,"id":..,"ok":false,"error":{"code":..,"message":..}}`. Codes:

| code | transport error? | when |
|---|---|---|
| `bad_request` | yes | not JSON / not an object, line too long, blank line, missing or mistyped field, invalid `time_ns`, unknown `op`, width/height out of range |
| `unsupported_version` | yes | `v` is an integer other than 1 (missing or non-integer `v` is `bad_request`) |
| `invalid_source` | no (MDGL-level) | `op:"frame"` on a source that fails parse/check; `error.diagnostics` is a required non-empty array, same shape as 3.1 |
| `internal` | yes | adapter bug caught at runtime; the adapter should keep serving |

An invalid MDGL source is never a transport error for `check` (`ok:true` with diagnostics). Any `ok:false` other than
`invalid_source` is a transport failure for the runner and fails the run (exit 2).

## 4. Examples

All frame examples are **illustrative, hand-derived** from the SPEC sections named, before reading Go; section 8
records the Go cross-check. Scene `S` used below (one line per `\n`):

```
scene width=8 height=1 fallback=end
actor a = text("AB") at (0, 0)
@0: a.fade(in, dur=2)
```

Simple duration = 2 s. Layout `(0,0)` puts `A`,`B` in columns 0 and 1. Blank cells are `{" ", normal, ""}`.

**E1 check ok** (SPEC Grammar):
```json
{"v":1,"id":"e1","op":"check","source":"scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n"}
{"v":1,"id":"e1","ok":true,"diagnostics":[]}
```

**E2 check with diagnostic, multibyte column** (SPEC "one-based UTF-8 byte columns"). Line 2 is
`actor a = text("é") $`: the 16 bytes `actor a = text("`, then `é` (2 bytes), then `") ` give `$` byte offset 21, so
col 22 (a rune count would give 21). The message text is Go's (SPEC pins no wording for this error, G4):
```json
{"v":1,"id":"e2","op":"check","source":"scene width=8 height=1 fallback=end\nactor a = text(\"é\") $\n"}
{"v":1,"id":"e2","ok":true,"diagnostics":[{"line":2,"col":22,"message":"unexpected character \"$\""}]}
```

**E3 frame, static text with fg** (SPEC Cells: normal-coloured spaces, named colour kept at full opacity; static is done):
```json
{"v":1,"id":"e3","op":"frame","source":"scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0) color=red\n","time_ns":0,"width":8,"height":1}
{"v":1,"id":"e3","ok":true,"width":8,"height":1,"cells":[[{"r":"A","fg":"red","bg":""},{"r":"B","fg":"red","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""}]],"done":true}
```

**E4 frame mid-fade, done false** (SPEC Time: linear default, opacity 0.5 at t=1; RGB source-over of white over
black: 255*0.5 = 127.5, rounded half up to 128 = `80`; zero-opacity cells absent). `S` at 1 s, `done` false (1 < 2):
```json
{"v":1,"id":"e4","op":"frame","source":"scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n","time_ns":1000000000,"width":8,"height":1}
{"v":1,"id":"e4","ok":true,"width":8,"height":1,"cells":[[{"r":"A","fg":"#808080","bg":""},{"r":"B","fg":"#808080","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""}]],"done":false}
```

**E5 frame done true** (SPEC: at/after the finite total duration the end is held and Done is true). `S` at 2 s: the fade
is held at opacity 1, so full-opacity paint keeps the actor colour `normal`:
```json
{"v":1,"id":"e5","op":"frame","source":"scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n","time_ns":2000000000,"width":8,"height":1}
{"v":1,"id":"e5","ok":true,"width":8,"height":1,"cells":[[{"r":"A","fg":"normal","bg":""},{"r":"B","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""}]],"done":true}
```

**E6 frame fallback** (SPEC: `fallback=end` is the exact end state; `time_ns` ignored, `done` omitted). A move to column 2:
```json
{"v":1,"id":"e6","op":"frame","source":"scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.move(to=(2, 0), dur=1)\n","fallback":true,"width":8,"height":1}
{"v":1,"id":"e6","ok":true,"width":8,"height":1,"cells":[[{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":"A","fg":"normal","bg":""},{"r":"B","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""},{"r":" ","fg":"normal","bg":""}]]}
```

**E7 bad_request** (fractional time; the id is still echoed; `"time_ns":1.0` and `1e9` would be valid):
```json
{"v":1,"id":"e7","op":"frame","source":"scene width=8 height=1 fallback=end\n","time_ns":1.5,"width":8,"height":1}
{"v":1,"id":"e7","ok":false,"error":{"code":"bad_request","message":"time_ns must be an integer in 0..2^53-1"}}
```

**E8 unsupported_version**:
```json
{"v":2,"id":"e8","op":"check","source":""}
{"v":1,"id":"e8","ok":false,"error":{"code":"unsupported_version","message":"protocol version 2 is not supported"}}
```

**E9 invalid_source on frame** (SPEC Grammar: scene requires width, height, fallback; the Go corpus pins the
sibling `missing_fallback.err` text, here a missing scene: `1:1: missing scene`, G4):
```json
{"v":1,"id":"e9","op":"frame","source":"","time_ns":0,"width":8,"height":1}
{"v":1,"id":"e9","ok":false,"error":{"code":"invalid_source","message":"source has diagnostics","diagnostics":[{"line":1,"col":1,"message":"missing scene"}]}}
```

Messages of `error.message` for transport codes are free text and never compared.

## 5. Runner interface (v/mdgl/scripts/conformance-runner.py)

```
conformance-runner.py --adapter 'CMD ARGS' [--suite DIR] [--class diagnostic,static,timed,cube,repeat] [--json] [--timeout SECONDS] [--shutdown-timeout SECONDS]
```

- `--adapter` (required): command line split with shell-style quoting (no shell is invoked), started once, kept
  running for the whole run, cwd = the suite directory. `--suite` defaults to the `conformance/` dir next to the
  script's parent. `--class` filters by fixture class (comma list, default all). `--timeout` per request, default 10.
- The runner sends sequential requests, checks the response against `protocol.schema.json` rules (ids must match;
  a response violating the contract is a transport failure), then compares.
- Exit codes: `0` all selected fixtures pass; `1` at least one fixture fails (comparison failures, including
  unexpected `invalid_source`); `2` usage error, adapter cannot start/crashes/times out, unparseable or mismatched
  response, any `ok:false` other than an expected `invalid_source`, or a malformed fixture. Zero selected fixtures is exit 2.
- Transport failures (exit 2) also include: a response line not terminated by LF (EOF mid-line, including a final
  unterminated response); any output line beyond one response per request (including after the last response);
  an adapter that does not exit within `--shutdown-timeout` (default 5 s) after the runner closes its stdin at the
  end of the run (it is killed, then the run fails); and a non-zero adapter exit status after stdin EOF. The runner
  itself always sends LF-terminated requests; the final-unterminated-request rule applies to adapters.
- Report (text, stdout): one line per fixture `PASS|FAIL <class> <name>[: first difference]`, then
  `summary: N passed, M failed`, then separate normative / non-normative counts and a verdict line (below). With `--json`
  stdout is a single object
  `{"protocol":1,"adapter":"CMD","total":N,"passed":P,"failed":F,"counts":{"normative":{"passed":..,"failed":..},"nonnormative":{"passed":..,"failed":..}},"verdict":"..","results":[{"name":"fade","class":"timed","normative":true,"status":"pass|fail","detail":"..."}]}`;
  logs go to stderr.
- **No false certification.** Legacy fixtures are normative; an `.obs.json` is normative unless it says `"normative":false`
  (a derivation that `ASSUMES` something SPEC does not fix). Non-normative passes print as `assumption-based pass (not
  certification)`; a non-normative failure still fails the run (exit 1) and is counted under non-normative. The verdict
  is `ALL NORMATIVE FIXTURES PASSED` only if at least one normative fixture ran, no normative fixture failed AND every class that has normative fixtures in
  the suite ran at least one normative fixture (so `--class` subsets get `NOT CERTIFIED: normative classes not run: ..`);
  if no normative fixture ran at all (an all-non-normative suite or `--class` selecting only non-normative fixtures)
  the verdict is `NOT CERTIFIED: no normative fixtures ran`; a normative failure gives `NORMATIVE FIXTURES FAILED`. Classes without fixtures print `class C: no fixtures`.
- The runner emits `time_ns` as a plain JSON integer. A frame success response is validated against the REQUEST
  (section 3.2): fallback request means no `done`, any other frame request means boolean `done`; a mismatch is exit 2.

### 5.1 Fixture formats

1. **Legacy glyph-only**: `NAME.mdgl` + `NAME.err` or `NAME.expect` as in SPEC "Cells and conformance". `.err` is
   `line:col: message` of the first diagnostic; the runner issues `check` and compares the first diagnostic's line,
   col and message. `.expect` is `@seconds` lines each followed by `height` rows; the runner converts `seconds`
   (fixture-time rule, section 2.1), issues `frame` with width 200 and height 60 (the response size is the scene size), joins each row's
   `r` values and compares to the expected row padded with spaces to the scene width. fg/bg/done are not compared.
   Class is derived, first match wins: `.err` is `diagnostic`; source contains `cube(` is `cube`; scene has `repeat=`
   is `repeat`; no `@t:` action line is `static`; otherwise `timed`.
2. **Observable fixture** `NAME.obs.json` (new):
   ```json
   {"source_file":"NAME.mdgl","cols":8,"rows":1,"class":"timed","derivation":"SPEC Time: linear fade, opacity 0.5 at t=1",
    "frames":[{"time":"1","cells":[[{"r":"A","fg":"#808080","bg":""}]],"done":false}]}
   ```
   `cols`,`rows` are the requested size (the scene size); `class` is one of `static|timed|cube|repeat|diagnostic`;
   `derivation` is mandatory prose naming the SPEC rule (an expectation with no derivable rule is a gap, not a
   fixture). `frames[].time` is a decimal string accepted per the fixture-time rule of section 2.1 (new fixtures should use the canonical short form); `cells` must equal the response exactly (r, fg, bg for
   every cell), `done` exactly. Every non-fallback frame, including class `cube`, MUST carry an explicit boolean `done`;
   a fallback frame MUST NOT carry `done` (either violation is a malformed fixture, exit 2, naming fixture and frame
   index). Legacy `.err`/`.expect` fixtures make no done/fg/bg claim and are reported as glyph-only. A `diagnostic` obs fixture has `"diagnostic":{"line":N,"col":N,"message":".."}` and no
   `frames`. Cube obs fixtures compare `r` and `done` only (fg/bg omitted = not compared); the shipped cube fixtures contain glyphs only.

## 6. Classes

| class | meaning | compared |
|---|---|---|
| `diagnostic` | check errors | first diagnostic line, col, message |
| `static` | no actions, or time-independent output | cells (legacy: r only) |
| `timed` | actions/easing/seek/fallback | cells + done (legacy: r only) |
| `repeat` | `repeat=`/`period=` cycles | cells + done; boundary semantics |
| `cube` | wire cube raster (braille) | glyph `r` (+ `done`); the normative and fallback cube fixtures carry no colour or background claim (G7); the non-normative `obs_ref_cube_x_30_red` does, under the reference profile |

## 7. Rule coverage map

Status: **L** = covered by legacy fixture, **O** = planned obs fixture, **GAP** = no case, SPEC under-specified or no
derivation yet.

| SPEC rule | class | status |
|---|---|---|
| Grammar errors: unknown action/actor/key, duplicates, missing fallback, bad duration, parent cycle | diagnostic | L `action_typo actor_typo unknown_key duplicate_actor missing_fallback bad_duration parent_cycle` |
| Overlapping actions on same property error | diagnostic | L `overlap` |
| Repeat other than 1 needs explicit period | diagnostic | L `repeat_period` |
| Stage limit 200x60 | diagnostic | L `stage_limit`; other limits (64 actors, 1024 actions, 256 KiB, 16 KiB line, 1024 graphemes) O |
| Byte columns for multibyte lines | diagnostic | obs `obs_diag_multibyte_2 obs_diag_multibyte_3` (message ASSUMES G4); GAP for other messages (G4) |
| Reserved vocabulary rejected | diagnostic | O |
| Static text, anchors, percent, pivots, parent | static | L `static anchors percent pivot_center pivot_origin parent` |
| fade, freeze, adjacent, move, scale, color, type, wipe, blink, slide | timed | L `fade freeze adjacent move scale color type wipe blink slide`; obs `obs_fade_endpoints obs_fade_out obs_color_switch obs_blink obs_type obs_wipe_in obs_wipe_out obs_slide_in obs_slide_out` (blink/type/wipe carry ASSUMES A1-A3) |
| Opacity blending (`#rrggbb`), fg/bg fields | timed | obs `obs_fade_blend_white obs_fade_blend_red obs_static_color obs_static_default` (blend rows ASSUME G5); bg is `""` in every fixture; the six cube observables are glyph-only and give NO colour/background coverage |
| Easing curves (ease, ease-in, ease-out, ease-in-out, bounce) | timed | O (Bezier and bounce numbers derivable) |
| z paint order, declaration order | static | obs `obs_paint_order obs_paint_z` |
| Grapheme clusters, wide glyph U+FFFD | static | L `graphemes`; obs `obs_grapheme_combining obs_wide_glyph` (wide ASSUMES A4) |
| rect/circle braille raster | static | Normative coverage MISSING (G7); non-normative reference-profile cases only: `obs_ref_rect_2x1_red obs_ref_circle_r05_green` ([`REFERENCE_PROFILE.md`](REFERENCE_PROFILE.md), differs from SPEC in the rect/circle dot offset). Original refusal: a hand derivation was attempted and refused, because SPEC states neither the dot rectangle a `rect(w,h)` outline or a `circle(N)` ellipse covers nor the number of ellipse samples (only "sampled on that grid"); no doubtful fixture was added |
| Repeat cycles, boundary, finite hold | repeat | L `repeat`; obs `obs_repeat_boundary obs_repeat_period_freeze` (nanosecond-exact boundaries, `done` flags) |
| Infinite repeat never done | repeat | obs `obs_repeat_infinite` |
| `done` for static / finite scenes | static/timed | obs `obs_static_* obs_fade_endpoints obs_fade_out obs_color_switch obs_repeat_boundary` (E3, E4, E5 are examples only) |
| fallback start/end/@t | timed | obs `obs_fallback_start obs_fallback_end obs_fallback_at obs_fallback_infinite` (ASSUME G1: done omitted) |
| Seek purity | timed | obs `obs_seek_purity` (repeated and out-of-order times; the runner also compares repeated requests) |
| Viewport larger than stage | static | obs `obs_clamp` (ASSUMES G2, protocol policy) |
| Cube rotate x/y/z, near plane clipping | cube | L `cube_x_* cube_y_* cube_z_* cube_x cube_z cube_near` (glyph only) |
| Cube colours/backgrounds; rect/circle observables | cube/static | Normative coverage MISSING (G7); colour exists only in non-normative `obs_ref_cube_x_30_red` under the reference profile. Normative derivation: not derived (projection/near-plane arithmetic is not tractable by hand to dot level), none fabricated |
| Cube glyph reuse (independent input) | cube | obs `obs_shape_cube_x_30 obs_shape_cube_y_45 obs_shape_cube_z_45` (normative, r only, legacy `cube_x_30 cube_y_45 cube_z_45` @1 rows, done true); `obs_shape_cube_*_fb` (fallback=end, ASSUMES G1: done omitted, non-normative). Glyphs are copied from legacy, not re-derived; cube colours remain MISSING (G7) |
| rect/circle observable reuse | static | GAP: the legacy corpus has no `rect(` or `circle(` fixture to reuse, and SPEC leaves unspecified the dot rectangle of a `rect(w,h)` outline, the dot extent and sample count of a `circle(N)` ellipse; no normative fixture added, no normative claim made; non-normative reference-profile cases exist (see the rect/circle raster row) |

## 8. Cross-check against Go (read-only, after derivation)

Go sources read: `go/mdgl.go`, `go/eval/eval.go`, `go/render/cells/{cells,color}.go`, `go/parse/parse.go`.
E1, E3, E5, E6, E8 (transport only) agree. E2: lexer column is the byte offset + 1 on the whole line: agrees (22).
E4: `overCell` rounds each channel with `math.Round` (half away from zero): 127.5 gives 128, `#808080`: agrees, but
SPEC does not fix the rounding mode (G5). Done in `eval.Frame` is `!Active`, `Active = Period>0 && (Repeat==0 ||
Time(t) < Time(Period*Repeat))` (repeat 0 = infinite), identical to section 3.2. E9: Go's missing-scene text is
`1:1: missing scene` (parser): agrees. **No disagreement** between hand derivation and Go was found; the differences
below are places where SPEC is silent and Go decides.

## 9. Gaps to resolve in SPEC

| id | gap | v1 handling |
|---|---|---|
| G1 | `FallbackFrame` returns cells only; SPEC does not say what Done means for a fallback sample (SPEC.md:205-208 defines Done only for the playing timeline) | `done` omitted |
| G2 | Viewport smaller than stage: SPEC fixes no viewport semantics; Go clamps to `min(request, scene)` | **PROTOCOL POLICY (not SPEC)**: response `width/height = min(request, scene)`; fixtures use scene size |
| G3 | `model.Time` stops rounding when `|t| > 1e6` s; SPEC.md:179 says all times round to ns | fixtures keep `time_ns <= 1e15`; larger values implementation-defined |
| G4 | Diagnostic wording beyond the corpus (`.err` files) and diagnostic count; positions for global errors (1:1). SPEC fixes only the `line:column: message` shape, byte columns and did-you-mean (SPEC.md:239-243) | first diagnostic compared; new messages need a SPEC-derived or Go-pinned entry |
| G5 | Blend channel rounding mode (SPEC.md:194-200 gives the source-over formula, not rounding; Go: half away from zero), lowercase hex, `accent` kept in fg | Go behaviour recorded, not normative |
| G6 | `big` text advisory; reduced-motion / play behaviour not observable here | out of protocol scope |
| G7 | **Missing fixture coverage**, not a normative gap: SPEC.md:222-238 fixes braille 2x4 quantisation, dot coordinates, line stepping (ceil(max(abs dx, abs dy)) steps, nearest-dot rounding), the cube rotation/projection and clipping. (a) Normative gap: SPEC does not fix the rect/circle dot offset and extents (nor reconcile them with the cube's SPEC offset), so no normative rect/circle/cube-colour fixtures exist; normative cube coverage is glyph-only (`obs_shape_cube_*`). (b) Three non-normative reference-profile fixtures exist ([`REFERENCE_PROFILE.md`](REFERENCE_PROFILE.md)): `obs_ref_rect_2x1_red` (class `static`), `obs_ref_circle_r05_green` (class `static`) and `obs_ref_cube_x_30_red` (class `timed`, full cells, not the glyph-only `cube` class) | (a) open; (b) `normative:false` coverage only |
| G10 | Circle size bound: SPEC.md said only `geometry 0<size<=200` without saying whether circle(N) is bounded by radius or diameter | **Resolved by SPEC clarification (radius <= 100, diameter <= 200)**, a compatibility interpretation preserving Go, Rust, C and Python (not an IETF or standards-body decision). The TypeScript adapter was corrected by its owner. All five adapters now emit `circle radius must be positive and <=100`; this agreement is an observation, not a SPEC rule (SPEC pins no wording or position, G4), so the reject fixtures stay `normative:false` (G4). The bound is confirmed by the five adapters on the three circle fixtures (targeted run); independent verification of the full 86-fixture corpus passed on all five adapters (2026-10-10 UTC, accepted by the coordinator); the accept fixture `obs_circle_r100_accept` is normative |
| G8 | Source over 256 KiB or invalid UTF-8: SPEC.md:247 says rejected, no position given | `check` returns a diagnostic (Go: 1:1) |

Removed: former G9 (unpainted cells have `fg` `normal`, empty `bg` means black) is specified, no gap: SPEC.md:195-196
"normal foreground is white and default background is black", SPEC.md:200 "`Background` string (empty means the
defined default black)", SPEC.md:222-223 "initialized with normal-colored spaces". In 0.1 actors have transparent
backgrounds (SPEC.md:198), so `bg` is `""` in practice.

## Appendix A. Observable fixture inventory (runner side, informative)

Written by hand from SPEC.md before any implementation was consulted. The expectations are hand-derived, not generated from any implementation; five adapters passed the 83-fixture corpus in the final integration, before the 3 `obs_circle_*` fixtures were added (bounded evidence, not a universal SPEC certification; the current 86-fixture corpus later passed on all five adapters in an independent verification, 2026-10-10 UTC, accepted by the coordinator). `normative: false` in the `.obs.json` marks a fixture
whose derivation `ASSUMES` something SPEC does not fix. Sources are at most 6 columns and 1 row (diagnostic ones 8x1), except the six cube fixtures (14x10). Columns: class, SPEC rule, derivation basis.

| fixture | class | SPEC rule | basis |
|---|---|---|---|
| `obs_static_color` | static | named Color kept at full opacity; static is done | normative |
| `obs_static_default` | static | default fg `normal`, bg `""`, layout column | normative |
| `obs_paint_order` | static | declaration order, later on top | normative |
| `obs_paint_z` | static | higher z paints on top | normative |
| `obs_grapheme_combining` | static | one grapheme per cell, marks dropped | normative |
| `obs_wide_glyph` | static | wide glyph is U+FFFD | ASSUMES A4 |
| `obs_clamp` | static | response is min(request, scene) | ASSUMES G2 |
| `obs_fade_endpoints` | timed | fade-in starts at 0, freezes at 1, done at P | normative |
| `obs_fade_out` | timed | fade-out starts at 1 (named colour kept), ends transparent | normative |
| `obs_fade_blend_white` | timed | RGB source-over, 0.25/0.5/0.75 | ASSUMES G5 (rounding, hex case) |
| `obs_fade_blend_red` | timed | primaries full-intensity, blend | ASSUMES G5, red = (255,0,0) |
| `obs_color_switch` | timed | colour switches at progress >= 0.5 | normative |
| `obs_blink` | timed | alternates each half-cycle, ends visible | ASSUMES A3 |
| `obs_type` | timed | floor(elapsed/per_char) clusters | ASSUMES A1 (done) |
| `obs_wipe_in`, `obs_wipe_out` | timed | wipe starts/ends unrevealed | ASSUMES A2 |
| `obs_slide_in`, `obs_slide_out` | timed | slide from/to the outside edge | normative |
| `obs_seek_purity` | timed | seeking is pure; out of order and repeated times | normative |
| `obs_fallback_end/_start/_at/_infinite` | timed | fallback samples the simple timeline; done omitted | ASSUMES G1 |
| `obs_repeat_boundary` | repeat | boundary = next cycle start; P*R is done; ns-exact | normative |
| `obs_repeat_infinite` | repeat | infinite never done | normative |
| `obs_repeat_period_freeze` | repeat | explicit period longer than actions; freeze until reset | normative |
| `obs_diag_multibyte_2`, `_3` | diagnostic | UTF-8 byte columns | ASSUMES G4 (message text) |
| `obs_shape_cube_x_30`, `_y_45`, `_z_45` | cube | glyph `r` + `done` copied from legacy `cube_*` @1 rows; no colour/background claim | normative (rasterisation not re-derived, G7) |
| `obs_shape_cube_x_30_fb`, `_y_45_fb`, `_z_45_fb` | cube | fallback frame, glyph `r` only, done omitted; no colour/background claim | ASSUMES G1 |
| `obs_circle_r100_accept` | static | circle radius 100 (diameter 200) is within the bound (SPEC.md Limits and API, G10); actor placed off-stage at (5000,5000), so clipping to stage bounds leaves only unpainted default cells (no raster claim, G7) | normative |
| `obs_circle_r101_reject`, `obs_circle_r0_reject` | diagnostic | circle radius 101 above the bound / radius 0 not positive is rejected; position actor start 2:1 and Go wording | `normative:false` (G4: adapters differ in wording, see G10) |
| `obs_ref_rect_2x1_red`, `obs_ref_circle_r05_green` | static | rect/circle raster under the reference profile ([`REFERENCE_PROFILE.md`](REFERENCE_PROFILE.md)) | `normative:false` (reference profile, not SPEC) |
| `obs_ref_cube_x_30_red` | cube | coloured wire cube under the reference profile | `normative:false` (reference profile, not SPEC) |

Local assumptions not in section 9 (proposed, not frozen): **A1** the end of a `type` action is begin plus
graphemes times `per_char` (SPEC defines `Done` through "greatest action end" but not this end); **A2** wipe reveals
left to right by whole clusters and wipe-out starts fully revealed; **A3** blink makes `2*times` half-cycles over
`dur`; **A4** "wide" means East Asian Wide/Fullwidth. Legacy fixtures pin A1-A3 for Go.

Totals (the runner computes these from the files; this text is informative): 40 observable fixtures = 18 normative (14 originals + 3 cube + 1 circle accept) + 22 non-normative (`normative:false`: 14 assumption-based originals, 3 fallback cube, 3 reference-profile `obs_ref_*` cases). The assumption-based ones are `obs_clamp`
(G2), `obs_diag_multibyte_2/_3` (G4), `obs_fade_blend_white/_red` (G5), `obs_blink` (A3), `obs_type` (A1),
`obs_wipe_in/_out` (A2), `obs_wide_glyph` (A4), `obs_fallback_start/_end/_at/_infinite` (G1), `obs_shape_cube_*_fb` (G1), `obs_circle_r101_reject/_r0_reject` (G4/G10). No normative rect or circle
observable fixture exists and no normative cube fixture has colour or background expectations (missing coverage, section 7); rect, circle and cube colour are covered only by the three non-normative `obs_ref_*` cases under the reference profile. Together with the 46 legacy fixtures (all normative, glyph-only) the suite
has 86 fixtures: 64 normative, 22 non-normative (loader tally from the files). All expectations are hand-derived from SPEC (not generated from any implementation); five adapters passed the earlier 83-fixture corpus in the final integration under the bounded protocol-v1 profile; the 3 `obs_circle_*` fixtures were matched by the five adapters in a targeted run, and the current 86-fixture corpus (64 normative + 22 non-normative) passed on all five adapters in an independent verification on 2026-10-10 UTC (accepted by the coordinator) (bounded evidence, not a universal SPEC certification). There is no full-conformance claim.

Runner report extensions (additive, not part of the frozen report shape): text output also prints fixtures per class,
`class C: no fixtures` for selected classes with no fixture, the normative / non-normative counts and the verdict line;
`--json` adds `counts`, `verdict`, `classes` (counts), `no_fixtures` and `normative` on every result.

Layout: observable fixtures (`conformance/observable/*.obs.json` plus the sibling `.mdgl` named by `source_file`) live in a
subdirectory because the Go legacy test `go/conformance_test.go` globs `conformance/*.mdgl` at the top level and requires
`.err` or `.expect` for every match; the glob is not recursive. The runner also accepts `*.obs.json` in the suite root.

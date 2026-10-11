# mdgl (Python - 0.3.0 release candidate in source: parser, checker, evaluator, renderer, adapter, player)

0.3.0 release candidate in source, not yet published. The **published 0.2.0 package is the limited header/resource seed check** (immutable); the
capabilities below exist only in source. Conformance adapter: `python3 -m mdgl.adapter`
(NDJSON protocol v1). In the final integration (2026-10-10 UTC) it passed, together with the four other adapters, the 83-fixture corpus (63 normative + 20 non-normative) under the bounded protocol-v1 profile; that is bounded evidence, not a universal SPEC certification. Rect/circle/cube
colour exist only as non-normative reference-profile fixtures; full SPEC conformance is NOT claimed. The Go module is the reference.

## Implemented

- `mdgl.compile(source)` -> `Animation` (`width/height/fps/period/fallback`); `.frame(seconds, cols=None, rows=None)`
  -> `Frame(cells, done)` with `Cell(rune, color, background)` and `.lines()`; `.frame_ns(ns)`, `.fallback_frame()`,
  `.active(seconds)`. Pure and seekable. All nine actions, easing (CSS cubic-bezier, bounce), parent/z order,
  period/repeat/Done, fallback, braille rect/circle/wire-cube, text, RGB source-over fg blending.

- `mdgl.parse(source)` -> source-located `Scene` (statements, quoted-string Go escapes, UTF-8 byte
  columns, finite non-exponent decimals, `scene` < `actor` < action order, reserved vocabulary).
- `mdgl.check_scene(scene)` / `mdgl.load(source)` -> checked scene: scene keys and limits, period,
  repeat, fps, fallback, actor shapes/arguments/attributes, duplicates, unknown names with
  did-you-mean (edit distance <= 2), forward parents and parent cycles, action verbs and arguments,
  overlapping properties, nanosecond rounding, duration/period limits, 1024-grapheme text.
- `mdgl.check(source)` keeps its shape: `[]` or `[{"line","col","message"}]` with the first
  diagnostic (`MdglError` carries `.line`, `.col`, `.message` from `parse`/`load`).

Graphemes: full extended UAX #29 segmentation (GB1-GB13) and cell width from generated **Unicode 15.0.0** tables
(`mdgl/_unicode15.py`, derived from rivo/uniseg v0.4.7, MIT, `LICENSE-UNISEG.txt`) - the compatibility profile of the
Go reference, not a normative MDGL Unicode version. No GB9c (Unicode 15.1 conjuncts). No runtime dependency.

```python
import mdgl
scene = mdgl.load("scene width=8 height=1 fallback=end\nactor a = circle(1) at (0, 0)\n")
assert mdgl.check("scene width=8 height=1\n")[0]["message"] == "missing scene attribute fallback"
```

## Install and versions

`pip install mdgl` gives the published 0.2.0 seed check only, not the code in this tree. To try the 0.3.0 release candidate from source, install it editable from a repository checkout (`v/mdgl/python`), ideally in a fresh virtual environment:

```
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
python examples/render.py                      # shared examples/text.mdgl at t=0
python examples/render.py --time 3.5           # seek to 3.5 s
python examples/render.py --fallback           # the scene's fallback frame
python examples/render.py my_scene.mdgl        # your own file; errors print FILE:LINE:COL: message, exit 1
```

`examples/render.py` is a source example (it is in the sdist, not installed by the wheel); its default scene is
`../examples/text.mdgl` in a checkout, so outside one pass a file path. The frame goes to stdout and a one-line summary
to stderr. API in one place:

```python
import mdgl
scene = mdgl.compile(open("scene.mdgl", encoding="utf-8").read())  # raises mdgl.MdglError(line, col, message)
print("\n".join(scene.frame(1.5).lines()))   # or scene.frame_ns(ns), scene.fallback_frame()
```

## Terminal player and CLI

Installing this tree (`pip install .` or `pip install -e .`) puts an `mdgl` command on your PATH (also `python -m mdgl`):

```
mdgl play FILE            # animate in the terminal; Ctrl+C stops and restores the cursor
mdgl check FILE           # validate, prints OK MDGL 0.1
mdgl frames FILE --at 0,1.5s   # print plain frames at the given times
mdgl --help
```

`play` follows the SPEC: frame time is the absolute monotonic elapsed time (dropped frames never change state), it
runs at the scene's `fps`, redraws only changed cells (foreground and background) inside DEC synchronized output
(mode 2026), stops when a finite scene is done (a `repeat=infinite` scene runs until Ctrl+C), and always hides then
restores the cursor and resets colors, on finish, Ctrl+C or a write error. If stdout is not a terminal, or `NO_COLOR` or
`MDGL_REDUCED_MOTION` is non-empty, it prints the fallback frame once as plain text, with no timer and no escape
sequences. Cell content is never sent to the terminal as a control character.

Exit codes: `0` ok, `1` invalid scene or output error, `2` usage or unreadable file, `130` interrupted (Ctrl+C).

From Python: `mdgl.player.play(mdgl.compile(src), sys.stdout.write, sys.stdout.flush)` (clock and sleep are injectable).

Versions track the shared MDGL release (`VERSION`). See [RELEASING.md](../RELEASING.md).

## Developer: conformance run

Run from the repository's `v/mdgl` directory; the detailed report and logs stay out of the source tree
(`conformance-report/` is git-ignored if you write it there):

```
mkdir -p -m 700 /tmp/mdgl-python-private
python3 scripts/conformance-runner.py --adapter "env PYTHONPATH=$PWD/python python3 -m mdgl.adapter" \
  --json > /tmp/mdgl-python-private/runner-report.json 2> /tmp/mdgl-python-private/runner.stderr.log
```

Reports contain absolute paths; do not commit or publish them. The current shared corpus has 86 fixtures (64 normative, 22 profile or assumption-based non-normative).

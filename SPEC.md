# MDGL 0.1

> **Licence.** The text of this specification is licensed under
> [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The conformance suite in
> `conformance/` and all code are available under either MIT or Apache-2.0, at your option
> (`LICENSE-MIT`, `LICENSE-APACHE`). Copyright (c) 2026 Enmaq and MDGL contributors.

Status: reference subset, 2026-10-08. A standalone, deterministic MarkdownGL
module; no host application dependency. Cube wireframes and rotate are included;
cells references, solid faces, def, seq, images and paths are reserved.

## Graphics pipeline and reserved vocabulary

0.1 implements 2-D text/rect/circle and a wire cube with an orthographic default
camera. Actor transforms use position, rotation (cube only), and scale, followed
by orthographic projection into cells. Both paths compose model → view → projection
like WebGL. Later versions will use a software depth buffer on terminal dots and a
WebGL browser renderer with Canvas 2D fallback. The 0.1 compositor uses declaration
order after sorting optional integer actor `z` (higher paints on top). Cube uses
a fixed internal perspective at distance 3×size in its own viewport; scene camera,
depth buffers, lighting, materials and scene imports are not enabled.

### GL conventions

The world is right-handed: +X right, +Y up, +Z toward the viewer; a camera
looks along −Z. Layout coordinates remain cell columns/rows, increasing down,
as sugar over world coordinates `(column, -2*row, 0)`. One cell is one world
unit wide and two high (physical aspect 2:1). Viewport mapping flips Y exactly
once: `column=(ndcX+1)*width/2`, `row=(1-ndcY)*height/2`.

Matrices are column-major, act on column vectors, and multiply right to left.
For an actor at layout `(x,y)` with local anchor `(ax,ay)`, its local matrix is
`T(x+ax,-2*(y+ay),0) * R * S * T(-ax,2*ay,0)`. The default anchor is the
centre `(width/2,height/2)`; `anchor=(0,0)` selects the top-left. The anchor is
the actor's local origin for scale/rotation, not an implicit top-left pivot.
World matrix is `parentWorld * local`; roots use `local`. All transforms and
opacity are inherited; local color remains independent. Glyph origins inherit
the transform, but individual terminal glyphs remain upright single-cell runes.

Euler rotation is intrinsic XYZ, exactly the default three.js Euler order:
`R=Rx*Ry*Rz`, **not** `Rz*Ry*Rx`. With `cx=cos(x)`, `sx=sin(x)` etc., rows are:

```text
 cy*cz             -cy*sz             sy       0
 cx*sz+sx*sy*cz     cx*cz-sx*sy*sz    -sx*cy    0
 sx*sz-cx*sy*cz     sx*cz+cx*sy*sz     cx*cy    0
 0                  0                 0        1
```

Angles in the DSL are degrees (optional `deg`); `rad` suffix is also accepted
and converted to degrees before interpolation. No unit means degrees.

Orthographic projection is `glOrtho(left,right,bottom,top,near,far)`, with diagonal
`(2/(r-l),2/(t-b),-2/(f-n),1)` and translation
`(-(r+l)/(r-l),-(t+b)/(t-b),-(f+n)/(f-n))`. The 2-D stage uses
`(l,r,b,t,n,f)=(0,width,-2*height,0,-1000,1000)`.
Each cube is a true equal-sided world mesh in its own fixed viewport. Camera is
at its transformed centre plus `(0,0,3*size)`, looking down −Z, vertical FOV 50°,
aspect `width/(2*height)`, near 0.1, far 1000. Perspective rows are:

```text
 q/aspect  0  0              0
 0         q  0              0
 0         0  -(f+n)/(f-n)   -2*f*n/(f-n)
 0         0  -1             0
 q = 1/tan(verticalFov/2)
```

Clip coordinates are `P*V*world*vertex`. Wire edges are clipped against all six
homogeneous GL planes `-w<=x,y,z<=w` **before** division by w and viewport mapping;
no edge behind the near plane can generate unbounded coordinates. This is the
OpenGL/WebGL NDC depth range [−1,+1], not WebGPU's [0,+1]. No depth buffer exists
in 0.1; optional integer `z` is paint order, never geometric depth.

Reference formulas: [three.js Matrix4](https://github.com/mrdoob/three.js/blob/master/src/math/Matrix4.js)
(`makeRotationFromEuler` XYZ, `makePerspective`, `makeOrthographic`) and
[gl-matrix mat4](https://github.com/toji/gl-matrix/blob/master/src/mat4.js)
(`perspectiveNO`, `orthoNO`). No runtime dependency is introduced.

The following three.js vocabulary is RESERVED, not accepted 0.1 syntax:
`camera perspective(fov=60) position=(0,0,10) look_at=(0,0,0)`;
`camera orthographic`; `light ambient(intensity=0.3)`;
`light directional(intensity=0.7) position=(1,1,1)`;
`mesh(geometry=box|sphere|plane, material=basic|lambert, color=red)`;
`position=(x,y,z) rotation=(x,y,z) scale=1`;
`actor imported = threejs("scene.json") at (0,0)`.
The reserved import is three.js JSON Object format (ObjectLoader), eventually
rendered through the same software pipeline; it performs no file/network loading
in 0.1. Shader source is outside this declarative DSL.

## Grammar

UTF-8 input, one statement per line; blank lines and lines beginning `#` are
ignored. No inline comments. Whitespace separates tokens, except inside strings.
Identifiers are ASCII letters/underscore followed by letters/digits/underscore.
Strings use Go quoted-string escapes. Numbers are finite decimal literals,
optionally signed (no exponent); times optionally end in `s`. Version is optional.
Every scene requires width, height and fallback. Attribute order is free.

```ebnf
document = [ "mdgl", "0.1", newline ], scene, newline,
           { actor, newline | action, newline | blank | comment } ;
scene = "scene", { key, "=", value } ;
actor = "actor", identifier, "=", shape, "at", point,
        { ("color", "=", color) | ("parent", "=", identifier) | ("z", "=", number)
        | ("anchor", "=", point) } ;
shape = "text", "(", string, [ ",", "big" ], ")"
      | "rect", "(", number, ",", number,
        { ",", ("border=", ("square" | "round") | "title=", string) }, ")"
      | "circle", "(", number, ")"
      | "cube", "(", "size=", number, [ ",style=wire" ], ")" ;
action = "@", time, ":", identifier, ".", verb, "(", arguments, ")" ;
verb = "fade" | "move" | "scale" | "color" | "type" | "blink"
     | "wipe" | "slide" | "rotate" ;
arguments = argument, { ",", argument } ;
argument = "in" | "out" | key, "=", value ;
angle = number, [ "deg" | "rad" ] ;
point = "(", coordinate, ",", coordinate, ")" ;
coordinate = number, [ "%" ] | anchor, [ ("+" | "-"), unsigned ] ;
anchor = "center" | "left" | "right" | "top" | "bottom" ;
value = number | time | keyword | string | point | "@", time ;
time = unsigned, [ "s" ] ;
key = identifier ;
number = [ "+" | "-" ], unsigned ;
unsigned = digit, { digit }, [ ".", { digit } ] | ".", digit, { digit } ;
identifier = letter, { letter | digit } ;
keyword = identifier, { "-", identifier } ;
letter = "A" ... "Z" | "a" ... "z" | "_" ;
digit = "0" ... "9" ;
string = '"', { printable | escape }, '"' ;
escape = "\\", GoQuotedStringEscape ;
newline = "\n" | "\r\n" ;
blank = { " " | "\t" }, newline ;
comment = { " " | "\t" }, "#", { nonNewline }, newline ;
```

`printable` excludes unescaped quote, backslash and newline; `GoQuotedStringEscape`
uses the Go interpreted string escape set. A final newline is optional. Actor
shape named arguments may appear in any order, but required positional arguments
must precede them; `cube` requires `size`. Duplicate arguments are always errors.

Scene keys: `width`, `height` (integer cells), `period` (seconds), `repeat`
(positive integer, default 1, or `infinite`), `fallback` (`start`, `end`, `@t`),
`fps` (integer, default 30). Repeat other than 1 requires an explicit period.
No unknown or duplicate key is permitted. Scene must precede actors/actions;
actors must precede actions. Forward parent references are allowed, cycles are not.

Action arguments (all but type require positive `dur`; `ease` is optional):

| Verb | Arguments | Property |
|---|---|---|
| fade | in/out, dur, ease | opacity |
| move | to=(x,y), dur, ease | position |
| scale | to=positive number, dur, ease | scale |
| color | to=color, dur, ease | color |
| type | per_char=positive seconds | reveal |
| blink | times=positive integer, dur | opacity |
| wipe | in/out, dur, ease | reveal |
| slide | in/out, to=left/right/top/bottom, dur, ease | position |
| rotate | one or more of x/y/z=degrees, dur, ease | rotation |

For rotate x/y/z, `angle` replaces the generic numeric value; suffixes are
part of the same token, e.g. `x=90deg` or `x=1.5707963267948966rad`.

Type is text-only; rotate is cube-only. Text `big` is accepted as an advisory
style, rendered at normal terminal size. Rect title is clipped to its top edge;
round borders use braille just as square borders do in the cells renderer.
Colors: normal, black, red, green, yellow, blue, magenta, cyan, white, accent.
Accent maps to cyan. Ease names: linear, ease, ease-in, ease-out, ease-in-out, bounce.
Linear is default. CSS cubic-bezier controls are ease=(.25,.1,.25,1),
ease-in=(.42,0,1,1), ease-out=(0,0,.58,1), ease-in-out=(.42,0,.58,1).
Solve the monotone Bezier X numerically for time, then sample Y; time is not
the Bezier parameter. See [CSS Easing](https://www.w3.org/TR/css-easing-1/).
Bounce uses the standard four
piece ease-out-bounce polynomial (7.5625, 2.75).

## Time and geometry

Time is absolute seconds, nonnegative and finite, rounded to nanoseconds.
Positive durations/periods must not round to zero. Simple duration is explicit
period or the greatest action end (zero for a static scene). Each action freezes
its final value, inspired by [SMIL fill=freeze](https://www.w3.org/TR/SMIL3/smil-timing.html#Timing-FillAttribute).
Intervals are half-open [begin,end); adjacent actions are valid. Overlapping
intervals on the same actor/property are a check error at the later source action;
there is no silent later-@t-wins merge. Different properties may run concurrently.
Actions are evaluated sorted by begin time; source order breaks equal-time ties.
The starting value of a move/scale/color/rotate is the preceding frozen value.
Rotate targets are absolute degrees in intrinsic XYZ order as defined above.

Fade-in starts at zero opacity even before its begin; fade-out starts at one.
Type/wipe-in similarly start unrevealed; text typing reveals floor(elapsed /
per_char) extended grapheme clusters, then freezes the complete text. Blink starts
visible, alternates each half-cycle, and ends visible. Wipe-out ends unrevealed.
Opacity uses RGB source-over, `out=source*alpha+destination*(1-alpha)`, not a
visibility threshold. Zero opacity is transparent. Named RGB primaries are
full-intensity; normal foreground is white and default background is black.
Cell glyph coverage uses the top nonblank glyph with its blended foreground;
background remains the destination background (actor backgrounds are transparent).
Cells preserve named `Color` at full opacity; blends use `#rrggbb`, with additive
`Background` string (empty means the defined default black). Hosts must honor both fields.
Color actions still switch at eased progress >= 0.5.

Each repeat resets all actor properties. Interior exact period boundaries are the
start of the next cycle; at/after the finite total duration the last cycle's end
is held and Done is true. Static scenes are immediately done. Infinite repeat
never finishes. Fallback=start/end/@t samples the simple timeline, without repeat.
Fallback @t must be within the simple duration. End means the exact end state,
including for infinite scenes. Dropped frames and seeking cannot alter state.

Actor layout position addresses its top-left bounding box (the transform pivot
is the local anchor, default centre); circle(N) has diameter 2N, cube(size=N)
has an N by N viewport. Coordinates are cells, percentages of remaining space
(stage minus unscaled actor bounds), with left/top=0, right/bottom=remaining space,
center=remaining space/2. Axis-inappropriate anchors are errors. Children use their
parent's unscaled bounding box for anchors; their coordinates are parent-local.
Parent full model transform, opacity and reveal are inherited; color is local.
Scale/rotation use the local anchor. Slide out targets the outside edge
(-actor size or stage extent), slide in starts there and ends at its current origin.

## Cells and conformance

Cells are a rectangular grid of rune plus named foreground color, initialized
with normal-colored spaces. One extended grapheme consumes one terminal cell:
the first non-mark rune is emitted; combining suffixes are omitted. Wide glyphs
are represented as U+FFFD; tabs, newlines and control characters in text/title
are rejected. Actors paint in declaration order, later nonblank pixels on top.
Coordinates round to nearest dot; text origins round to nearest cell. Wire endpoints
are quantized to 1e-9 dot before raster stepping, stabilizing exact integer step counts.
Shapes use braille 2×4 dots per cell (Unicode U+2800 bit layout). Rect outlines
and circle ellipses are sampled on that grid. Cube: eight corners, x/y/z rotation,
fixed GL perspective described above, twelve wire edges. Empty dot masks become spaces.
Cube local vertices are `(size/2±size/2, -height±size/2, ±size/2)` in physical
world units, transformed by its full scene graph model matrix.
Dot coordinates are `2*cellX-0.5`, `4*cellY-0.5`; this leaves room for rotation
inside the actor viewport. Lines sample both endpoints and evenly spaced points,
with ceil(max(abs(dx),abs(dy))) steps, rounding each dot to nearest integer.
Clipping is to stage bounds, with no terminal control sequences in cell content.

Conformance files pair NAME.mdgl with NAME.expect, or NAME.err. Expect files
contain `@seconds` followed by exactly height rows of width cells. Trailing spaces
may be omitted and are restored by the runner. Err is the exact first diagnostic,
`line:column: message`, one-based UTF-8 byte columns. Unknown names include a
did-you-mean suggestion when edit distance <=2; ties choose lexical order.

## Limits and API

Maximum input 256 KiB; line 16 KiB; stage 200×60; 64 actors; 1024 actions;
text/title 1024 grapheme clusters; period and each action end <=60 seconds;
fps 1..30; repeat 1..1000 or infinite; scale 0<value<=16; geometry 0<size<=200;
coordinates/rotation bounded to ±10000. Values must be finite. Rejected input
never plays. Parser creates source-located model; checker validates references,
arguments and conflicts; evaluator is pure and requires a checked scene. Renderer
returns cells without I/O. CLI `check FILE`, `frames FILE --at t1,t2`, `play FILE`.
Frames prints the conformance format. Play uses absolute elapsed time, dirty cells,
DEC synchronized-output mode 2026, and stops its timer on finite completion or
interrupt. Redirected output and reduced motion (`NO_COLOR` or `MDGL_REDUCED_MOTION`)
use the fallback frame with no timer. No background scheduler exists.

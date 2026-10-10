# MDGL reference compatibility profile (rect / circle / coloured cube)

Status: **reference compatibility profile, NON-NORMATIVE, not full conformance.** It records the rect/circle
rasterisation used by an independent reference journal so that the `obs_ref_*` fixtures have a written derivation.
SPEC.md stays the only normative text; where SPEC is silent or the profile differs, see the mismatch table.
Passing these fixtures proves compatibility with the profile only. The three `obs_ref_*` fixtures pass on all five adapters in the final integration (2026-10-10 UTC, bounded evidence); the derivations below were written by hand before any implementation was consulted.

## 1. Profile semantics

For an actor spanning W x H cells (rect(W,H) cells; circle(N) has diameter 2N, SPEC.md:211, so W=H=2N):

- Local dot box: x in [0, max(0, 2W-1)], y in [0, max(0, 4H-1)] (integer dots, 2 columns x 4 rows per cell).
- **rect**: its four edges: rows y=0 and y=4H-1, columns x=0 and x=2W-1; corner dots included (outline).
- **circle**: a closed polyline of 720 chords inscribed in an ellipse centred in the box,
  centre (cx,cy) = ((2W-1)/2, (4H-1)/2), radii (rx,ry) = (cx, cy) (half the box extents). Vertices
  `(cx + rx*cos(a), cy + ry*sin(a))`, a = k*2*pi/720, k = 0..720, starting at the rightmost point.
- rect and circle use **no 0.5 dot offset**; the actor's cell origin maps to dot (2*cellX, 4*cellY) directly.
  The cube keeps the SPEC offset (`2*cellX-0.5`, `4*cellY-0.5`, SPEC.md:234); the profile therefore differs from SPEC for rect/circle.
- Lines (chords, edges): endpoints are quantised to 1e-9 dot (SPEC.md:227-228), then clipped to the stage;
  steps = ceil(max(|dx|,|dy|)), minimum 1, capped at 800; both endpoints and evenly spaced points are sampled and
  each dot is rounded to the nearest integer (SPEC.md:235-236, 227).
- Painted cells keep the actor's named colour at full opacity (SPEC.md:199); unpainted cells are `normal` spaces
  with bg `""` (PROTOCOL 3.2). Static scenes are immediately done (SPEC.md:205).

## 2. Braille layout

Dot (col,row) within a cell sets bit: (0,0)=0x01, (0,1)=0x02, (0,2)=0x04, (0,3)=0x40,
(1,0)=0x08, (1,1)=0x10, (1,2)=0x20, (1,3)=0x80. Glyph = U+2800 + mask. An empty mask becomes a space
(SPEC.md:231 "Empty dot masks become spaces"; layout SPEC.md:229 "Unicode U+2800 bit layout").

## 3. Worked derivations

**obs_ref_rect_2x1_red** (4x2 stage, rect(2,1) at (1,0), red). W=2,H=1: box [0,3]x[0,3]. Outline dots:
y=0 and y=3 for x=0..3; x=0 and x=3 for y=0..3.
- Cell (1,0), local x=0,1: col 0 is the left edge (rows 0,1,2,3) = 0x01+0x02+0x04+0x40 = 0x47; col 1 has only
  top and bottom (rows 0,3) = 0x08+0x80 = 0x88. Mask 0xCF = U+28CF.
- Cell (2,0), local x=2,3: col 0 (x=2) rows 0,3 = 0x01+0x40 = 0x41; col 1 (x=3) is the right edge, all rows =
  0x08+0x10+0x20+0x80 = 0xB8. Mask 0xF9 = U+28F9.
- Cells (0,0),(3,0),(0,1)..(3,1) are empty: spaces, fg `normal`. Independent re-derivation matches the
  coordinator's hand values 0xCF / 0xF9 exactly.

**obs_ref_circle_r05_green** (2x1 stage, circle(0.5) at (0,0), green). circle(0.5): diameter 1 cell, W=H=1, box
[0,1]x[0,3], centre (0.5,1.5), radii (0.5,1.5). The 721 vertices (k=0..720) give 720 chords; each chord is tiny
(|dx|,|dy| <= ~0.0131) so steps = 1 (min) and only its two endpoints are sampled. Vertices near the extreme points
are at x=0.5+-0.5 -> dots 0 and 1; y=1.5+-1.5 -> 0 and 3; tie values (x=0.5, y=0.5/1.5/2.5) occur at
the symmetric points. A throwaway python3 float/Decimal script (no MDGL code) rounding all sampled points to the
nearest integer visits all eight dots (0..1)x(0..3) under half-up, half-even and half-down tie rules, with and
without 1e-9 quantisation, so the result does not depend on tie handling. Mask 0xFF = U+28FF in cell (0,0); cell
(1,0) is a blank space. Colour green (full opacity) on the painted cell only.

**obs_ref_cube_x_30_red** (14x10, cube(size=8,style=wire) at (3,1) color=red, rotate x=30 over 1 s). Source is
the legacy `cube_x_30.mdgl` plus `color=red` (grammar SPEC `actor ... { "color" "=" color }`). Glyph rows are the
legacy `cube_x_30.expect` `@1` rows padded to width 14 (not re-derived, G7). Every non-blank glyph has fg red,
blanks `normal`, bg `""`; P=1 so done is true at t=1. Class `timed` (cells + done compared, fg/bg required;
class `cube` would be glyph-only). The cube keeps the SPEC dot offset.

## 4. Provenance

- Profile text: coordinator-supplied, from the independent journal entry re 001a126f647cf5cfa9c63e03c6725eaaf.
- Cube glyphs: legacy `cube_x_30.mdgl` / `.expect` (independently accepted). No Go output was used or consulted.
- Masks/glyphs for rect and circle: hand/throwaway arithmetic from section 1-2 formulas only.
- The derivations were hand-made; the final integration later showed all five adapters agreeing with them (bounded evidence, not certification).

## 5. Where the profile differs from, or goes beyond, SPEC (open mismatch/gap list)

| item | SPEC | profile | status |
|---|---|---|---|
| rect/circle dot offset | `2*cellX-0.5`, `4*cellY-0.5` (SPEC.md:234, stated generally) | none (integer origin) for rect/circle; cube keeps the SPEC offset | open mismatch |
| rect/circle dot extents | unstated (G7) | box [0,2W-1]x[0,4H-1], edges incl. corners | profile-only, gap |
| circle sample count/start | "sampled on that grid" only | 720 chords, k=0..720, from rightmost point | profile-only, gap |
| line step cap | ceil(max(abs dx,abs dy)) (SPEC.md:236), no cap | min 1, cap 800 | profile-only, gap |
| endpoint quantisation | 1e-9 dot before stepping (SPEC.md:227-228) | same, then clip | agrees; clip order is profile detail |
| tie rounding at .5 | "nearest integer" | unspecified; fixtures chosen so result is tie-independent | gap (circle fixture checked under 3 rules) |
| title epsilon | unresolved | not used | open gap |
| reveal / transform | unresolved contradiction | not used | open gap |
| raster extents of rotated shapes | unstated | not used (cube glyphs reused) | open gap |

Source-vs-fixture negative zero: MDGL source times take no sign (grammar `time = unsigned`), so `-0` in a scene is a
syntax error; fixture-time strings (`frames[].time`, `.expect` headers) reject a leading minus including `-0`
before rounding (PROTOCOL 2.1); JSON `time_ns` -0 is mathematically 0 and is accepted on the wire.

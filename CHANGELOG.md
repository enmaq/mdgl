# Changelog

All notable changes to MDGL. The format follows [Keep a Changelog](https://keepachangelog.com/);
0.x versions are unstable and may change the syntax between minor versions.

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

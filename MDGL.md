# MDGL 0.1 — authoring primer

Put a scene in a `mdgl` Markdown fence. Coordinates are terminal cells; time is
absolute seconds. Run `mdgl check demo.mdgl` before rendering.

```mdgl
mdgl 0.1
scene width=40 height=8 period=4s fallback=end
actor title = text("Build complete") at (center, 1) color=green
actor box = rect(14, 4) at (center, 3)
@0: title.fade(in, dur=1, ease=ease-out)
@1: box.move(to=(right, 3), dur=2, ease=ease-in-out)
```

- Declare one scene, then all actors, then actions. Names are explicit; typos are
  errors with suggestions. Every scene needs width, height, fallback.
- Actors: `text("hello")`, `rect(12,4,title="Status")`, `circle(3)`,
  `cube(size=6,style=wire)`. Optional `color=red`, `parent=box`, integer `z=1`.
  Children use parent-local coordinates and inherit the full transform and opacity.
  Scale/rotation pivot at the local centre; use `anchor=(0,0)` for top-left.
- Positions: `(2,3)`, `(center,top)`, `(right-2,bottom)`, `(50%,0)`.
  Center/right/bottom account for the actor's unscaled size.
- Actions: `name.fade(in|out,dur=1)`, `move(to=(x,y),dur=1)`,
  `scale(to=1.5,dur=1)`, `color(to=cyan,dur=1)`, `type(per_char=0.1)`,
  `blink(times=3,dur=1)`, `wipe(in|out,dur=1)`,
  `slide(in|out,to=left,dur=1)`, `rotate(x=90,y=180,dur=2)` (cube only).
- Easing: linear (default), CSS ease/ease-in/ease-out/ease-in-out, bounce.
  Blink and type use their own timing and do not take ease.
- End values freeze. Overlapping actions on the same actor/property are errors,
  including fade+blink and move+slide. Adjacent actions are allowed.
- `repeat=3` or `repeat=infinite` needs `period=...`; every action must fit.
  Fallback is `start`, `end`, or `@1.5`; use a meaningful still frame.
- Maximum 200×60 cells, 64 actors, 1024 actions, 60 seconds per period, 30 fps.
  Use named colors normal/black/red/green/yellow/blue/magenta/cyan/white/accent.
- Shapes use braille dots. Text is one grapheme per cell, with wide glyphs replaced
  by `�`. `big` is advisory only. No multiline strings or control characters.
- Camera/light/mesh/material/three.js imports are reserved for later versions.
  0.1 has a fixed ortho stage and a fixed-perspective wire cube, no shaders.
- World is right-handed, +Y up; layout rows point down with a viewport flip.
  Cube Euler XYZ matches three.js (`Rx*Ry*Rz`); angles are degrees or `rad`.
  Perspective uses vertical FOV50°, physical cell aspect2:1 and near/far clipping.
  Opacity blends RGB, rather than hiding actors below 50%.

`mdgl frames demo.mdgl --at 0,1,4` emits plain frame rows. `mdgl play demo.mdgl`
uses dirty terminal cells and DEC 2026, then stops completely when done. Redirect
output or set `MDGL_REDUCED_MOTION=1` for the fallback frame without animation.

Embedding (module `github.com/enmaq/mdgl`):

```go
scene, diagnostics := mdgl.Parse(source)
if len(diagnostics) == 0 {
    frame := scene.Frame(1.5, 80, 24) // [][]Cell: Rune, Color, Background
    _ = frame.Lines()
    _ = scene.Active(1.5) // false after finite completion; no scheduler in library
    _ = scene.FallbackFrame(80, 24)
}
```

`Scene.Period`, `Fallback` are seconds; `Width`, `Height`, `FPS` are integers.
Do not mutate exported metadata; validated internals remain immutable and frames
can be sampled concurrently. The full normative contract is in SPEC.md.
Cell colors may be named or `#rrggbb`; empty Background means black. Hosts must
honor RGB foreground/background, not reduce blends back to named colors.

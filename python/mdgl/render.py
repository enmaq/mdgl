"""Terminal-cell renderer: braille dots, text, RGB source-over blending, wire cube."""
import math
from dataclasses import dataclass
from typing import List

from . import geometry as g
from .model import glyphs

_PALETTE = {"black": 0x000000, "red": 0xFF0000, "green": 0x00FF00, "yellow": 0xFFFF00, "blue": 0x0000FF,
            "magenta": 0xFF00FF, "cyan": 0x00FFFF, "accent": 0x00FFFF, "white": 0xFFFFFF}
_BIT = ((0, 3), (1, 4), (2, 5), (6, 7))


def go_round(x):
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


@dataclass
class Cell:
    rune: str = " "
    color: str = "normal"
    background: str = ""


def _rgb(color, background):
    value = _PALETTE.get(color)
    if len(color) == 7 and color[0] == "#":
        try:
            value = int(color[1:], 16)
        except ValueError:
            pass
    if value is None:
        value = 0 if background else 0xFFFFFF
    return [float(value >> 16), float(value >> 8 & 255), float(value & 255)]


def _over(dst, glyph, color, opacity):
    opacity = max(0.0, min(1.0, opacity))
    if opacity == 0:
        return dst
    if opacity == 1:
        return Cell(glyph, color, dst.background)
    below = _rgb(dst.background, True) if dst.rune == " " else _rgb(dst.color, False)
    fg = _rgb(color, False)
    out = [go_round(fg[i] * opacity + below[i] * (1 - opacity)) for i in range(3)]
    return Cell(glyph, "#%02x%02x%02x" % tuple(int(c) for c in out), dst.background)


def render(state, cols, rows):
    cols, rows = max(0, min(200, cols)), max(0, min(60, rows))
    grid = [[Cell() for _ in range(cols)] for _ in range(rows)]
    if rows == 0 or cols == 0:
        return grid
    for a in sorted(state.actors, key=lambda s: s.z):
        if a.opacity <= 0 or a.reveal <= 0:
            continue
        kind = a.actor.kind
        if kind == "text":
            _text(grid, a, a.actor.text, 0, 0, a.actor.width)
            continue
        dots = [bytearray(cols * 2) for _ in range(rows * 4)]
        w, h = a.actor.width, a.actor.height
        lx, ly = max(0.0, w * 2 - 1), max(0.0, h * 4 - 1)
        if kind in ("rect", "circle"):
            matrix = g.mul(g.ortho(0, cols, -2 * rows, 0, -1000, 1000), _transform(a))

            def draw(sx, sy, ex, ey):
                s = g.transform(matrix, [sx / 2, -sy / 2, 0, 1])
                e = g.transform(matrix, [ex / 2, -ey / 2, 0, 1])
                c = g.clip(s, e)
                if c:
                    x0, y0 = g.viewport(c[0], cols * 2, rows * 4)
                    x1, y1 = g.viewport(c[1], cols * 2, rows * 4)
                    _line(dots, x0, y0, x1, y1)

            if kind == "rect":
                draw(0, 0, lx, 0)
                draw(lx, 0, lx, ly)
                draw(lx, ly, 0, ly)
                draw(0, ly, 0, 0)
            else:
                cx, cy, rx, ry = lx / 2, ly / 2, lx / 2, ly / 2
                px, py = cx + rx, cy
                for k in range(1, 721):
                    ang = k * math.pi / 360
                    nx, ny = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
                    draw(px, py, nx, ny)
                    px, py = nx, ny
        elif kind == "cube":
            _cube(dots, a)
        for row in range(rows):
            for col in range(cols):
                mask = 0
                for v in range(4):
                    for hh in range(2):
                        if dots[row * 4 + v][col * 2 + hh]:
                            mask |= 1 << _BIT[v][hh]
                if mask and (a.reveal >= 1 or col + 0.5 <= a.x + w * a.scale * a.reveal):
                    grid[row][col] = _over(grid[row][col], chr(0x2800 + mask), a.color, a.opacity)
        if kind == "rect" and a.actor.text:
            _text(grid, a, a.actor.text, 1, 0, max(0.0, a.actor.width - 2))
    return grid


def _transform(a):
    if any(a.transform):
        return a.transform
    ax, ay = a.actor.width / 2, a.actor.height
    return g.mul(g.compose([a.x + ax, -2 * a.y - ay, 0], a.rotation, [a.scale] * 3), g.translation(-ax, ay, 0))


def _text(grid, a, text, ox, oy, max_width):
    gl = glyphs(text)
    limit = min(len(gl), int(math.floor(max_width * a.reveal + 1e-9)))
    m = _transform(a)
    for i in range(limit):
        p = g.transform(m, [ox + float(i), -2.0 * oy, 0, 1])
        x, y = go_round(p[0]), go_round(-p[1] / 2)
        if x < 0 or y < 0 or y >= len(grid) or x >= len(grid[0]):
            continue
        if gl[i] != " ":
            grid[y][x] = _over(grid[y][x], gl[i], a.color, a.opacity)


def _line(dots, sx, sy, ex, ey):
    sx, sy = go_round(sx * 1e9) / 1e9, go_round(sy * 1e9) / 1e9
    ex, ey = go_round(ex * 1e9) / 1e9, go_round(ey * 1e9) / 1e9
    width, height = float(len(dots[0]) - 1), float(len(dots) - 1)
    dx, dy = ex - sx, ey - sy
    lower, upper = 0.0, 1.0
    for direction, distance in ((-dx, sx), (dx, width - sx), (-dy, sy), (dy, height - sy)):
        if direction == 0:
            if distance < 0:
                return
            continue
        ratio = distance / direction
        if direction < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return
    cx, cy = sx + lower * dx, sy + lower * dy
    ex, ey = sx + upper * dx, sy + upper * dy
    steps = int(min(800.0, math.ceil(max(abs(ex - cx), abs(ey - cy)))))
    if steps <= 0:
        steps = 1
    for step in range(steps + 1):
        p = step / steps
        x, y = int(go_round(cx + (ex - cx) * p)), int(go_round(cy + (ey - cy) * p))
        if 0 <= y < len(dots) and 0 <= x < len(dots[0]):
            dots[y][x] = 1


def _cube(dots, a):
    size, height = a.actor.width, a.actor.height
    world = _transform(a)
    center = g.transform(world, [size / 2, -height, 0, 1])
    view = g.translation(-center[0], -center[1], -(3 * size))
    proj = g.perspective(50, size / (2 * height), 0.1, 1000)
    m = g.mul(g.mul(proj, view), world)
    corners = []
    for i in range(8):
        hx = 0.5 if i & 1 else -0.5
        vy = 0.5 if i & 2 else -0.5
        dz = 0.5 if i & 4 else -0.5
        corners.append(g.transform(m, [size / 2 + hx * size, -height + vy * size, dz * size, 1]))
    for i in range(8):
        for bit in (1, 2, 4):
            o = i ^ bit
            if o > i:
                c = g.clip(corners[i], corners[o])
                if not c:
                    continue
                x0, y0 = g.viewport(c[0], size, height)
                x1, y1 = g.viewport(c[1], size, height)
                ox, oy = center[0] - size / 2, -center[1] / 2 - height / 2
                _line(dots, (ox + x0) * 2 - 0.5, (oy + y0) * 4 - 0.5, (ox + x1) * 2 - 0.5, (oy + y1) * 4 - 0.5)


def lines(grid):
    return ["".join(c.rune for c in row) for row in grid]

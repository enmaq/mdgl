"""Checked scene + time -> cell frames, with period/repeat/Done and fallback."""
from dataclasses import dataclass
from typing import List

from . import evaluate
from .checker import load
from .evaluate import number
from .model import Value
from .render import Cell, lines, render


@dataclass
class Frame:
    cells: List[List[Cell]]
    done: bool

    def lines(self):
        return lines(self.cells)


class Animation:
    """Pure, seekable animation compiled from MDGL source (raises MdglError)."""

    def __init__(self, source):
        self.scene = scene = load(source)
        self.width, self.height, self.fps = scene.width, scene.height, scene.fps
        self.period = scene.period
        fb = 0.0
        if scene.fallback == "end":
            fb = scene.period
        elif scene.fallback.startswith("@"):
            fb = number(Value(scene.fallback[1:]))
        self.fallback = fb

    def _size(self, cols, rows):
        return (min(cols, self.width) if cols is not None else self.width,
                min(rows, self.height) if rows is not None else self.height)

    def active(self, seconds):
        return evaluate.active(self.scene, seconds)

    def frame(self, seconds, cols=None, rows=None):
        c, r = self._size(cols, rows)
        st = evaluate.frame(self.scene, seconds)
        return Frame(render(st, c, r), st.done)

    def frame_ns(self, nanos, cols=None, rows=None):
        return self.frame(nanos / 1e9, cols, rows)

    def fallback_frame(self, cols=None, rows=None):
        c, r = self._size(cols, rows)
        return Frame(render(evaluate.at(self.scene, self.fallback), c, r), True)


def compile(source):  # noqa: A001 - mirrors mdgl.Parse naming
    return Animation(source)

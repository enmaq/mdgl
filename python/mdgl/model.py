"""Source-located scene model (parsed, then filled in by the checker)."""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .graphemes import clusters


class MdglError(ValueError):
    """First diagnostic: one-based line, one-based UTF-8 byte column, message."""

    def __init__(self, line, col, message):
        super().__init__("%d:%d: %s" % (line, col, message))
        self.line, self.col, self.message = line, col, message

    @property
    def diagnostic(self):
        return {"line": self.line, "col": self.col, "message": self.message}


@dataclass(frozen=True)
class Pos:
    line: int
    col: int = 1

    def error(self, message):
        return MdglError(self.line, self.col, message)


@dataclass(frozen=True)
class Value:
    text: str = ""
    pair: Tuple["Value", ...] = ()
    quoted: bool = False


Args = Dict[str, Value]


@dataclass
class Actor:
    pos: Pos
    name: str
    kind: str
    args: Args
    x: Value
    y: Value
    attr: Args = field(default_factory=dict)
    text: str = ""
    color: str = "normal"
    parent: str = ""
    width: float = 0.0
    height: float = 0.0
    z: float = 0.0
    scale: float = 1.0


@dataclass
class Action:
    pos: Pos
    actor: str
    verb: str
    args: Args
    begin: float
    duration: float = 0.0
    property: str = ""
    ease: str = "linear"


@dataclass
class Scene:
    pos: Pos = Pos(1, 1)
    attr: Args = field(default_factory=dict)
    actors: List[Actor] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    width: int = 0
    height: int = 0
    fps: int = 30
    period: float = 0.0
    explicit_period: bool = False
    repeat: int = 1  # 0 = infinite
    fallback: str = ""
    checked: bool = False


_NUM = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)\Z")


def finite(x):
    return not (math.isnan(x) or math.isinf(x))


def parse_float(text):
    """Finite non-exponent decimal; raises ValueError otherwise."""
    if not _NUM.match(text):
        raise ValueError(text)
    x = float(text)
    if not finite(x):
        raise ValueError(text)
    return x


def to_nanos(x):
    """Round to nanoseconds (half away from zero), like the Go reference."""
    if abs(x) > 1e6:
        return x
    y = x * 1e9
    return (math.floor(y + 0.5) if y >= 0 else -math.floor(-y + 0.5)) / 1e9


def glyphs(text):
    """One rune per extended grapheme cluster: first non-mark rune; wide -> U+FFFD."""
    out = []
    for cluster, width in clusters(text):
        g = " "
        if width > 1:
            g = "\ufffd"
        else:
            for c in cluster:
                if not unicodedata.category(c).startswith("M") and c != "\u200d":
                    g = c
                    break
        out.append(g)
    return out

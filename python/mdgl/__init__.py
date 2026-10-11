"""MDGL for Python (development): parser and semantic checker.

Development tree, not a release: published 0.2.0 artifacts are the old subset
checker. This tree adds a parser, checker, evaluator and terminal-cell renderer
following SPEC.md; full conformance is not claimed without shared runner evidence.
Spec: https://github.com/enmaq/mdgl/blob/main/SPEC.md
"""

from .checker import check_scene, load
from .model import Action, Actor, MdglError, Pos, Scene, Value
from .parser import parse
from .animation import Animation, Frame, compile
from .render import Cell

__version__ = "0.3.1"
__all__ = ["check", "parse", "load", "check_scene", "MdglError", "Scene", "Actor", "Action",
           "Pos", "Value", "Animation", "Frame", "Cell", "compile", "__version__"]


def check(source):
    """Returns [] or [{line, col, message}] with the first diagnostic.

    Raises TypeError for non-str input.
    """
    if not isinstance(source, str):
        raise TypeError("mdgl.check: source must be str")
    try:
        load(source)
    except MdglError as e:
        return [e.diagnostic]
    return []

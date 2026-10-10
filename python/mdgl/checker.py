"""Semantic checker: validates and fills in a parsed Scene (mirrors SPEC)."""
import math
import unicodedata
from decimal import Decimal
from .model import MdglError, Value, finite, glyphs, parse_float, to_nanos
from .parser import go_quote, parse, unknown

COLORS = ["normal", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "accent"]
EASES = ["linear", "ease", "ease-in", "ease-out", "ease-in-out", "bounce"]
VERBS = ["fade", "move", "scale", "color", "type", "blink", "wipe", "slide", "rotate"]
SHAPE_ARGS = {"text": ["0", "1"], "rect": ["0", "1", "border", "title"], "circle": ["0"], "cube": ["size", "style"]}
ACTION_ARGS = {
    "fade": ["0", "dur", "ease"], "move": ["to", "dur", "ease"], "scale": ["to", "dur", "ease"],
    "color": ["to", "dur", "ease"], "type": ["per_char"], "rotate": ["x", "y", "z", "dur", "ease"],
    "blink": ["times", "dur"], "wipe": ["0", "dur", "ease"], "slide": ["0", "to", "dur", "ease"],
}
_RESERVED = ("camera", "light", "material", "position", "rotation", "threejs")
_EMPTY = Value()


class _Fail(Exception):
    pass


def _number(v):
    if v.quoted or v.pair:
        raise _Fail("expected number")
    try:
        return parse_float(v.text[:-1] if v.text.endswith("s") else v.text)
    except ValueError:
        raise _Fail("expected finite number")


def _integer(v, lo, hi, name):
    try:
        r = _number(v)
    except _Fail:
        r = None
    if r is None or r != math.trunc(r) or r < lo or r > hi:
        raise _Fail("%s must be an integer in %d..%d" % (name, lo, hi))
    return int(r)


def _dimension(v):
    r = _number(v)
    if r <= 0 or r > 200:
        raise _Fail("invalid dimension")
    return r


def _one_of(v, choices):
    return not v.quoted and not v.pair and v.text in choices


def _keys(args, allowed, kind):
    for key in sorted(args):
        if key in _RESERVED:
            raise _Fail("%s is reserved; not yet supported in 0.1" % key)
        if key not in allowed:
            if kind.endswith("argument"):
                choices = [a for a in allowed if not a.isdigit()]
                valid = ["positional %d" % (int(a) + 1) if a.isdigit() else a for a in allowed]
                raise _Fail("%s; valid arguments: %s" % (unknown(kind, key, choices), ", ".join(valid)))
            raise _Fail(unknown(kind, key, allowed))


def _coordinate(v, horizontal):
    if v.quoted or v.pair:
        raise _Fail("invalid coordinate")
    text = v.text
    try:
        r = _number(Value(text[:-1] if text.endswith("%") else text))
        if abs(r) > 10000:
            raise _Fail("coordinate exceeds -10000..10000")
        return
    except _Fail as e:
        if "exceeds" in e.args[0]:
            raise
    for a in ("center", "left", "right") if horizontal else ("center", "top", "bottom"):
        if text == a:
            return
        if text.startswith(a + "+") or text.startswith(a + "-"):
            try:
                if abs(_number(Value(text[len(a):]))) <= 10000:
                    return
            except _Fail:
                pass
    raise _Fail("invalid coordinate " + go_quote(text))


def _valid_text(text):
    if len(glyphs(text)) > 1024:
        raise _Fail("text exceeds 1024 graphemes")
    for c in text:
        if unicodedata.category(c) == "Cc" or c in "\u2028\u2029":
            raise _Fail("text contains a control character")


def _fmt(x):
    s = repr(x)
    if "e" in s or "E" in s:
        s = format(Decimal(s), "f")
    return s[:-2] if s.endswith(".0") else s


def _angle(v):
    if v.text.endswith("rad"):
        return _number(Value(v.text[:-3])) * 180 / math.pi
    return _number(Value(v.text[:-3] if v.text.endswith("deg") else v.text))


def check_scene(scene):
    """Validate a parsed Scene in place. Raises MdglError (first diagnostic)."""
    _check(scene)
    scene.checked = True
    return scene


def _at(pos, fn, *a):
    try:
        return fn(*a)
    except _Fail as e:
        raise MdglError(pos.line, pos.col, e.args[0])


def _check(scene):
    P = scene.pos

    def fail(msg):
        raise MdglError(P.line, P.col, msg)

    def s(fn, *a):
        return _at(P, fn, *a)

    s(_keys, scene.attr, ["width", "height", "period", "repeat", "fallback", "fps"], "scene attribute")
    for r in ("width", "height", "fallback"):
        if r not in scene.attr:
            fail("missing scene attribute " + r)
    A = scene.attr
    scene.width = s(_integer, A["width"], 1, 200, "width")
    scene.height = s(_integer, A["height"], 1, 60, "height")
    scene.fps = 30
    if "fps" in A:
        scene.fps = s(_integer, A["fps"], 1, 30, "fps")
    scene.period, scene.explicit_period, scene.repeat = 0.0, False, 1
    if "period" in A:
        scene.explicit_period = True
        try:
            p = _number(A["period"])
        except _Fail:
            p = 0
        if p <= 0 or p > 60:
            fail("period must be positive and <=60")
        scene.period = to_nanos(p)
        if scene.period == 0:
            fail("period rounds to zero at nanosecond precision")
    if "repeat" in A:
        v = A["repeat"]
        if v.text == "infinite" and not v.quoted:
            scene.repeat = 0
        else:
            scene.repeat = s(_integer, v, 1, 1000, "repeat")
        if scene.repeat != 1 and not scene.explicit_period:
            fail("repeat requires explicit period")
    scene.fallback = A["fallback"].text
    if A["fallback"].quoted or A["fallback"].pair:
        fail("fallback must be start, end or @time")

    names, ordered = {}, []
    for index, actor in enumerate(scene.actors):
        pos = actor.pos

        def a(fn, *args, _pos=pos):
            return _at(_pos, fn, *args)

        def afail(msg, _pos=pos):
            raise MdglError(_pos.line, _pos.col, msg)

        if actor.name in names:
            afail("duplicate actor " + actor.name)
        names[actor.name] = index
        ordered.append(actor.name)
        a(_keys, actor.attr, ["color", "parent", "z", "anchor"], "actor attribute")
        actor.color, actor.parent, actor.scale = "normal", "", 1.0
        if "color" in actor.attr:
            v = actor.attr["color"]
            if not _one_of(v, COLORS):
                afail(unknown("color", v.text, COLORS))
            actor.color = v.text
        if "parent" in actor.attr:
            v = actor.attr["parent"]
            if v.quoted or v.pair:
                afail("parent must be an actor identifier")
            actor.parent = v.text
        if "z" in actor.attr:
            actor.z = float(a(_integer, actor.attr["z"], -10000, 10000, "z"))
        k = actor.kind
        if k == "text":
            a(_keys, actor.args, SHAPE_ARGS[k], "text argument")
            t = actor.args.get("0")
            if t is None or not t.quoted:
                afail("text requires a quoted string")
            actor.text = t.text
            if "1" in actor.args and (actor.args["1"].text != "big" or actor.args["1"].quoted):
                afail("text style must be big")
            a(_valid_text, actor.text)
            actor.width, actor.height = float(len(glyphs(actor.text))), 1.0
        elif k == "rect":
            a(_keys, actor.args, SHAPE_ARGS[k], "rect argument")
            try:
                actor.width = _dimension(actor.args.get("0", _EMPTY))
            except _Fail:
                afail("rect width must be positive and <=200")
            try:
                actor.height = _dimension(actor.args.get("1", _EMPTY))
            except _Fail:
                afail("rect height must be positive and <=200")
            if "border" in actor.args and not _one_of(actor.args["border"], ["round", "square"]):
                afail("border must be round or square")
            if "title" in actor.args:
                v = actor.args["title"]
                if not v.quoted:
                    afail("title requires a quoted string")
                actor.text = v.text
                a(_valid_text, actor.text)
        elif k == "circle":
            a(_keys, actor.args, SHAPE_ARGS[k], "circle argument")
            try:
                r = _dimension(actor.args.get("0", _EMPTY))
                if r > 100:
                    raise _Fail("")
            except _Fail:
                afail("circle radius must be positive and <=100")
            actor.width = actor.height = r * 2
        elif k == "cube":
            a(_keys, actor.args, SHAPE_ARGS[k], "cube argument")
            try:
                actor.width = _dimension(actor.args.get("size", _EMPTY))
            except _Fail:
                afail("cube size must be positive and <=200")
            actor.height = actor.width
            if "style" in actor.args and not _one_of(actor.args["style"], ["wire"]):
                afail("only cube style=wire is supported in 0.1")
        elif k in ("mesh", "sphere", "plane", "threejs", "cells"):
            afail(k + " is reserved; not yet supported in 0.1")
        else:
            afail(unknown("shape", k, ["text", "rect", "circle", "cube"]))
        a(_coordinate, actor.x, True)
        a(_coordinate, actor.y, False)
        if "anchor" in actor.attr:
            v = actor.attr["anchor"]
            if len(v.pair) != 2:
                afail("anchor requires (x, y)")
            for axis, c in enumerate(v.pair):
                a(_coordinate, c, axis == 0)

    for actor in scene.actors:
        if actor.parent and actor.parent not in names:
            raise actor.pos.error(unknown("parent", actor.parent, ordered))
    for actor in scene.actors:
        seen, cur = set(), actor
        while cur.parent:
            if cur.name in seen:
                raise actor.pos.error("parent cycle involving " + actor.name)
            seen.add(cur.name)
            cur = scene.actors[names[cur.parent]]

    for index, action in enumerate(scene.actions):
        pos = action.pos

        def a(fn, *args, _pos=pos):
            return _at(_pos, fn, *args)

        def afail(msg, _pos=pos):
            raise MdglError(_pos.line, _pos.col, msg)

        if action.actor not in names:
            afail(unknown("actor", action.actor, ordered))
        actor = scene.actors[names[action.actor]]
        v = action.verb
        if v not in VERBS:
            afail(unknown("action", v, VERBS))
        if not finite(action.begin) or action.begin < 0:
            afail("invalid action time")
        action.begin = to_nanos(action.begin)
        a(_keys, action.args, ACTION_ARGS[v], "action argument")
        action.ease = "linear"
        g = action.args.get
        if v in ("fade", "wipe"):
            if not _one_of(g("0", _EMPTY), ["in", "out"]):
                afail(v + " requires in or out")
        elif v == "slide":
            if not _one_of(g("0", _EMPTY), ["in", "out"]):
                afail("slide requires in or out")
            if not _one_of(g("to", _EMPTY), ["left", "right", "top", "bottom"]):
                afail("slide to must be left, right, top or bottom")
        elif v == "type":
            if actor.kind != "text":
                afail("type requires a text actor")
        elif v == "blink":
            a(_integer, g("times", _EMPTY), 1, 1000, "times")
        elif v == "rotate":
            if actor.kind != "cube":
                afail("rotate requires a cube actor")
            found = False
            for axis in "xyz":
                if axis in action.args:
                    found = True
                    try:
                        ang = _angle(action.args[axis])
                        if abs(ang) > 10000:
                            raise _Fail("")
                    except _Fail:
                        afail("rotation must be within -10000..10000")
                    action.args[axis] = Value(_fmt(ang))
            if not found:
                afail("rotate requires x, y or z")
        if "ease" in action.args:
            e = action.args["ease"]
            if not _one_of(e, EASES):
                afail(unknown("easing", e.text, EASES))
            action.ease = e.text
        if v == "type":
            try:
                sec = _number(g("per_char", _EMPTY))
            except _Fail:
                sec = 0
            if sec <= 0:
                afail("per_char must be positive")
            sec = to_nanos(sec)
            if sec == 0:
                afail("per_char rounds to zero at nanosecond precision")
            action.args["per_char"] = Value(_fmt(sec))
            action.duration = sec * len(glyphs(actor.text))
        else:
            try:
                action.duration = _number(g("dur", _EMPTY))
            except _Fail:
                action.duration = 0
            if action.duration <= 0:
                afail("dur must be positive")
        action.property = {"fade": "opacity", "blink": "opacity", "type": "reveal", "wipe": "reveal",
                           "move": "position", "slide": "position", "scale": "scale",
                           "color": "color", "rotate": "rotation"}[v]
        if v == "move":
            pair = g("to", _EMPTY).pair
            if len(pair) != 2:
                afail("move requires to=(x, y)")
            a(_coordinate, pair[0], True)
            a(_coordinate, pair[1], False)
        elif v == "scale":
            try:
                f = _number(g("to", _EMPTY))
            except _Fail:
                f = 0
            if f <= 0 or f > 16:
                afail("scale to must be positive and <=16")
        elif v == "color":
            if not _one_of(g("to", _EMPTY), COLORS):
                afail(unknown("color", g("to", _EMPTY).text, COLORS))
        action.duration = to_nanos(action.duration)
        if action.duration == 0 and v != "type":
            afail("dur rounds to zero at nanosecond precision")
        end = to_nanos(action.begin + action.duration)
        if not finite(end) or end > 60:
            afail("action end must be <=60")
        if scene.explicit_period:
            if end > scene.period:
                afail("action exceeds period")
        elif end > scene.period:
            scene.period = end
        for other in scene.actions[:index]:
            if (action.actor == other.actor and action.property == other.property
                    and action.begin < to_nanos(other.begin + other.duration) and other.begin < end):
                afail("overlapping %s actions on %s" % (action.property, action.actor))

    if scene.fallback not in ("start", "end"):
        if not scene.fallback.startswith("@"):
            fail("fallback must be start, end or @time")
        try:
            t = _number(Value(scene.fallback[1:]))
        except _Fail:
            t = -1
        if t < 0 or t > scene.period:
            fail("fallback time must be within period")


def load(source):
    """Parse and check; returns a checked Scene or raises MdglError."""
    return check_scene(parse(source))

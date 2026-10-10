"""MDGL 0.0.1 -- SUBSET limit/header checker. NOT a conformant MDGL implementation.

Checks only: input <= 256 KiB, line <= 16 KiB, scene header (width 1..200,
height 1..60, fallback; no unknown/duplicate keys), statement order,
<= 64 actors, <= 1024 actions. Does NOT parse actor/action bodies or check
grammar, timing, references or rendering. An empty result means
"no limit/header problems found", NOT "valid MDGL". Reference: the Go module.
Spec: https://github.com/enmaq/mdgl/blob/main/SPEC.md
"""

__version__ = "0.2.0"
__all__ = ["check", "__version__"]

_MAX_INPUT = 256 * 1024
_MAX_LINE = 16384
_MAX_ACTORS = 64
_MAX_ACTIONS = 1024
_KEYS = ("width", "height", "period", "repeat", "fallback", "fps")
_WS = " \t\r"


def _d(line, message):
    return [{"line": line, "col": 1, "message": message}]


def _blen(s):
    try:
        return len(s.encode("utf-8"))
    except UnicodeEncodeError:
        return None


def _scene_header(n, rest):
    seen = {}
    for tok in rest.replace("\t", " ").replace("\r", " ").split():
        k, eq, v = tok.partition("=")
        if not eq or not k or not v:
            return _d(n, "malformed scene attribute %r" % tok)
        if k not in _KEYS:
            return _d(n, "unknown scene attribute %r" % k)
        if k in seen:
            return _d(n, "duplicate scene attribute %r" % k)
        seen[k] = v
    out = [{"line": n, "col": 1, "message": "scene header missing %s=" % k}
           for k in ("width", "height", "fallback") if k not in seen]
    if out:
        return out
    for k, mx in (("width", 200), ("height", 60)):
        v = seen[k]
        if not (v.isascii() and v.isdigit() and len(v) <= 9 and 1 <= int(v) <= mx):
            return _d(n, "%s must be an integer 1..%d" % (k, mx))
    return []


def check(source):
    """Subset check. Returns a list of {line, col, message} dicts.

    [] means "no limit/header problems found" (NOT "valid MDGL").
    Raises TypeError for non-str input.
    """
    if not isinstance(source, str):
        raise TypeError("mdgl.check: source must be str")
    total = _blen(source)
    if total is None:
        return _d(1, "input is not valid UTF-8")
    if total > _MAX_INPUT:
        return _d(1, "input exceeds 256 KiB")
    scene = action = version = False
    actors = actions = 0
    for i, line in enumerate(source.split("\n")):
        n = i + 1
        if _blen(line) > _MAX_LINE:
            return _d(n, "line exceeds 16 KiB")
        t = line.strip(_WS)
        if not t or t[0] == "#":
            continue
        head = "@" if t[0] == "@" else t.replace("\t", " ").split(" ", 1)[0]
        if head == "mdgl":
            if scene or version or t[4:].strip(_WS) != "0.1":
                return _d(n, "expected initial mdgl 0.1")
            version = True
        elif head == "scene":
            if scene:
                return _d(n, "duplicate scene")
            scene = True
            r = _scene_header(n, t[5:])
            if r:
                return r
        elif head == "actor":
            if not scene:
                return _d(n, "scene must precede actors")
            if action:
                return _d(n, "actors must precede actions")
            actors += 1
            if actors > _MAX_ACTORS:
                return _d(n, "actor limit 64 exceeded")
        elif head == "@":
            if not scene:
                return _d(n, "scene must precede actions")
            action = True
            actions += 1
            if actions > _MAX_ACTIONS:
                return _d(n, "action limit 1024 exceeded")
        else:
            return _d(n, "unsupported statement (expected mdgl, scene, actor or @)")
    return [] if scene else _d(1, "missing scene")

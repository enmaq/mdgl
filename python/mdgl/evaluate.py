"""Pure evaluator: checked Scene + time -> per-actor state (SPEC "Time and geometry")."""
import math
from dataclasses import dataclass, field
from typing import List

from . import geometry as g
from .model import Actor, finite, glyphs, to_nanos
from .checker import _number


def number(value):
    try:
        return _number(value)
    except Exception:
        return 0.0


def resolve(value, extent, size):
    text = value.text
    remaining = extent - size
    if text.endswith("%"):
        return number(type(value)(text[:-1])) * remaining / 100
    for anchor in ("center", "left", "right", "top", "bottom"):
        if text.startswith(anchor):
            base = 0.0
            if anchor == "center":
                base = remaining / 2
            if anchor in ("right", "bottom"):
                base = remaining
            tail = text[len(anchor):]
            if tail:
                base += number(type(value)(tail))
            return base
    return number(value)


@dataclass
class ActorState:
    actor: Actor
    x: float
    y: float
    z: float
    scale: float = 1.0
    opacity: float = 1.0
    reveal: float = 1.0
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    transform: List[float] = field(default_factory=lambda: [0.0] * 16)
    color: str = "normal"


@dataclass
class State:
    width: int
    height: int
    actors: List[ActorState]
    done: bool = False


def _ns(seconds):
    """Integer nanoseconds of an already ns-rounded time (exact: the float is within 1e-7 of the integer)."""
    return round(seconds * 1e9)


def _mix(a, b, p):
    return a + (b - a) * p


def active(scene, time):
    return scene.period > 0 and (scene.repeat == 0 or to_nanos(time) < to_nanos(scene.period * scene.repeat))


def frame(scene, time):
    if not finite(time) or time < 0:
        time = 0.0
    time = to_nanos(time)
    done = not active(scene, time)
    if scene.period > 0:
        if done:
            time = scene.period
        else:
            time = to_nanos(math.fmod(time, scene.period))
            if time == scene.period:
                time = 0.0
    state = at(scene, time)
    state.done = done
    return state


def _extent(scene, actor, names):
    if actor.parent:
        p = scene.actors[names[actor.parent]]
        return p.width, p.height
    return float(scene.width), float(scene.height)


def _outside(scene, st, direction, names):
    h, v = st.x, st.y
    w, ht = _extent(scene, st.actor, names)
    if direction == "left":
        h = -st.actor.width * st.scale
    elif direction == "right":
        h = w
    elif direction == "top":
        v = -st.actor.height * st.scale
    elif direction == "bottom":
        v = ht
    return h, v


def at(scene, time):
    time = max(0.0, min(scene.period, time))
    names = {a.name: i for i, a in enumerate(scene.actors)}
    state = State(scene.width, scene.height, [])
    for a in scene.actors:
        w, h = _extent(scene, a, names)
        state.actors.append(ActorState(a, resolve(a.x, w, a.width), resolve(a.y, h, a.height), a.z, color=a.color))
    initialized = set()
    now = _ns(time)
    for act in sorted(scene.actions, key=lambda x: x.begin):
        begin, dur = _ns(act.begin), _ns(act.duration)
        t = state.actors[names[act.actor]]
        key = act.actor + "/" + act.property
        first = act.args.get("0")
        first = first.text if first else ""
        if key not in initialized:
            initialized.add(key)
            if act.verb == "fade" and first == "in":
                t.opacity = 0.0
            if act.verb == "type" or (act.verb == "wipe" and first == "in"):
                t.reveal = 0.0
            if act.verb == "slide" and first == "in" and now < begin:
                t.x, t.y = _outside(scene, t, act.args["to"].text, names)
        if now < begin:
            continue
        # integer-ns first (root decision): no float subtraction noise at exact boundaries
        progress = min(1.0, (now - begin) / dur) if dur > 0 else 1.0
        if now >= begin + dur:
            progress = 1.0
        eased = ease(act.ease, progress)
        v = act.verb
        if v == "fade":
            t.opacity = eased if first == "in" else 1 - eased
        elif v == "move":
            w, h = _extent(scene, t.actor, names)
            pt = act.args["to"].pair
            t.x = _mix(t.x, resolve(pt[0], w, t.actor.width), eased)
            t.y = _mix(t.y, resolve(pt[1], h, t.actor.height), eased)
        elif v == "slide":
            ex, ey = _outside(scene, t, act.args["to"].text, names)
            if first == "in":
                t.x, t.y = _mix(ex, t.x, eased), _mix(ey, t.y, eased)
            else:
                t.x, t.y = _mix(t.x, ex, eased), _mix(t.y, ey, eased)
        elif v == "scale":
            t.scale = _mix(t.scale, number(act.args["to"]), eased)
        elif v == "color":
            if eased >= 0.5:
                t.color = act.args["to"].text
        elif v == "type":
            count = float(len(glyphs(t.actor.text)))
            if count == 0:
                t.reveal = 1.0
            else:
                # SPEC: floor(elapsed / per_char) in exact integer nanoseconds (no float epsilon)
                steps = (now - begin) // _ns(number(act.args["per_char"]))
                t.reveal = min(count, steps) / count
        elif v == "wipe":
            t.reveal = eased if first == "in" else 1 - eased
        elif v == "blink":
            t.opacity = 1.0
            if progress < 1 and int(math.floor(progress * number(act.args["times"]) * 2)) % 2 == 1:
                t.opacity = 0.0
        elif v == "rotate":
            for axis, name in enumerate("xyz"):
                if name in act.args:
                    t.rotation[axis] = _mix(t.rotation[axis], number(act.args[name]), eased)
    composed = [False] * len(state.actors)

    def compose(i):
        if composed[i]:
            return
        s = state.actors[i]
        a = s.actor
        ax, ay = a.width / 2, a.height / 2
        if "anchor" in a.attr:
            p = a.attr["anchor"].pair
            ax, ay = resolve(p[0], a.width, 0), resolve(p[1], a.height, 0)
        s.transform = g.mul(g.compose([s.x + ax, -2 * (s.y + ay), 0], s.rotation, [s.scale] * 3),
                            g.translation(-ax, 2 * ay, 0))
        if a.parent:
            pi = names[a.parent]
            compose(pi)
            par = state.actors[pi]
            s.transform = g.mul(par.transform, s.transform)
            s.scale *= par.scale
            s.opacity *= par.opacity
            s.reveal *= par.reveal
        o = g.transform(s.transform, [0, 0, 0, 1])
        s.x, s.y = o[0], -o[1] / 2
        composed[i] = True

    for i in range(len(state.actors)):
        compose(i)
    return state


def ease(name, p):
    p = max(0.0, min(1.0, p))
    if name == "ease":
        return _bezier(p, 0.25, 0.1, 0.25, 1)
    if name == "ease-in":
        return _bezier(p, 0.42, 0, 1, 1)
    if name == "ease-out":
        return _bezier(p, 0, 0, 0.58, 1)
    if name == "ease-in-out":
        return _bezier(p, 0.42, 0, 0.58, 1)
    if name == "bounce":
        d = 2.75
        if p < 1 / d:
            return 7.5625 * p * p
        if p < 2 / d:
            p -= 1.5 / d
            return 7.5625 * p * p + 0.75
        if p < 2.5 / d:
            p -= 2.25 / d
            return 7.5625 * p * p + 0.9375
        p -= 2.625 / d
        return 7.5625 * p * p + 0.984375
    return p


def _bezier(p, x1, y1, x2, y2):
    if p == 0 or p == 1:
        return p

    def sample(t, a, b):
        i = 1 - t
        return 3 * i * i * t * a + 3 * i * t * t * b + t * t * t

    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if sample(mid, x1, x2) < p:
            lo = mid
        else:
            hi = mid
    return sample((lo + hi) / 2, y1, y2)

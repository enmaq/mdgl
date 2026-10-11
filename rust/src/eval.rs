//! Pure, stateless evaluator: a checked scene and an absolute time give actor states.
use crate::checker::time;
use crate::geometry::{self as g, Mat4};
use crate::model::{Actor, Scene, Value};
use crate::parse::decimal;

#[derive(Debug, Clone)]
pub struct ActorState {
    pub actor: usize,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub scale: f64,
    pub opacity: f64,
    pub reveal: f64,
    pub rotation: [f64; 3],
    pub transform: Mat4,
    pub color: String,
}

#[derive(Debug, Clone)]
pub struct State {
    pub actors: Vec<ActorState>,
    pub done: bool,
}

pub(crate) fn number(v: Option<&Value>) -> f64 {
    v.and_then(|v| decimal(v.text.strip_suffix('s').unwrap_or(&v.text))).unwrap_or(0.0)
}

/// Resolve a coordinate: cells, percent of remaining space, or anchor plus offset.
pub fn resolve(v: &Value, extent: f64, size: f64) -> f64 {
    let t = v.text.as_str();
    let remaining = extent - size;
    if let Some(p) = t.strip_suffix('%') {
        return number(Some(&Value { text: p.into(), ..Default::default() })) * remaining / 100.0;
    }
    for a in ["center", "left", "right", "top", "bottom"] {
        if let Some(tail) = t.strip_prefix(a) {
            let base = match a {
                "center" => remaining / 2.0,
                "right" | "bottom" => remaining,
                _ => 0.0,
            };
            return base + if tail.is_empty() { 0.0 } else { number(Some(&Value { text: tail.into(), ..Default::default() })) };
        }
    }
    number(Some(v))
}

fn mix(a: f64, b: f64, p: f64) -> f64 {
    a + (b - a) * p
}

pub fn ease(name: &str, p: f64) -> f64 {
    let p = p.clamp(0.0, 1.0);
    match name {
        "ease" => bezier(p, 0.25, 0.1, 0.25, 1.0),
        "ease-in" => bezier(p, 0.42, 0.0, 1.0, 1.0),
        "ease-out" => bezier(p, 0.0, 0.0, 0.58, 1.0),
        "ease-in-out" => bezier(p, 0.42, 0.0, 0.58, 1.0),
        "bounce" => {
            let d = 2.75;
            if p < 1.0 / d {
                7.5625 * p * p
            } else if p < 2.0 / d {
                let p = p - 1.5 / d;
                7.5625 * p * p + 0.75
            } else if p < 2.5 / d {
                let p = p - 2.25 / d;
                7.5625 * p * p + 0.9375
            } else {
                let p = p - 2.625 / d;
                7.5625 * p * p + 0.984375
            }
        }
        _ => p,
    }
}

/// CSS cubic-bezier: solve X(t)=p by bisection, then sample Y.
fn bezier(p: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    if p == 0.0 || p == 1.0 {
        return p;
    }
    let s = |t: f64, a: f64, b: f64| {
        let i = 1.0 - t;
        3.0 * i * i * t * a + 3.0 * i * t * t * b + t * t * t
    };
    let (mut lo, mut hi) = (0.0, 1.0);
    for _ in 0..60 {
        let m = (lo + hi) / 2.0;
        if s(m, x1, x2) < p { lo = m } else { hi = m }
    }
    s((lo + hi) / 2.0, y1, y2)
}

/// True while a finite scene still has time left (or is infinite).
pub fn active(scene: &Scene, t: f64) -> bool {
    scene.period > 0.0 && (scene.repeat == 0 || time(t) < time(scene.period * scene.repeat as f64))
}

/// Frame at absolute elapsed seconds, applying period/repeat and `done`.
pub fn frame(scene: &Scene, t: f64) -> State {
    let mut t = if t.is_finite() && t >= 0.0 { time(t) } else { 0.0 };
    let done = !active(scene, t);
    if scene.period > 0.0 {
        if done {
            t = scene.period;
        } else {
            t = time(t % scene.period);
            if t == scene.period {
                t = 0.0;
            }
        }
    }
    let mut s = at(scene, t);
    s.done = done;
    s
}

fn extent(scene: &Scene, a: &Actor) -> (f64, f64) {
    match scene.actors.iter().find(|p| !a.parent.is_empty() && p.name == a.parent) {
        Some(p) => (p.width, p.height),
        None => (scene.width as f64, scene.height as f64),
    }
}

fn outside(scene: &Scene, st: &ActorState, dir: &str) -> (f64, f64) {
    let a = &scene.actors[st.actor];
    let (w, h) = extent(scene, a);
    let (mut x, mut y) = (st.x, st.y);
    match dir {
        "left" => x = -a.width * st.scale,
        "right" => x = w,
        "top" => y = -a.height * st.scale,
        _ => y = h,
    }
    (x, y)
}

/// Scene state at simple-timeline time `t` (clamped to `[0, period]`).
pub fn at(scene: &Scene, t: f64) -> State {
    let t = t.clamp(0.0, scene.period);
    // Quantize time, begin and duration to integer nanoseconds before any subtraction.
    let q = |x: f64| (x * 1e9).round() as i64;
    let t_ns = q(t);
    let idx = |n: &str| scene.actors.iter().position(|a| a.name == n).unwrap();
    let mut st: Vec<ActorState> = scene
        .actors
        .iter()
        .enumerate()
        .map(|(i, a)| {
            let (w, h) = extent(scene, a);
            ActorState { actor: i, x: resolve(&a.x, w, a.width), y: resolve(&a.y, h, a.height), z: a.z, scale: 1.0, opacity: 1.0, reveal: 1.0, rotation: [0.0; 3], transform: g::IDENTITY, color: a.color.clone() }
        })
        .collect();
    let mut order: Vec<usize> = (0..scene.actions.len()).collect();
    order.sort_by(|&a, &b| scene.actions[a].begin.total_cmp(&scene.actions[b].begin));
    let mut init: Vec<(usize, &str)> = Vec::new();
    for i in order {
        let ac = &scene.actions[i];
        let ti = idx(&ac.actor);
        let dir_in = ac.args.get("0").is_some_and(|v| v.text == "in");
        let key = (ti, ac.property.as_str());
        if !init.contains(&key) {
            init.push(key);
            if ac.verb == "fade" && dir_in {
                st[ti].opacity = 0.0;
            }
            if ac.verb == "type" || ac.verb == "wipe" && dir_in {
                st[ti].reveal = 0.0;
            }
            if ac.verb == "slide" && dir_in && t_ns < q(ac.begin) {
                let (x, y) = outside(scene, &st[ti], &ac.args["to"].text);
                (st[ti].x, st[ti].y) = (x, y);
            }
        }
        let (begin_ns, dur_ns) = (q(ac.begin), q(ac.duration));
        if t_ns < begin_ns {
            continue;
        }
        // One float division of exact integers: the linear midpoint is exactly 0.5.
        let elapsed_ns = t_ns - begin_ns;
        let p = if t_ns >= begin_ns + dur_ns || dur_ns <= 0 { 1.0 } else { elapsed_ns as f64 / dur_ns as f64 };
        let e = ease(&ac.ease, p);
        let actor = &scene.actors[ti];
        match ac.verb.as_str() {
            "fade" => st[ti].opacity = if dir_in { e } else { 1.0 - e },
            "move" => {
                let (w, h) = extent(scene, actor);
                let pt = &ac.args["to"].pair;
                st[ti].x = mix(st[ti].x, resolve(&pt[0], w, actor.width), e);
                st[ti].y = mix(st[ti].y, resolve(&pt[1], h, actor.height), e);
            }
            "slide" => {
                let (ex, ey) = outside(scene, &st[ti], &ac.args["to"].text);
                let s = &mut st[ti];
                if dir_in {
                    (s.x, s.y) = (mix(ex, s.x, e), mix(ey, s.y, e));
                } else {
                    (s.x, s.y) = (mix(s.x, ex, e), mix(s.y, ey, e));
                }
            }
            "scale" => st[ti].scale = mix(st[ti].scale, number(ac.args.get("to")), e),
            "color" if e >= 0.5 => st[ti].color = ac.args["to"].text.clone(),
            "type" => {
                let n = crate::checker::glyphs(&actor.text).len() as f64;
                // Exact integer-nanosecond division: floor(elapsed / per_char) clusters.
                let per = (q(number(ac.args.get("per_char"))) as f64).max(1.0);
                st[ti].reveal = if n == 0.0 { 1.0 } else { n.min(((t_ns - begin_ns) as f64 / per).floor()) / n };
            }
            "wipe" => st[ti].reveal = if dir_in { e } else { 1.0 - e },
            "blink" => {
                st[ti].opacity = 1.0;
                if p < 1.0 && ((p * number(ac.args.get("times")) * 2.0).floor() as i64) % 2 == 1 {
                    st[ti].opacity = 0.0;
                }
            }
            "rotate" => {
                for (axis, name) in ["x", "y", "z"].iter().enumerate() {
                    if let Some(v) = ac.args.get(*name) {
                        st[ti].rotation[axis] = mix(st[ti].rotation[axis], number(Some(v)), e);
                    }
                }
            }
            _ => {}
        }
    }
    let mut composed = vec![false; st.len()];
    fn compose(i: usize, scene: &Scene, st: &mut Vec<ActorState>, composed: &mut Vec<bool>) {
        if composed[i] {
            return;
        }
        let a = &scene.actors[st[i].actor];
        let (ax, ay) = match a.attr.get("anchor") {
            Some(v) => (resolve(&v.pair[0], a.width, 0.0), resolve(&v.pair[1], a.height, 0.0)),
            None => (a.width / 2.0, a.height / 2.0),
        };
        let s = &st[i];
        let mut m = g::mul(&g::compose([s.x + ax, -2.0 * (s.y + ay), 0.0], s.rotation, [s.scale; 3]), &g::translation(-ax, 2.0 * ay, 0.0));
        if !a.parent.is_empty() {
            let pi = scene.actors.iter().position(|p| p.name == a.parent).unwrap();
            compose(pi, scene, st, composed);
            let (pm, ps, po, pr) = (st[pi].transform, st[pi].scale, st[pi].opacity, st[pi].reveal);
            m = g::mul(&pm, &m);
            st[i].scale *= ps;
            st[i].opacity *= po;
            st[i].reveal *= pr;
        }
        let o = g::transform(&m, [0.0, 0.0, 0.0, 1.0]);
        let s = &mut st[i];
        s.transform = m;
        (s.x, s.y) = (o[0], -o[1] / 2.0);
        composed[i] = true;
    }
    for i in 0..st.len() {
        compose(i, scene, &mut st, &mut composed);
    }
    State { actors: st, done: false }
}

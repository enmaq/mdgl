//! Semantic checker (SPEC Grammar tables, Time and geometry). Mutates the scene with derived values.
use crate::model::*;
use crate::parse::{decimal, unknown};
use unicode_segmentation::UnicodeSegmentation;

pub const COLORS: [&str; 10] = ["normal", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "accent"];
pub const EASES: [&str; 6] = ["linear", "ease", "ease-in", "ease-out", "ease-in-out", "bounce"];
pub const VERBS: [&str; 9] = ["fade", "move", "scale", "color", "type", "blink", "wipe", "slide", "rotate"];

fn shape_args(kind: &str) -> &'static [&'static str] {
    match kind {
        "text" => &["0", "1"],
        "rect" => &["0", "1", "border", "title"],
        "circle" => &["0"],
        _ => &["size", "style"],
    }
}
fn verb_args(verb: &str) -> &'static [&'static str] {
    match verb {
        "fade" | "wipe" => &["0", "dur", "ease"],
        "move" | "scale" | "color" => &["to", "dur", "ease"],
        "type" => &["per_char"],
        "rotate" => &["x", "y", "z", "dur", "ease"],
        "blink" => &["times", "dur"],
        _ => &["0", "to", "dur", "ease"],
    }
}

/// Round to nanoseconds (SPEC Time).
pub fn time(v: f64) -> f64 {
    if v.abs() > 1e6 { v } else { (v * 1e9).round() / 1e9 }
}

/// Extended grapheme clusters (UAX #29, Unicode 15.0 via `unicode-segmentation` =1.10.1, the
/// reference profile of Go uniseg v0.4.7). Each cluster is represented by its first scalar.
pub fn glyphs(text: &str) -> Vec<char> {
    text.graphemes(true).filter_map(|g| g.chars().next()).collect()
}

type R<T> = Result<T, String>;

fn is_key_reserved(k: &str) -> bool {
    ["camera", "light", "material", "position", "rotation", "threejs"].contains(&k)
}

fn keys(args: &Args, allowed: &[&str], kind: &str) -> R<()> {
    for k in args.keys() {
        if is_key_reserved(k) {
            return Err(format!("{k} is reserved; not yet supported in 0.1"));
        }
        if !allowed.contains(&k.as_str()) {
            if kind.ends_with("argument") {
                let (mut choices, mut valid) = (vec![], vec![]);
                for n in allowed {
                    if let Ok(p) = n.parse::<usize>() {
                        valid.push(format!("positional {}", p + 1));
                    } else {
                        choices.push(*n);
                        valid.push(n.to_string());
                    }
                }
                return Err(format!("{}; valid arguments: {}", unknown(kind, k, &choices), valid.join(", ")));
            }
            return Err(unknown(kind, k, allowed));
        }
    }
    Ok(())
}

fn one_of(v: Option<&Value>, choices: &[&str]) -> bool {
    v.is_some_and(|v| !v.quoted && v.pair.is_empty() && choices.contains(&v.text.as_str()))
}
fn num(v: Option<&Value>) -> R<f64> {
    let v = v.ok_or("expected number")?;
    if v.quoted || !v.pair.is_empty() {
        return Err("expected number".into());
    }
    decimal(&v.text).ok_or_else(|| "expected finite number".into())
}
/// Times accept an optional trailing `s`.
fn secs(v: Option<&Value>) -> R<f64> {
    match v {
        Some(v) if !v.quoted && v.pair.is_empty() => num(Some(&Value { text: v.text.strip_suffix('s').unwrap_or(&v.text).into(), ..Default::default() })),
        _ => num(v),
    }
}
fn integer(v: Option<&Value>, lo: i64, hi: i64, name: &str) -> R<i64> {
    match num(v) {
        Ok(r) if r == r.trunc() && r >= lo as f64 && r <= hi as f64 => Ok(r as i64),
        _ => Err(format!("{name} must be an integer in {lo}..{hi}")),
    }
}
fn dimension(v: Option<&Value>) -> R<f64> {
    match num(v) {
        Ok(r) if r > 0.0 && r <= 200.0 => Ok(r),
        _ => Err("invalid dimension".into()),
    }
}
fn angle(v: &Value) -> R<f64> {
    let t = v.text.as_str();
    let wrap = |s: &str| Value { text: s.into(), pair: v.pair.clone(), quoted: v.quoted };
    if let Some(s) = t.strip_suffix("rad") {
        return Ok(num(Some(&wrap(s)))? * 180.0 / std::f64::consts::PI);
    }
    num(Some(&wrap(t.strip_suffix("deg").unwrap_or(t))))
}
fn coordinate(v: &Value, horizontal: bool) -> R<()> {
    if v.quoted || !v.pair.is_empty() {
        return Err("invalid coordinate".into());
    }
    let t = v.text.as_str();
    if let Some(r) = decimal(t.strip_suffix('%').unwrap_or(t)) {
        return if r.abs() > 10000.0 { Err("coordinate exceeds -10000..10000".into()) } else { Ok(()) };
    }
    let anchors = if horizontal { ["center", "left", "right"] } else { ["center", "top", "bottom"] };
    for a in anchors {
        if t == a {
            return Ok(());
        }
        if let Some(rest) = t.strip_prefix(a).filter(|r| r.starts_with(['+', '-'])) {
            if decimal(rest).is_some_and(|o| o.abs() <= 10000.0) {
                return Ok(());
            }
        }
    }
    Err(format!("invalid coordinate {}", crate::parse::quote(t)))
}
fn validate_text(text: &str) -> R<()> {
    if glyphs(text).len() > 1024 {
        return Err("text exceeds 1024 graphemes".into());
    }
    if text.chars().any(|c| c.is_control() || c == '\u{2028}' || c == '\u{2029}') {
        return Err("text contains a control character".into());
    }
    Ok(())
}

/// Validate a parsed scene, filling derived fields. Returns the first diagnostic.
pub fn check_scene(scene: &mut Scene) -> Result<(), Diag> {
    let sp = scene.pos;
    let fail = |m: String| sp.err(m);
    keys(&scene.attr, &["width", "height", "period", "repeat", "fallback", "fps"], "scene attribute").map_err(&fail)?;
    for req in ["width", "height", "fallback"] {
        if !scene.attr.contains_key(req) {
            return Err(fail(format!("missing scene attribute {req}")));
        }
    }
    scene.width = integer(scene.attr.get("width"), 1, 200, "width").map_err(&fail)? as u32;
    scene.height = integer(scene.attr.get("height"), 1, 60, "height").map_err(&fail)? as u32;
    scene.fps = 30;
    if let Some(v) = scene.attr.get("fps") {
        scene.fps = integer(Some(v), 1, 30, "fps").map_err(&fail)? as u32;
    }
    scene.period = 0.0;
    scene.explicit_period = false;
    scene.repeat = 1;
    if let Some(v) = scene.attr.get("period") {
        scene.explicit_period = true;
        let p = secs(Some(v)).ok().filter(|p| *p > 0.0 && *p <= 60.0).ok_or_else(|| fail("period must be positive and <=60".into()))?;
        scene.period = time(p);
        if scene.period == 0.0 {
            return Err(fail("period rounds to zero at nanosecond precision".into()));
        }
    }
    if let Some(v) = scene.attr.get("repeat") {
        scene.repeat = if v.text == "infinite" && !v.quoted { 0 } else { integer(Some(v), 1, 1000, "repeat").map_err(&fail)? as u32 };
        if scene.repeat != 1 && !scene.explicit_period {
            return Err(fail("repeat requires explicit period".into()));
        }
    }
    let fb = &scene.attr["fallback"];
    scene.fallback = fb.text.clone();
    if fb.quoted || !fb.pair.is_empty() {
        return Err(fail("fallback must be start, end or @time".into()));
    }

    let mut names: Vec<String> = Vec::new();
    for i in 0..scene.actors.len() {
        let a = &mut scene.actors[i];
        let fa = |m: String| a.pos.err(m);
        if names.contains(&a.name) {
            return Err(fa(format!("duplicate actor {}", a.name)));
        }
        names.push(a.name.clone());
        keys(&a.attr, &["color", "parent", "z", "anchor"], "actor attribute").map_err(&fa)?;
        a.color = "normal".into();
        a.parent.clear();
        a.scale = 1.0;
        if let Some(v) = a.attr.get("color") {
            if !one_of(Some(v), &COLORS) {
                return Err(fa(unknown("color", &v.text, &COLORS)));
            }
            a.color = v.text.clone();
        }
        if let Some(v) = a.attr.get("parent") {
            if v.quoted || !v.pair.is_empty() {
                return Err(fa("parent must be an actor identifier".into()));
            }
            a.parent = v.text.clone();
        }
        if let Some(v) = a.attr.get("z") {
            a.z = integer(Some(v), -10000, 10000, "z").map_err(&fa)? as f64;
        }
        let kind = a.kind.clone();
        match kind.as_str() {
            "text" | "rect" | "circle" | "cube" => keys(&a.args, shape_args(&kind), &format!("{kind} argument")).map_err(&fa)?,
            "mesh" | "sphere" | "plane" | "threejs" | "cells" => return Err(fa(format!("{kind} is reserved; not yet supported in 0.1"))),
            _ => return Err(fa(unknown("shape", &kind, &["text", "rect", "circle", "cube"]))),
        }
        match kind.as_str() {
            "text" => {
                let t = a.args.get("0").filter(|t| t.quoted).ok_or_else(|| fa("text requires a quoted string".into()))?;
                a.text = t.text.clone();
                if a.args.get("1").is_some_and(|v| v.text != "big" || v.quoted) {
                    return Err(fa("text style must be big".into()));
                }
                validate_text(&a.text).map_err(&fa)?;
                a.width = glyphs(&a.text).len() as f64;
                a.height = 1.0;
            }
            "rect" => {
                a.width = dimension(a.args.get("0")).map_err(|_| fa("rect width must be positive and <=200".into()))?;
                a.height = dimension(a.args.get("1")).map_err(|_| fa("rect height must be positive and <=200".into()))?;
                if a.args.get("border").is_some_and(|v| !one_of(Some(v), &["round", "square"])) {
                    return Err(fa("border must be round or square".into()));
                }
                if let Some(v) = a.args.get("title") {
                    if !v.quoted {
                        return Err(fa("title requires a quoted string".into()));
                    }
                    a.text = v.text.clone();
                    validate_text(&a.text).map_err(&fa)?;
                }
            }
            "circle" => {
                let r = dimension(a.args.get("0")).ok().filter(|r| *r <= 100.0).ok_or_else(|| fa("circle radius must be positive and <=100".into()))?;
                a.width = r * 2.0;
                a.height = r * 2.0;
            }
            _ => {
                a.width = dimension(a.args.get("size")).map_err(|_| fa("cube size must be positive and <=200".into()))?;
                a.height = a.width;
                if a.args.get("style").is_some_and(|v| !one_of(Some(v), &["wire"])) {
                    return Err(fa("only cube style=wire is supported in 0.1".into()));
                }
            }
        }
        coordinate(&a.x, true).map_err(&fa)?;
        coordinate(&a.y, false).map_err(&fa)?;
        if let Some(v) = a.attr.get("anchor") {
            if v.pair.len() != 2 {
                return Err(fa("anchor requires (x, y)".into()));
            }
            for (axis, c) in v.pair.iter().enumerate() {
                coordinate(c, axis == 0).map_err(&fa)?;
            }
        }
    }
    for a in &scene.actors {
        if !a.parent.is_empty() && !names.contains(&a.parent) {
            return Err(a.pos.err(unknown("parent", &a.parent, &names)));
        }
    }
    let index_of = |n: &str| scene.actors.iter().position(|a| a.name == n);
    for a in &scene.actors {
        let (mut seen, mut cur) = (Vec::new(), a);
        while !cur.parent.is_empty() {
            if seen.contains(&cur.name) {
                return Err(a.pos.err(format!("parent cycle involving {}", a.name)));
            }
            seen.push(cur.name.clone());
            cur = &scene.actors[index_of(&cur.parent).unwrap()];
        }
    }

    for i in 0..scene.actions.len() {
        let kind_text = {
            let ac = &scene.actions[i];
            let idx = index_of(&ac.actor).ok_or_else(|| ac.pos.err(unknown("actor", &ac.actor, &names)))?;
            (scene.actors[idx].kind.clone(), scene.actors[idx].text.clone())
        };
        let ac = &mut scene.actions[i];
        let fa = |m: String| ac.pos.err(m);
        if !VERBS.contains(&ac.verb.as_str()) {
            return Err(fa(unknown("action", &ac.verb, &VERBS)));
        }
        ac.begin = time(ac.begin);
        keys(&ac.args, verb_args(&ac.verb), "action argument").map_err(&fa)?;
        ac.ease = "linear".into();
        match ac.verb.as_str() {
            "fade" | "wipe" if !one_of(ac.args.get("0"), &["in", "out"]) => return Err(fa(format!("{} requires in or out", ac.verb))),
            "slide" => {
                if !one_of(ac.args.get("0"), &["in", "out"]) {
                    return Err(fa("slide requires in or out".into()));
                }
                if !one_of(ac.args.get("to"), &["left", "right", "top", "bottom"]) {
                    return Err(fa("slide to must be left, right, top or bottom".into()));
                }
            }
            "type" if kind_text.0 != "text" => return Err(fa("type requires a text actor".into())),
            "blink" => {
                integer(ac.args.get("times"), 1, 1000, "times").map_err(&fa)?;
            }
            "rotate" => {
                if kind_text.0 != "cube" {
                    return Err(fa("rotate requires a cube actor".into()));
                }
                let mut found = false;
                for axis in ["x", "y", "z"] {
                    if let Some(v) = ac.args.get(axis) {
                        found = true;
                        let a = angle(v).ok().filter(|a| a.abs() <= 10000.0).ok_or_else(|| fa("rotation must be within -10000..10000".into()))?;
                        ac.args.insert(axis.into(), Value { text: a.to_string(), ..Default::default() });
                    }
                }
                if !found {
                    return Err(fa("rotate requires x, y or z".into()));
                }
            }
            _ => {}
        }
        if let Some(v) = ac.args.get("ease") {
            if !one_of(Some(v), &EASES) {
                return Err(fa(unknown("easing", &v.text, &EASES)));
            }
            ac.ease = v.text.clone();
        }
        if ac.verb == "type" {
            let s = secs(ac.args.get("per_char")).ok().filter(|s| *s > 0.0).ok_or_else(|| fa("per_char must be positive".into()))?;
            let s = time(s);
            if s == 0.0 {
                return Err(fa("per_char rounds to zero at nanosecond precision".into()));
            }
            ac.args.insert("per_char".into(), Value { text: s.to_string(), ..Default::default() });
            ac.duration = s * glyphs(&kind_text.1).len() as f64;
        } else {
            ac.duration = secs(ac.args.get("dur")).ok().filter(|d| *d > 0.0).ok_or_else(|| fa("dur must be positive".into()))?;
        }
        ac.property = match ac.verb.as_str() {
            "fade" | "blink" => "opacity",
            "type" | "wipe" => "reveal",
            "move" | "slide" => "position",
            "scale" => "scale",
            "color" => "color",
            _ => "rotation",
        }
        .into();
        match ac.verb.as_str() {
            "move" => {
                let p = ac.args.get("to").map(|v| v.pair.as_slice()).unwrap_or(&[]);
                if p.len() != 2 {
                    return Err(fa("move requires to=(x, y)".into()));
                }
                coordinate(&p[0], true).map_err(&fa)?;
                coordinate(&p[1], false).map_err(&fa)?;
            }
            "scale" if !num(ac.args.get("to")).is_ok_and(|f| f > 0.0 && f <= 16.0) => return Err(fa("scale to must be positive and <=16".into())),
            "color" if !one_of(ac.args.get("to"), &COLORS) => {
                return Err(fa(unknown("color", ac.args.get("to").map_or("", |v| &v.text), &COLORS)));
            }
            _ => {}
        }
        ac.duration = time(ac.duration);
        if ac.duration == 0.0 && ac.verb != "type" {
            return Err(fa("dur rounds to zero at nanosecond precision".into()));
        }
        let end = time(ac.begin + ac.duration);
        if !end.is_finite() || end > 60.0 {
            return Err(fa("action end must be <=60".into()));
        }
        if scene.explicit_period {
            if end > scene.period {
                return Err(fa("action exceeds period".into()));
            }
        } else if end > scene.period {
            scene.period = end;
        }
        let ac = &scene.actions[i];
        for o in &scene.actions[..i] {
            if ac.actor == o.actor && ac.property == o.property && ac.begin < time(o.begin + o.duration) && o.begin < end {
                return Err(ac.pos.err(format!("overlapping {} actions on {}", ac.property, ac.actor)));
            }
        }
    }
    if scene.fallback != "start" && scene.fallback != "end" {
        let Some(rest) = scene.fallback.strip_prefix('@') else {
            return Err(fail("fallback must be start, end or @time".into()));
        };
        if !decimal(rest.strip_suffix('s').unwrap_or(rest)).is_some_and(|t| t >= 0.0 && t <= scene.period) {
            return Err(fail("fallback time must be within period".into()));
        }
    }
    Ok(())
}

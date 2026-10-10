//! MDGL 0.0.1 -- SUBSET limit/header checker. NOT a conformant MDGL implementation.
//!
//! `check` verifies only: input <= 256 KiB, lines <= 16 KiB, scene header with
//! width (1..=200), height (1..=60) and fallback, no unknown/duplicate scene
//! keys, statement order, <= 64 actors, <= 1024 actions. It does NOT parse
//! actor/action bodies, check timing, references, grammar, UTF-8 validity of
//! raw bytes (a `&str` is always UTF-8) or rendering. An empty result means
//! "no limit/header problems found", NOT "valid MDGL". The Go module in
//! `go/` is the reference. Spec: <https://github.com/enmaq/mdgl/blob/main/SPEC.md>

/// A single line:col diagnostic.
#[derive(Debug, PartialEq, Eq)]
pub struct Diag {
    pub line: usize,
    pub col: usize,
    pub message: String,
}

pub const MAX_INPUT: usize = 256 * 1024;
pub const MAX_LINE: usize = 16384;
pub const MAX_ACTORS: usize = 64;
pub const MAX_ACTIONS: usize = 1024;

fn d(line: usize, message: impl Into<String>) -> Vec<Diag> {
    vec![Diag { line, col: 1, message: message.into() }]
}

/// Subset check; an empty vec means "no limit/header problems found".
pub fn check(source: &str) -> Vec<Diag> {
    if source.len() > MAX_INPUT {
        return d(1, "input exceeds 256 KiB");
    }
    let (mut scene, mut action, mut version) = (false, false, false);
    let (mut actors, mut actions) = (0usize, 0usize);
    for (i, line) in source.split('\n').enumerate() {
        let n = i + 1;
        if line.len() > MAX_LINE {
            return d(n, "line exceeds 16 KiB");
        }
        let t = line.trim_matches(|c| c == ' ' || c == '\t' || c == '\r');
        if t.is_empty() || t.starts_with('#') {
            continue;
        }
        let head = if t.starts_with('@') {
            "@"
        } else {
            t.split([' ', '\t']).next().unwrap_or("")
        };
        match head {
            "mdgl" => {
                if scene || version || t[4..].trim() != "0.1" {
                    return d(n, "expected initial mdgl 0.1");
                }
                version = true;
            }
            "scene" => {
                if scene {
                    return d(n, "duplicate scene");
                }
                scene = true;
                let out = scene_header(n, &t[5..]);
                if !out.is_empty() {
                    return out;
                }
            }
            "actor" => {
                if !scene {
                    return d(n, "scene must precede actors");
                }
                if action {
                    return d(n, "actors must precede actions");
                }
                actors += 1;
                if actors > MAX_ACTORS {
                    return d(n, "actor limit 64 exceeded");
                }
            }
            "@" => {
                if !scene {
                    return d(n, "scene must precede actions");
                }
                action = true;
                actions += 1;
                if actions > MAX_ACTIONS {
                    return d(n, "action limit 1024 exceeded");
                }
            }
            _ => return d(n, "unsupported statement (expected mdgl, scene, actor or @)"),
        }
    }
    if !scene {
        return d(1, "missing scene");
    }
    Vec::new()
}

fn scene_header(n: usize, rest: &str) -> Vec<Diag> {
    let mut seen: Vec<(&str, &str)> = Vec::new();
    for tok in rest.split([' ', '\t', '\r']).filter(|s| !s.is_empty()) {
        let (k, v) = match tok.split_once('=') {
            Some((k, v)) if !k.is_empty() && !v.is_empty() => (k, v),
            _ => return d(n, format!("malformed scene attribute {tok:?}")),
        };
        if !["width", "height", "period", "repeat", "fallback", "fps"].contains(&k) {
            return d(n, format!("unknown scene attribute {k:?}"));
        }
        if seen.iter().any(|(sk, _)| *sk == k) {
            return d(n, format!("duplicate scene attribute {k:?}"));
        }
        seen.push((k, v));
    }
    let mut out = Vec::new();
    for key in ["width", "height", "fallback"] {
        if !seen.iter().any(|(k, _)| *k == key) {
            out.push(Diag { line: n, col: 1, message: format!("scene header missing {key}=") });
        }
    }
    if !out.is_empty() {
        return out;
    }
    for (key, max) in [("width", 200u32), ("height", 60)] {
        let v = seen.iter().find(|(k, _)| *k == key).unwrap().1;
        let ok = !v.is_empty()
            && v.bytes().all(|b| b.is_ascii_digit())
            && v.len() <= 9
            && matches!(v.parse::<u32>(), Ok(x) if (1..=max).contains(&x));
        if !ok {
            return d(n, format!("{key} must be an integer 1..{max}"));
        }
    }
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;
    const BASE: &str = "scene width=8 height=1 fallback=end\n";

    fn pad(total: usize) -> String {
        format!("{BASE}{}", "\n".repeat(total - BASE.len()))
    }
    fn actors(n: usize) -> String {
        let mut s = BASE.to_string();
        for i in 0..n {
            s += &format!("actor a{i} = circle(1) at (0, 0)\n");
        }
        s
    }
    fn actions(n: usize) -> String {
        let mut s = format!("{BASE}actor a = text(\"AB\") at (0, 0)\n");
        for i in 0..n {
            s += &format!("@{:.2}: a.move(to=({}, 0), dur=0.01)\n", i as f64 * 0.05, i % 2);
        }
        s
    }

    #[test]
    fn case_table() {
        let line = |n: usize| format!("{BASE}#{}\n", "x".repeat(n - 1));
        let cases: Vec<(&str, String, bool)> = vec![
            ("minimal", BASE.into(), true),
            ("version", format!("mdgl 0.1\n{BASE}"), true),
            ("order", "scene fallback=start height=60 width=200\n".into(), true),
            ("comments", format!("# hi\n\n{BASE}"), true),
            ("empty", "\n".into(), false),
            ("no width", "scene height=1 fallback=end\n".into(), false),
            ("no height", "scene width=8 fallback=end\n".into(), false),
            ("no fallback", "scene width=8 height=1 period=4\n".into(), false),
            ("width 0", "scene width=0 height=1 fallback=end\n".into(), false),
            ("width 201", "scene width=201 height=1 fallback=end\n".into(), false),
            ("height 61", "scene width=8 height=61 fallback=end\n".into(), false),
            ("dup key", "scene width=8 width=9 height=1 fallback=end\n".into(), false),
            ("unknown key", format!("{}bogus=1\n", BASE.trim_end().to_string() + " "), false),
            ("dup scene", format!("{BASE}{BASE}"), false),
            ("actor first", format!("actor a = circle(1) at (0, 0)\n{BASE}"), false),
            ("actor after action", format!("{BASE}@0: a.fade(in, dur=1)\nactor a = circle(1) at (0, 0)\n"), false),
            ("unknown stmt", format!("{BASE}bogus\n"), false),
            ("size 256KiB", pad(262144), true),
            ("size +1", pad(262145), false),
            ("line 16384", line(16384), true),
            ("line 16385", line(16385), false),
            ("64 actors", actors(64), true),
            ("65 actors", actors(65), false),
            ("1024 actions", actions(1024), true),
            ("1025 actions", actions(1025), false),
        ];
        for (name, src, ok) in cases {
            assert_eq!(check(&src).is_empty(), ok, "case {name}: {:?}", check(&src));
        }
    }
}

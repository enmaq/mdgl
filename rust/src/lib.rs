//! MDGL 0.1 parser, checker, pure evaluator, terminal-cell renderer and terminal player.
//!
//! Development tree: not yet in a published release. Grapheme clusters follow UAX #29 and Go uniseg
//! v0.4.7 (Unicode 15.0.0). Spec: <https://github.com/enmaq/mdgl/blob/main/SPEC.md>

mod checker;
mod eval;
mod geometry;
mod model;
mod parse;
mod player;
mod render;
mod width_tables;

pub use checker::{check_scene, glyphs, time, COLORS, EASES, VERBS};
pub use eval::{ease, frame as eval_frame, at as eval_at, ActorState, State};
pub use player::{diff, play, plain, Clock, Outcome, SystemClock};
pub use render::{cell_glyphs, render, Cell, Frame};
pub use model::{Action, Actor, Args, Diag, Pos, Scene, Value};
pub use parse::{parse, MAX_ACTIONS, MAX_ACTORS, MAX_INPUT, MAX_LINE};

/// Parse and check, returning the checked, source-located scene.
pub fn parse_checked(source: &str) -> Result<Scene, Diag> {
    let mut scene = parse(source)?;
    check_scene(&mut scene)?;
    Ok(scene)
}

/// Full parse + check; an empty vec means the source is valid. At most one (the first) diagnostic.
pub fn check(source: &str) -> Vec<Diag> {
    parse_checked(source).err().into_iter().collect()
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

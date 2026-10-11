//! Deterministic clock/writer tests for the terminal player: absolute time, frame boundaries,
//! dirty cells, completion, interrupt and terminal cleanup.
use mdgl::{Cell, Clock, Outcome};
use std::cell::Cell as StdCell;
use std::io::{self, Write};
use std::time::Duration;

/// Scripted clock: `now()` pops the next instant (the last one repeats); sleeps are recorded.
struct Script {
    times: Vec<u64>,
    i: usize,
    slept: Vec<u64>,
}
impl Script {
    fn new(ms: &[u64]) -> Self {
        Self { times: ms.to_vec(), i: 0, slept: vec![] }
    }
}
impl Clock for Script {
    fn now(&mut self) -> Duration {
        let t = self.times[self.i.min(self.times.len() - 1)];
        self.i += 1;
        Duration::from_millis(t)
    }
    fn sleep(&mut self, d: Duration) {
        self.slept.push(d.as_millis() as u64);
    }
}

const FADE: &str = "scene width=4 height=1 period=1 fps=10 fallback=end\nactor a = text(\"AB\") at (0,0)\n@0: a.fade(in, dur=1)\n";

fn scene(src: &str) -> mdgl::Scene {
    mdgl::parse_checked(src).unwrap()
}

#[test]
fn uses_absolute_time_not_tick_count() {
    // The clock jumps 0 -> 450 ms: the second drawn frame must be the t=0.45 frame, and the sleep
    // must end at the next absolute boundary (500 ms), not a fixed 100 ms later.
    let s = scene(FADE);
    let mut clock = Script::new(&[0, 0, 450, 450, 1000]);
    let mut out = Vec::new();
    let r = mdgl::play(&s, &mut out, &mut clock, &|| false).unwrap();
    assert_eq!(r, Outcome::Finished);
    let text = String::from_utf8(out).unwrap();
    let f0 = s.frame_ns(0, 4, 1);
    let f450 = s.frame_ns(450_000_000, 4, 1);
    let expected_second = mdgl::diff(Some(&f0.cells), &f450.cells);
    assert!(!expected_second.is_empty() && text.contains(&expected_second), "second frame is the t=0.45s frame");
    assert_eq!(clock.slept, vec![100, 50], "boundaries at 100 ms and 500 ms");
}

#[test]
fn finite_scene_stops_on_done_and_restores_the_terminal() {
    let s = scene(FADE);
    let mut out = Vec::new();
    let mut clock = Script::new(&[2_000]); // past the end immediately
    assert_eq!(mdgl::play(&s, &mut out, &mut clock, &|| false).unwrap(), Outcome::Finished);
    let t = String::from_utf8(out).unwrap();
    assert!(t.starts_with("\x1b[?25l"), "cursor hidden first");
    assert!(t.contains("\x1b[?2026h") && t.contains("\x1b[?2026l"), "synchronized output");
    assert!(t.ends_with("\x1b[0m\x1b[?25h\x1b[2;1H\n"), "reset, show cursor, park below the stage: {t:?}");
    assert!(clock.slept.is_empty(), "no sleep after the final frame");
}

#[test]
fn infinite_scene_runs_until_interrupted_then_cleans_up() {
    let s = scene("scene width=4 height=1 period=1 repeat=infinite fps=10 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in, dur=1)\n");
    let polls = StdCell::new(0);
    let stop = || {
        polls.set(polls.get() + 1);
        polls.get() > 5
    };
    let mut out = Vec::new();
    let mut clock = Script::new(&[0, 0, 100, 100, 200, 200, 300, 300, 400, 400, 500, 500]);
    assert_eq!(mdgl::play(&s, &mut out, &mut clock, &stop).unwrap(), Outcome::Interrupted);
    assert!(String::from_utf8(out).unwrap().ends_with("\x1b[0m\x1b[?25h\x1b[2;1H\n"));
    assert!(clock.slept.len() >= 4, "it kept animating");
}

#[test]
fn write_error_is_surfaced_and_cleanup_is_attempted() {
    struct Failing {
        calls: usize,
        seen: Vec<u8>,
    }
    impl Write for Failing {
        fn write(&mut self, b: &[u8]) -> io::Result<usize> {
            self.calls += 1;
            if self.calls == 3 {
                return Err(io::Error::other("disk full"));
            }
            self.seen.extend_from_slice(b);
            Ok(b.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    let s = scene(FADE);
    let mut w = Failing { calls: 0, seen: vec![] };
    let r = mdgl::play(&s, &mut w, &mut Script::new(&[0, 100, 200]), &|| false);
    assert_eq!(r.unwrap_err().to_string(), "disk full");
    assert!(String::from_utf8(w.seen).unwrap().contains("\x1b[?25h"), "cursor restored after the failure");
}

#[test]
fn diff_sends_only_changed_cells_with_colours_and_no_raw_controls() {
    let cell = |r: char, fg: &str, bg: &str| Cell { rune: r, fg: fg.into(), bg: bg.into() };
    let a = vec![vec![cell('a', "normal", ""), cell('b', "red", "")]];
    assert_eq!(mdgl::diff(Some(&a), &a), "", "identical frames produce no output");
    let b = vec![vec![cell('a', "normal", ""), cell('b', "#102030", "blue")]];
    let d = mdgl::diff(Some(&a), &b);
    assert_eq!(d, "\x1b[?2026h\x1b[1;2H\x1b[38;2;16;32;48;44mb\x1b[0m\x1b[?2026l");
    let evil = vec![vec![cell('\u{1b}', "normal", "")]];
    let d = mdgl::diff(None, &evil);
    assert!(!d.contains("\u{1b}[31m") && d.contains("m \x1b[0m"), "escape glyph is neutralised: {d:?}");
    assert_eq!(d.matches('\u{1b}').count(), 5, "only our own sequences");
}

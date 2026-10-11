//! Animated terminal playback (SPEC "Limits and API": absolute elapsed time, dirty cells,
//! DEC synchronized output 2026). Pure of I/O policy: the clock, the writer and the stop
//! request are injected, so timing and cleanup are testable without a terminal.
use crate::{Cell, Frame, Scene};
use std::io::{self, Write};
use std::time::Duration;

const SYNC_BEGIN: &str = "\x1b[?2026h";
const SYNC_END: &str = "\x1b[?2026l";
const HIDE_CURSOR: &str = "\x1b[?25l";
const RESTORE: &str = "\x1b[0m\x1b[?25h";

/// Monotonic time source. `now` is elapsed time since playback began.
pub trait Clock {
    fn now(&mut self) -> Duration;
    fn sleep(&mut self, d: Duration);
}

/// Wall-clock implementation on `std::time::Instant` (monotonic).
pub struct SystemClock(std::time::Instant);

impl SystemClock {
    pub fn start() -> Self {
        Self(std::time::Instant::now())
    }
}

impl Clock for SystemClock {
    fn now(&mut self) -> Duration {
        self.0.elapsed()
    }
    fn sleep(&mut self, d: Duration) {
        std::thread::sleep(d);
    }
}

/// Why playback ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// A finite scene reached its end (evaluator `done`).
    Finished,
    /// `stop` returned true (interrupt).
    Interrupted,
}

/// SGR parameters for a cell colour; `""`/`normal` is the terminal default.
fn sgr(color: &str, background: bool) -> String {
    if color.len() == 7 && color.starts_with('#') {
        if let Ok(v) = u32::from_str_radix(&color[1..], 16) {
            return format!("{};2;{};{};{}", if background { 48 } else { 38 }, v >> 16, v >> 8 & 255, v & 255);
        }
    }
    let base = match color {
        "black" => 30,
        "red" => 31,
        "green" => 32,
        "yellow" => 33,
        "blue" => 34,
        "magenta" => 35,
        "cyan" | "accent" => 36,
        "white" => 37,
        _ => 39,
    };
    (base + if background { 10 } else { 0 }).to_string()
}

/// A glyph that is safe to send to a terminal: control characters never reach it as escapes.
fn safe(c: char) -> char {
    if c.is_control() || matches!(c, '\u{2028}' | '\u{2029}') { ' ' } else { c }
}

/// Escape sequences that turn the `previous` grid into `current`; empty when nothing changed.
pub fn diff(previous: Option<&[Vec<Cell>]>, current: &[Vec<Cell>]) -> String {
    let mut body = String::new();
    for (r, row) in current.iter().enumerate() {
        for (c, cell) in row.iter().enumerate() {
            if previous.and_then(|p| p.get(r)).and_then(|p| p.get(c)) == Some(cell) {
                continue;
            }
            body += &format!("\x1b[{};{}H\x1b[{};{}m{}", r + 1, c + 1, sgr(&cell.fg, false), sgr(&cell.bg, true), safe(cell.rune));
        }
    }
    if body.is_empty() { body } else { format!("{SYNC_BEGIN}{body}\x1b[0m{SYNC_END}") }
}

/// Plain text rows, one per line, no escapes (fallback output).
pub fn plain(frame: &Frame) -> String {
    frame.cells.iter().map(|r| r.iter().map(|c| safe(c.rune)).collect::<String>() + "\n").collect()
}

/// Restores the terminal on every exit path, including early returns and write errors.
struct Restore<'a, W: Write> {
    out: &'a mut W,
    rows: usize,
}

impl<W: Write> Drop for Restore<'_, W> {
    fn drop(&mut self) {
        // Best effort: if the writer is already broken there is nothing more to do.
        let _ = write!(self.out, "{SYNC_END}{RESTORE}\x1b[{};1H\n", self.rows + 1);
        let _ = self.out.flush();
    }
}

/// Play `scene` to `out` using absolute elapsed time from `clock`, at the scene's fps.
///
/// Each iteration samples `clock.now()` once, renders the pure frame for that instant and writes
/// only changed cells; frames are never advanced by counting ticks, so dropped frames and slow
/// writers cannot skew the animation. Returns after the frame whose `done` is true, or as soon
/// as `stop()` is observed. The cursor is hidden for the duration and always restored.
pub fn play<W: Write>(scene: &Scene, out: &mut W, clock: &mut dyn Clock, stop: &dyn Fn() -> bool) -> io::Result<Outcome> {
    let (w, h) = (scene.width as usize, scene.height as usize);
    out.write_all(HIDE_CURSOR.as_bytes())?;
    let guard = Restore { out, rows: h };
    let interval_ns = 1_000_000_000u64 / scene.fps.max(1) as u64;
    let mut previous: Option<Frame> = None;
    let outcome = loop {
        if stop() {
            break Outcome::Interrupted;
        }
        let ns = clock.now().as_nanos().min(u64::MAX as u128) as u64;
        let frame = scene.frame_ns(ns, w, h);
        let patch = diff(previous.as_ref().map(|f| f.cells.as_slice()), &frame.cells);
        guard.out.write_all(patch.as_bytes())?;
        guard.out.flush()?;
        let done = frame.done;
        previous = Some(frame);
        if done {
            break Outcome::Finished;
        }
        // Sleep to the next absolute frame boundary, not for a fixed delta.
        let next = (ns / interval_ns + 1) * interval_ns;
        let after = clock.now().as_nanos().min(u64::MAX as u128) as u64;
        if next > after {
            clock.sleep(Duration::from_nanos(next - after));
        }
    };
    Ok(outcome)
}

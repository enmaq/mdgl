//! Terminal-cell renderer: braille 2x4 dots, RGB source-over, painter order by integer `z`.
use crate::eval::{self, ActorState, State};
use crate::geometry::{self as g, Mat4};
use crate::model::Scene;
use unicode_segmentation::UnicodeSegmentation;

/// One terminal cell: glyph, foreground (named colour or `#rrggbb`) and background ("" = default black).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cell {
    pub rune: char,
    pub fg: String,
    pub bg: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Frame {
    pub width: usize,
    pub height: usize,
    pub cells: Vec<Vec<Cell>>,
    /// Meaningful for timed frames; fallback frames report `false`.
    pub done: bool,
}

impl Frame {
    /// Glyph rows, the legacy conformance format.
    pub fn lines(&self) -> Vec<String> {
        self.cells.iter().map(|r| r.iter().map(|c| c.rune).collect()).collect()
    }
}

fn lookup<T: Copy>(t: &[(u32, u32, T)], c: char) -> Option<T> {
    let c = c as u32;
    t.binary_search_by(|&(lo, hi, _)| if hi < c { std::cmp::Ordering::Less } else if lo > c { std::cmp::Ordering::Greater } else { std::cmp::Ordering::Equal })
        .ok()
        .map(|i| t[i].2)
}

fn in_ranges(t: &[(u32, u32)], c: char) -> bool {
    lookup(&t.iter().map(|&(a, b)| (a, b, ())).collect::<Vec<_>>(), c).is_some()
}

fn rune_width(c: char, prop: u8) -> usize {
    use crate::width_tables as w;
    match prop {
        w::CONTROL | w::CR | w::LF | w::EXTEND | w::ZWJ => 0,
        w::REGIONALINDICATOR => 2,
        w::EXTENDEDPICTOGRAPHIC => 1 + usize::from(in_ranges(w::EMOJI_PRESENTATION, c)),
        _ => match (c, lookup(w::EAST_ASIAN, c)) {
            ('\u{2e3a}', _) => 3,
            ('\u{2e3b}', _) => 4,
            (_, Some(b'W' | b'F')) => 2,
            _ => 1,
        },
    }
}

/// Monospace cell width of one grapheme cluster, following Go uniseg v0.4.7 (Unicode 15.0.0).
fn cluster_width(g: &str) -> usize {
    use crate::width_tables as w;
    let mut it = g.chars();
    let Some(c0) = it.next() else { return 0 };
    let first = lookup(w::GRAPHEME, c0).unwrap_or(w::GB_OTHER);
    let mut width = rune_width(c0, first);
    for c in it {
        if first == w::EXTENDEDPICTOGRAPHIC {
            match c {
                '\u{FE0E}' => width = 1,
                '\u{FE0F}' => width = 2,
                _ => {}
            }
        } else if first != w::REGIONALINDICATOR && first != w::L {
            width += rune_width(c, lookup(w::GRAPHEME, c).unwrap_or(w::GB_OTHER));
        }
    }
    width
}

/// Terminal glyph per grapheme cluster (SPEC Cells): the first non-mark scalar; clusters wider than
/// one cell become U+FFFD. Cluster width and marks use Unicode 15.0.0 data (see `width_tables`).
pub fn cell_glyphs(text: &str) -> Vec<char> {
    text.graphemes(true)
        .map(|g| {
            if cluster_width(g) > 1 {
                '\u{FFFD}'
            } else {
                g.chars().find(|&c| c != '\u{200d}' && !in_ranges(crate::width_tables::MARKS, c)).unwrap_or(' ')
            }
        })
        .collect()
}

fn rgb(color: &str, background: bool) -> [f64; 3] {
    let v: u32 = match color {
        "black" => 0,
        "red" => 0xff0000,
        "green" => 0x00ff00,
        "yellow" => 0xffff00,
        "blue" => 0x0000ff,
        "magenta" => 0xff00ff,
        "cyan" | "accent" => 0x00ffff,
        "white" => 0xffffff,
        c if c.len() == 7 && c.starts_with('#') => u32::from_str_radix(&c[1..], 16).unwrap_or(if background { 0 } else { 0xffffff }),
        _ if background => 0,
        _ => 0xffffff,
    };
    [(v >> 16) as f64, (v >> 8 & 255) as f64, (v & 255) as f64]
}

fn over(dest: &Cell, glyph: char, color: &str, opacity: f64) -> Cell {
    let o = opacity.clamp(0.0, 1.0);
    if o == 0.0 {
        return dest.clone();
    }
    if o == 1.0 {
        return Cell { rune: glyph, fg: color.into(), bg: dest.bg.clone() };
    }
    let below = if dest.rune == ' ' { rgb(&dest.bg, true) } else { rgb(&dest.fg, false) };
    let f = rgb(color, false);
    let c: Vec<u32> = (0..3).map(|i| (f[i] * o + below[i] * (1.0 - o)).round() as u32).collect();
    Cell { rune: glyph, fg: format!("#{:02x}{:02x}{:02x}", c[0], c[1], c[2]), bg: dest.bg.clone() }
}

type Dots = Vec<Vec<bool>>;

fn line(dots: &mut Dots, mut sx: f64, mut sy: f64, mut ex: f64, mut ey: f64) {
    let q = |v: f64| (v * 1e9).round() / 1e9;
    (sx, sy, ex, ey) = (q(sx), q(sy), q(ex), q(ey));
    let (w, h) = ((dots[0].len() - 1) as f64, (dots.len() - 1) as f64);
    let (dx, dy) = (ex - sx, ey - sy);
    let (mut lo, mut hi) = (0.0f64, 1.0f64);
    for (dir, dist) in [(-dx, sx), (dx, w - sx), (-dy, sy), (dy, h - sy)] {
        if dir == 0.0 {
            if dist < 0.0 {
                return;
            }
            continue;
        }
        let r = dist / dir;
        if dir < 0.0 { lo = lo.max(r) } else { hi = hi.min(r) }
        if lo > hi {
            return;
        }
    }
    let (cx, cy) = (sx + lo * dx, sy + lo * dy);
    (ex, ey) = (sx + hi * dx, sy + hi * dy);
    let steps = (ex - cx).abs().max((ey - cy).abs()).ceil().min(800.0) as i64;
    let steps = steps.max(1);
    for s in 0..=steps {
        let p = s as f64 / steps as f64;
        let (hx, vy) = ((cx + (ex - cx) * p).round(), (cy + (ey - cy) * p).round());
        if vy >= 0.0 && (vy as usize) < dots.len() && hx >= 0.0 && (hx as usize) < dots[0].len() {
            dots[vy as usize][hx as usize] = true;
        }
    }
}

fn paint_text(grid: &mut [Vec<Cell>], st: &ActorState, glyphs: &[char], ox: f64, max_w: f64) {
    let limit = glyphs.len().min((max_w * st.reveal + 1e-9).floor() as usize);
    for (i, &gl) in glyphs.iter().take(limit).enumerate() {
        let p = g::transform(&st.transform, [ox + i as f64, 0.0, 0.0, 1.0]);
        let (h, v) = (p[0].round(), (-p[1] / 2.0).round());
        if h < 0.0 || v < 0.0 || v >= grid.len() as f64 || h >= grid[0].len() as f64 {
            continue;
        }
        if gl != ' ' {
            let c = &mut grid[v as usize][h as usize];
            *c = over(c, gl, &st.color, st.opacity);
        }
    }
}

fn cube(dots: &mut Dots, st: &ActorState, size: f64) {
    let world: &Mat4 = &st.transform;
    let center = g::transform(world, [size / 2.0, -size, 0.0, 1.0]);
    let view = g::translation(-center[0], -center[1], -3.0 * size);
    let proj = g::perspective(50.0, size / (2.0 * size), 0.1, 1000.0);
    let m = g::mul(&g::mul(&proj, &view), world);
    let corner = |i: usize| {
        let s = |bit: usize| if i & bit != 0 { 0.5 } else { -0.5 };
        g::transform(&m, [size / 2.0 + s(1) * size, -size + s(2) * size, s(4) * size, 1.0])
    };
    let corners: Vec<_> = (0..8).map(corner).collect();
    let (ox, oy) = (center[0] - size / 2.0, -center[1] / 2.0 - size / 2.0);
    for i in 0..8 {
        for bit in [1, 2, 4] {
            let o = i ^ bit;
            if o > i {
                if let Some((s, e)) = g::clip(corners[i], corners[o]) {
                    let (sx, sy) = g::viewport(s, size, size);
                    let (ex, ey) = g::viewport(e, size, size);
                    line(dots, (ox + sx) * 2.0 - 0.5, (oy + sy) * 4.0 - 0.5, (ox + ex) * 2.0 - 0.5, (oy + ey) * 4.0 - 0.5);
                }
            }
        }
    }
}

/// Render a state to a `cols` x `rows` grid.
pub fn render(scene: &Scene, state: &State, cols: usize, rows: usize) -> Vec<Vec<Cell>> {
    let (cols, rows) = (cols.min(200), rows.min(60));
    let blank = Cell { rune: ' ', fg: "normal".into(), bg: String::new() };
    let mut grid = vec![vec![blank; cols]; rows];
    if rows == 0 || cols == 0 {
        return grid;
    }
    let mut actors: Vec<&ActorState> = state.actors.iter().collect();
    actors.sort_by(|a, b| a.z.total_cmp(&b.z));
    for st in actors {
        let a = &scene.actors[st.actor];
        if st.opacity <= 0.0 || st.reveal <= 0.0 {
            continue;
        }
        if a.kind == "text" {
            paint_text(&mut grid, st, &cell_glyphs(&a.text), 0.0, a.width);
            continue;
        }
        let mut dots: Dots = vec![vec![false; cols * 2]; rows * 4];
        let (w, h) = (a.width, a.height);
        let (last_x, last_y) = ((w * 2.0 - 1.0).max(0.0), (h * 4.0 - 1.0).max(0.0));
        let stage = g::mul(&g::ortho(0.0, cols as f64, -2.0 * rows as f64, 0.0, -1000.0, 1000.0), &st.transform);
        let seg = |dots: &mut Dots, sx: f64, sy: f64, ex: f64, ey: f64| {
            let s = g::transform(&stage, [sx / 2.0, -sy / 2.0, 0.0, 1.0]);
            let e = g::transform(&stage, [ex / 2.0, -ey / 2.0, 0.0, 1.0]);
            if let Some((s, e)) = g::clip(s, e) {
                let (sx, sy) = g::viewport(s, cols as f64 * 2.0, rows as f64 * 4.0);
                let (ex, ey) = g::viewport(e, cols as f64 * 2.0, rows as f64 * 4.0);
                line(dots, sx, sy, ex, ey);
            }
        };
        match a.kind.as_str() {
            "rect" => {
                seg(&mut dots, 0.0, 0.0, last_x, 0.0);
                seg(&mut dots, last_x, 0.0, last_x, last_y);
                seg(&mut dots, last_x, last_y, 0.0, last_y);
                seg(&mut dots, 0.0, last_y, 0.0, 0.0);
            }
            "circle" => {
                let (cx, cy, rx, ry) = (last_x / 2.0, last_y / 2.0, last_x / 2.0, last_y / 2.0);
                let (mut px, mut py) = (cx + rx, cy);
                for s in 1..=720 {
                    let ang = s as f64 * std::f64::consts::PI / 360.0;
                    let (nx, ny) = (cx + rx * ang.cos(), cy + ry * ang.sin());
                    seg(&mut dots, px, py, nx, ny);
                    (px, py) = (nx, ny);
                }
            }
            _ => cube(&mut dots, st, w),
        }
        for (row, line_cells) in grid.iter_mut().enumerate() {
            for (col, cell) in line_cells.iter_mut().enumerate() {
                let mut mask = 0u32;
                for v in 0..4 {
                    for hz in 0..2 {
                        if dots[row * 4 + v][col * 2 + hz] {
                            mask |= 1 << [[0, 3], [1, 4], [2, 5], [6, 7]][v][hz];
                        }
                    }
                }
                if mask != 0 && (st.reveal >= 1.0 || col as f64 + 0.5 <= st.x + w * st.scale * st.reveal) {
                    *cell = over(cell, char::from_u32(0x2800 + mask).unwrap(), &st.color, st.opacity);
                }
            }
        }
        if a.kind == "rect" && !a.text.is_empty() {
            paint_text(&mut grid, st, &cell_glyphs(&a.text), 1.0, (a.width - 2.0).max(0.0));
        }
    }
    grid
}

impl Scene {
    fn frame_of(&self, state: State, cols: usize, rows: usize, done: bool) -> Frame {
        let (w, h) = (cols.min(self.width as usize), rows.min(self.height as usize));
        Frame { width: w, height: h, cells: render(self, &state, w, h), done }
    }
    /// Timed frame at absolute elapsed seconds; pure, so seeking is order independent.
    pub fn frame(&self, seconds: f64, cols: usize, rows: usize) -> Frame {
        let s = eval::frame(self, seconds);
        let done = s.done;
        self.frame_of(s, cols, rows, done)
    }
    /// Frame at integer nanoseconds (the wire-protocol time unit).
    pub fn frame_ns(&self, ns: u64, cols: usize, rows: usize) -> Frame {
        self.frame(ns as f64 / 1e9, cols, rows)
    }
    /// Fallback frame (`start`, `end` or `@t`), ignoring repeat.
    pub fn fallback_frame(&self, cols: usize, rows: usize) -> Frame {
        let t = match self.fallback.as_str() {
            "start" => 0.0,
            "end" => self.period,
            f => f.trim_start_matches('@').trim_end_matches('s').parse().unwrap_or(0.0),
        };
        self.frame_of(eval::at(self, t), cols, rows, false)
    }
}

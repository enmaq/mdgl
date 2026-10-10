//! NDJSON conformance adapter for observable protocol v1 (conformance/PROTOCOL.md).
//! One request per line on stdin, exactly one response line per request on stdout. Stateless.
use std::io::{self, BufRead, Write};

const MAX_LINE: usize = 2_097_152;
const MAX_DEPTH: usize = 64;
const MAX_NS: u64 = (1 << 53) - 1;

#[allow(dead_code)]
enum J {
    Null,
    Bool(bool),
    /// Original number token, validated as RFC 8259 syntax.
    Num(String),
    Str(String),
    Arr(Vec<J>),
    Obj(Vec<(String, J)>),
}

struct P<'a> {
    b: &'a [u8],
    i: usize,
}

impl P<'_> {
    fn ws(&mut self) {
        while matches!(self.b.get(self.i), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.i += 1;
        }
    }
    fn lit(&mut self, s: &str, v: J) -> Option<J> {
        self.b[self.i..].starts_with(s.as_bytes()).then(|| {
            self.i += s.len();
            v
        })
    }
    fn value(&mut self, depth: usize) -> Option<J> {
        if depth > MAX_DEPTH {
            return None;
        }
        self.ws();
        match *self.b.get(self.i)? {
            b'n' => self.lit("null", J::Null),
            b't' => self.lit("true", J::Bool(true)),
            b'f' => self.lit("false", J::Bool(false)),
            b'"' => self.string().map(J::Str),
            b'[' => {
                self.i += 1;
                let mut v = Vec::new();
                self.ws();
                if self.b.get(self.i) == Some(&b']') {
                    self.i += 1;
                    return Some(J::Arr(v));
                }
                loop {
                    v.push(self.value(depth + 1)?);
                    self.ws();
                    match self.b.get(self.i)? {
                        b',' => self.i += 1,
                        b']' => {
                            self.i += 1;
                            return Some(J::Arr(v));
                        }
                        _ => return None,
                    }
                }
            }
            b'{' => {
                self.i += 1;
                let mut v = Vec::new();
                self.ws();
                if self.b.get(self.i) == Some(&b'}') {
                    self.i += 1;
                    return Some(J::Obj(v));
                }
                loop {
                    self.ws();
                    let k = self.string()?;
                    self.ws();
                    if self.b.get(self.i) != Some(&b':') {
                        return None;
                    }
                    self.i += 1;
                    v.push((k, self.value(depth + 1)?));
                    self.ws();
                    match self.b.get(self.i)? {
                        b',' => self.i += 1,
                        b'}' => {
                            self.i += 1;
                            return Some(J::Obj(v));
                        }
                        _ => return None,
                    }
                }
            }
            b'-' | b'0'..=b'9' => self.number(),
            _ => None,
        }
    }
    fn digits(&mut self) -> usize {
        let s = self.i;
        while self.b.get(self.i).is_some_and(u8::is_ascii_digit) {
            self.i += 1;
        }
        self.i - s
    }
    fn number(&mut self) -> Option<J> {
        let s = self.i;
        if self.b[self.i] == b'-' {
            self.i += 1;
        }
        match self.b.get(self.i)? {
            b'0' => self.i += 1,
            b'1'..=b'9' => {
                self.digits();
            }
            _ => return None,
        }
        if self.b.get(self.i) == Some(&b'.') {
            self.i += 1;
            if self.digits() == 0 {
                return None;
            }
        }
        if matches!(self.b.get(self.i), Some(b'e' | b'E')) {
            self.i += 1;
            if matches!(self.b.get(self.i), Some(b'+' | b'-')) {
                self.i += 1;
            }
            if self.digits() == 0 {
                return None;
            }
        }
        Some(J::Num(String::from_utf8_lossy(&self.b[s..self.i]).into()))
    }
    fn hex4(&mut self) -> Option<u32> {
        let h = std::str::from_utf8(self.b.get(self.i..self.i + 4)?).ok()?;
        if !h.bytes().all(|c| c.is_ascii_hexdigit()) {
            return None;
        }
        self.i += 4;
        u32::from_str_radix(h, 16).ok()
    }
    fn string(&mut self) -> Option<String> {
        if self.b.get(self.i) != Some(&b'"') {
            return None;
        }
        self.i += 1;
        let mut out = String::new();
        loop {
            let c = *self.b.get(self.i)?;
            self.i += 1;
            match c {
                b'"' => return Some(out),
                0..=0x1f => return None,
                b'\\' => {
                    let e = *self.b.get(self.i)?;
                    self.i += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\x08'),
                        b'f' => out.push('\x0c'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let hi = self.hex4()?;
                            let cp = match hi {
                                0xD800..=0xDBFF => {
                                    if !self.b[self.i..].starts_with(b"\\u") {
                                        return None; // lone high surrogate
                                    }
                                    self.i += 2;
                                    let lo = self.hex4()?;
                                    if !(0xDC00..=0xDFFF).contains(&lo) {
                                        return None;
                                    }
                                    0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00)
                                }
                                0xDC00..=0xDFFF => return None, // lone low surrogate
                                _ => hi,
                            };
                            out.push(char::from_u32(cp)?);
                        }
                        _ => return None,
                    }
                }
                _ => {
                    // The line was validated as UTF-8 up front; copy the full scalar.
                    let start = self.i - 1;
                    let mut end = self.i;
                    while self.b.get(end).is_some_and(|b| b & 0xC0 == 0x80) {
                        end += 1;
                    }
                    out.push_str(std::str::from_utf8(&self.b[start..end]).ok()?);
                    self.i = end;
                }
            }
        }
    }
}

/// Exact mathematical integer check for a JSON number token, within `0..=max`. No float parsing.
fn exact_int(tok: &str, max: u64) -> Option<u64> {
    let (neg, t) = tok.strip_prefix('-').map_or((false, tok), |r| (true, r));
    let (mant, exp) = t.split_once(['e', 'E']).map_or((t, "0"), |(m, e)| (m, e));
    let exp: i64 = exp.trim_start_matches('+').parse().unwrap_or(if exp.starts_with('-') { i64::MIN / 2 } else { i64::MAX / 2 });
    let (w, f) = mant.split_once('.').unwrap_or((mant, ""));
    let digits: String = format!("{w}{f}");
    let digits = digits.trim_start_matches('0');
    if digits.is_empty() {
        return Some(0); // zero (including -0 and 0e999): not negative
    }
    if neg {
        return None;
    }
    // value = digits * 10^(exp - len(f)); strip trailing zeros of the integer mantissa.
    let mut shift = exp - f.len() as i64;
    let d = digits.trim_end_matches('0');
    shift += (digits.len() - d.len()) as i64;
    if shift < 0 {
        return None; // non-zero fractional part
    }
    if d.len() as i64 + shift > 16 {
        return None; // beyond 2^53-1 magnitude (max has 16 digits)
    }
    let mut v: u64 = d.parse().ok()?;
    for _ in 0..shift {
        v = v.checked_mul(10)?;
    }
    (v <= max).then_some(v)
}

fn get<'a>(o: &'a [(String, J)], k: &str) -> Option<&'a J> {
    o.iter().rev().find(|(n, _)| n == k).map(|(_, v)| v)
}

fn esc(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    o.push('"');
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

fn fail(id: Option<&str>, code: &str, msg: &str) -> String {
    format!("{{\"v\":1,\"id\":{},\"ok\":false,\"error\":{{\"code\":\"{code}\",\"message\":{}}}}}", id.map_or("null".into(), esc), esc(msg))
}

fn diags(d: &[mdgl::Diag]) -> String {
    let items: Vec<String> = d.iter().map(|d| format!("{{\"line\":{},\"col\":{},\"message\":{}}}", d.line, d.col, esc(&d.message))).collect();
    format!("[{}]", items.join(","))
}

fn handle(line: &[u8]) -> String {
    let Ok(text) = std::str::from_utf8(line) else { return fail(None, "bad_request", "request is not UTF-8") };
    if text.trim_matches([' ', '\t', '\r']).is_empty() {
        return fail(None, "bad_request", "blank line");
    }
    let mut p = P { b: text.as_bytes(), i: 0 };
    let root = p.value(0);
    p.ws();
    let Some(J::Obj(o)) = root.filter(|_| p.i == p.b.len()) else { return fail(None, "bad_request", "request is not a JSON object") };
    let id = match get(&o, "id") {
        Some(J::Str(s)) => Some(s.as_str()),
        _ => None,
    };
    match get(&o, "v") {
        Some(J::Num(n)) => match exact_int(n, u64::MAX) {
            Some(1) => {}
            Some(_) => return fail(id, "unsupported_version", "protocol version is not supported"),
            None if exact_int(n.trim_start_matches('-'), u64::MAX).is_some() || !n.contains(['.', 'e', 'E']) => return fail(id, "unsupported_version", "protocol version is not supported"),
            None => return fail(id, "bad_request", "v must be an integer"),
        },
        _ => return fail(id, "bad_request", "v must be an integer"),
    }
    let op = match get(&o, "op") {
        Some(J::Str(s)) if s == "check" || s == "frame" => s.as_str(),
        _ => return fail(id, "bad_request", "op must be \"check\" or \"frame\""),
    };
    let Some(id) = id else { return fail(None, "bad_request", "id must be a string") };
    let Some(J::Str(source)) = get(&o, "source") else { return fail(Some(id), "bad_request", "source must be a string") };
    if op == "check" {
        let d: Vec<_> = mdgl::check(source);
        return format!("{{\"v\":1,\"id\":{},\"ok\":true,\"diagnostics\":{}}}", esc(id), diags(&d));
    }
    let fallback = match get(&o, "fallback") {
        None | Some(J::Null) => false,
        Some(J::Bool(b)) => *b,
        _ => return fail(Some(id), "bad_request", "fallback must be a boolean"),
    };
    let dim = |k: &str, max: u64| match get(&o, k) {
        Some(J::Num(n)) => exact_int(n, max).filter(|v| *v >= 1),
        _ => None,
    };
    let (Some(w), Some(h)) = (dim("width", 200), dim("height", 60)) else { return fail(Some(id), "bad_request", "width/height out of range") };
    let ns = if fallback {
        0
    } else {
        match get(&o, "time_ns") {
            Some(J::Num(n)) => match exact_int(n, MAX_NS) {
                Some(v) => v,
                None => return fail(Some(id), "bad_request", "time_ns must be a mathematical integer in 0..2^53-1"),
            },
            _ => return fail(Some(id), "bad_request", "time_ns must be a mathematical integer in 0..2^53-1"),
        }
    };
    let scene = match mdgl::parse_checked(source) {
        Ok(s) => s,
        Err(d) => return format!("{{\"v\":1,\"id\":{},\"ok\":false,\"error\":{{\"code\":\"invalid_source\",\"message\":\"source has diagnostics\",\"diagnostics\":{}}}}}", esc(id), diags(&[d])),
    };
    let f = if fallback { scene.fallback_frame(w as usize, h as usize) } else { scene.frame_ns(ns, w as usize, h as usize) };
    let rows: Vec<String> = f
        .cells
        .iter()
        .map(|r| {
            let cs: Vec<String> = r.iter().map(|c| format!("{{\"r\":{},\"fg\":{},\"bg\":{}}}", esc(&c.rune.to_string()), esc(&c.fg), esc(&c.bg))).collect();
            format!("[{}]", cs.join(","))
        })
        .collect();
    let done = if fallback { String::new() } else { format!(",\"done\":{}", f.done) };
    format!("{{\"v\":1,\"id\":{},\"ok\":true,\"width\":{},\"height\":{},\"cells\":[{}]{done}}}", esc(id), f.width, f.height, rows.join(","))
}

fn main() {
    let (stdin, stdout) = (io::stdin(), io::stdout());
    let (mut r, mut w) = (stdin.lock(), io::BufWriter::new(stdout.lock()));
    let mut buf: Vec<u8> = Vec::new();
    loop {
        buf.clear();
        let (mut too_long, mut eof, mut got) = (false, false, false);
        loop {
            let chunk = match r.fill_buf() {
                Ok(c) => c,
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => return,
            };
            if chunk.is_empty() {
                eof = true;
                break;
            }
            got = true;
            let (take, nl) = match chunk.iter().position(|&b| b == b'\n') {
                Some(p) => (p + 1, true),
                None => (chunk.len(), false),
            };
            if !too_long {
                let body = if nl { take - 1 } else { take };
                if buf.len() + body > MAX_LINE {
                    too_long = true;
                } else {
                    buf.extend_from_slice(&chunk[..body]);
                }
            }
            r.consume(take);
            if nl {
                break;
            }
        }
        if eof && !got {
            return;
        }
        let out = if too_long {
            fail(None, "bad_request", "request line exceeds 2097152 bytes")
        } else {
            std::panic::catch_unwind(|| handle(&buf)).unwrap_or_else(|_| fail(None, "internal", "adapter error"))
        };
        if writeln!(w, "{out}").and_then(|_| w.flush()).is_err() || eof {
            return;
        }
    }
}

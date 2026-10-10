//! Lexer and statement parser (SPEC Grammar). Columns are UTF-8 byte offsets.
use crate::model::*;

pub const MAX_INPUT: usize = 256 * 1024;
pub const MAX_LINE: usize = 16384;
pub const MAX_ACTORS: usize = 64;
pub const MAX_ACTIONS: usize = 1024;

struct Token {
    text: String,
    col: usize,
    quoted: bool,
}

struct Reader {
    tokens: Vec<Token>,
    offset: usize,
    pos: Pos,
}

/// Go-style `%q` for diagnostics.
pub(crate) fn quote(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\x07' => o.push_str("\\a"),
            '\x08' => o.push_str("\\b"),
            '\x0c' => o.push_str("\\f"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            '\x0b' => o.push_str("\\v"),
            c if (c as u32) < 0x20 || c as u32 == 0x7f => o.push_str(&format!("\\x{:02x}", c as u32)),
            c if c.is_control() || matches!(c, '\u{a0}' | '\u{ad}' | '\u{2028}' | '\u{2029}') => {
                o.push_str(&format!("\\u{:04x}", c as u32))
            }
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

/// Interpret a Go double-quoted string literal (`lit` includes the quotes).
fn unquote(lit: &str) -> Option<String> {
    let b = lit.as_bytes();
    let inner = &b[1..b.len() - 1];
    let mut out: Vec<u8> = Vec::new();
    let mut i = 0;
    let hex = |s: &[u8]| -> Option<u32> {
        let t = std::str::from_utf8(s).ok()?;
        if t.bytes().all(|c| c.is_ascii_hexdigit()) { u32::from_str_radix(t, 16).ok() } else { None }
    };
    while i < inner.len() {
        let c = inner[i];
        if c == b'\n' || c == b'"' {
            return None;
        }
        if c != b'\\' {
            out.push(c);
            i += 1;
            continue;
        }
        i += 1;
        let e = *inner.get(i)?;
        i += 1;
        match e {
            b'a' => out.push(7),
            b'b' => out.push(8),
            b'f' => out.push(12),
            b'n' => out.push(b'\n'),
            b'r' => out.push(b'\r'),
            b't' => out.push(b'\t'),
            b'v' => out.push(11),
            b'\\' => out.push(b'\\'),
            b'"' => out.push(b'"'),
            b'x' => {
                out.push(hex(inner.get(i..i + 2)?)? as u8);
                i += 2;
            }
            b'u' | b'U' => {
                let n = if e == b'u' { 4 } else { 8 };
                let ch = char::from_u32(hex(inner.get(i..i + n)?)?)?;
                out.extend_from_slice(ch.encode_utf8(&mut [0; 4]).as_bytes());
                i += n;
            }
            b'0'..=b'7' => {
                let d = inner.get(i..i + 2)?;
                if !d.iter().all(|c| (b'0'..=b'7').contains(c)) {
                    return None;
                }
                let v = ((e - b'0') as u32) << 6 | ((d[0] - b'0') as u32) << 3 | (d[1] - b'0') as u32;
                if v > 255 {
                    return None;
                }
                out.push(v as u8);
                i += 2;
            }
            _ => return None,
        }
    }
    // Go strings may carry invalid UTF-8 from \xNN; Rust Strings cannot (documented gap).
    String::from_utf8(out).ok()
}

fn lex(line: &str, ln: usize) -> Result<Vec<Token>, Diag> {
    let b = line.as_bytes();
    let (letter, digit) = (|c: u8| c.is_ascii_alphabetic() || c == b'_', |c: u8| c.is_ascii_digit());
    let mut out = Vec::new();
    let mut o = 0;
    while o < b.len() {
        let c = b[o];
        if matches!(c, b' ' | b'\t' | b'\r') {
            o += 1;
            continue;
        }
        let start = o;
        let at = Pos { line: ln, col: start + 1 };
        if c == b'"' {
            o += 1;
            let mut closed = false;
            while o < b.len() {
                if b[o] == b'\\' {
                    o += 2;
                    continue;
                }
                o += 1;
                if b[o - 1] == b'"' {
                    closed = true;
                    break;
                }
            }
            if !closed || o > b.len() {
                return Err(at.err("unterminated string"));
            }
            let text = unquote(&line[start..o]).ok_or_else(|| at.err("invalid string escape"))?;
            out.push(Token { text, col: start + 1, quoted: true });
            continue;
        }
        if digit(c) || c == b'.' && b.get(o + 1).is_some_and(|&d| digit(d)) {
            o += 1;
            while o < b.len() && (digit(b[o]) || b[o] == b'.') {
                o += 1;
            }
            if line[o..].starts_with("rad") || line[o..].starts_with("deg") {
                o += 3;
            } else if o < b.len() && (b[o] == b's' || b[o] == b'%') {
                o += 1;
            }
        } else if letter(c) {
            o += 1;
            while o < b.len() && (letter(b[o]) || digit(b[o]) || b[o] == b'-') {
                o += 1;
            }
        } else if b"=(),@:.+-".contains(&c) {
            o += 1;
        } else {
            // Go reports the offending byte as a Latin-1 rune.
            return Err(at.err(format!("unexpected character {}", quote(&char::from(c).to_string()))));
        }
        out.push(Token { text: line[start..o].to_string(), col: start + 1, quoted: false });
    }
    Ok(out)
}

pub(crate) fn identifier(v: &str) -> bool {
    let b = v.as_bytes();
    !b.is_empty() && (b[0].is_ascii_alphabetic() || b[0] == b'_') && b.iter().all(|c| c.is_ascii_alphanumeric() || *c == b'_')
}

impl Reader {
    fn end(&self) -> bool {
        self.offset >= self.tokens.len()
    }
    fn peek(&self) -> (String, usize, bool) {
        match self.tokens.get(self.offset) {
            Some(t) => (t.text.clone(), t.col, t.quoted),
            None => ("<end>".into(), self.pos.col, false),
        }
    }
    fn take(&mut self) -> (String, usize, bool) {
        let t = self.peek();
        if !self.end() {
            self.offset += 1;
        }
        t
    }
    fn failure(&self, m: impl Into<String>) -> Diag {
        Pos { line: self.pos.line, col: self.peek().1 }.err(m)
    }
    fn want(&mut self, text: &str) -> Result<(), Diag> {
        let p = self.peek();
        if p.0 != text || p.2 {
            return Err(self.failure(format!("expected {}", quote(text))));
        }
        self.take();
        Ok(())
    }
    fn is(&self, text: &str) -> bool {
        let p = self.peek();
        !p.2 && p.0 == text
    }
    fn value(&mut self) -> Result<Value, Diag> {
        let cur = self.take();
        if cur.2 {
            return Ok(Value { text: cur.0, pair: vec![], quoted: true });
        }
        if cur.0 == "<end>" {
            return Err(self.failure("expected value"));
        }
        let mut text = cur.0;
        if text == "(" {
            let first = self.value()?;
            self.want(",")?;
            let second = self.value()?;
            let mut pair = vec![first, second];
            if self.peek().0 == "," {
                self.take();
                pair.push(self.value()?);
            }
            self.want(")")?;
            return Ok(Value { text: String::new(), pair, quoted: false });
        }
        if matches!(text.as_str(), "+" | "-" | "@") {
            let next = self.take();
            if next.0 == "<end>" {
                return Err(self.failure("expected value"));
            }
            text += &next.0;
        }
        if matches!(self.peek().0.as_str(), "+" | "-") {
            text += &self.take().0;
            text += &self.take().0;
        }
        if text.contains(['=', ')', ',', ':']) {
            return Err(self.failure("expected value"));
        }
        Ok(Value { text, pair: vec![], quoted: false })
    }
    fn attributes(&mut self) -> Result<Args, Diag> {
        let mut r = Args::new();
        while !self.end() {
            let n = self.take();
            if n.2 || !identifier(&n.0) {
                return Err(self.pos.err("expected attribute identifier"));
            }
            self.want("=")?;
            let v = self.value()?;
            if r.contains_key(&n.0) {
                return Err(self.pos.err(format!("duplicate attribute {}", n.0)));
            }
            r.insert(n.0, v);
        }
        Ok(r)
    }
    fn arguments(&mut self) -> Result<Args, Diag> {
        self.want("(")?;
        let mut r = Args::new();
        let mut ordinal = 0;
        while !self.is(")") {
            if self.end() {
                return Err(self.failure("expected \")\""));
            }
            let mut key = ordinal.to_string();
            ordinal += 1;
            if self.tokens.get(self.offset + 1).is_some_and(|t| t.text == "=") {
                let n = self.take();
                if n.2 || !identifier(&n.0) {
                    return Err(self.pos.err("expected argument identifier"));
                }
                key = n.0;
                self.take();
            }
            let v = self.value()?;
            if r.contains_key(&key) {
                return Err(self.pos.err(format!("duplicate argument {key}")));
            }
            r.insert(key, v);
            if self.is(")") {
                break;
            }
            self.want(",")?;
            if self.is(")") {
                return Err(self.failure("trailing comma"));
            }
        }
        self.take();
        Ok(r)
    }
}

/// Strict decimal: `[+-]? (digits[.digits*] | .digits)`, finite, no exponent.
pub(crate) fn decimal(s: &str) -> Option<f64> {
    let u = s.strip_prefix(['+', '-']).unwrap_or(s);
    let (w, f) = u.split_once('.').map_or((u, None), |(a, b)| (a, Some(b)));
    let ok = w.bytes().all(|c| c.is_ascii_digit()) && f.map_or(true, |f| f.bytes().all(|c| c.is_ascii_digit()));
    if !ok || (w.is_empty() && f.map_or(true, str::is_empty)) {
        return None;
    }
    s.parse::<f64>().ok().filter(|v| v.is_finite())
}

fn edit_distance(a: &str, b: &str) -> usize {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    let mut row: Vec<usize> = (0..=b.len()).collect();
    for i in 0..a.len() {
        let mut diag = row[0];
        row[0] = i + 1;
        for j in 0..b.len() {
            let saved = row[j + 1];
            let cost = usize::from(a[i] != b[j]);
            row[j + 1] = (row[j] + 1).min(row[j + 1] + 1).min(diag + cost);
            diag = saved;
        }
    }
    row[b.len()]
}

/// `unknown KIND "name"` plus a did-you-mean when edit distance <= 2 (ties: lexical).
pub(crate) fn unknown<S: AsRef<str>>(kind: &str, name: &str, choices: &[S]) -> String {
    let (mut best, mut dist) = ("", 3);
    for c in choices {
        let c = c.as_ref();
        let d = edit_distance(name, c);
        if d < dist || d == dist && c < best {
            best = c;
            dist = d;
        }
    }
    let mut m = format!("unknown {kind} {}", quote(name));
    if dist <= 2 {
        m += &format!("; did you mean {}?", quote(best));
    }
    m
}

/// Parse source into a source-located (unchecked) scene.
pub fn parse(source: &str) -> Result<Scene, Diag> {
    let p11 = Pos { line: 1, col: 1 };
    if source.len() > MAX_INPUT {
        return Err(p11.err("input exceeds 256 KiB"));
    }
    let mut scene = Scene::default();
    let (mut seen_scene, mut seen_action, mut seen_version) = (false, false, false);
    for (index, line) in source.split('\n').enumerate() {
        let mut pos = Pos { line: index + 1, col: 1 };
        if line.len() > MAX_LINE {
            return Err(pos.err("line exceeds 16 KiB"));
        }
        let trimmed = line.trim_matches(|c: char| c.is_whitespace());
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let tokens = lex(line, index + 1)?;
        let mut r = Reader { tokens, offset: 0, pos };
        let head = r.take();
        if head.2 {
            return Err(pos.err("expected statement identifier"));
        }
        pos.col = head.1;
        r.pos = pos;
        let mut err: Option<Diag> = None;
        match head.0.as_str() {
            "mdgl" => {
                let v = r.take();
                if seen_scene || seen_version || v.2 || v.0 != "0.1" || !r.end() {
                    return Err(pos.err("expected initial mdgl 0.1"));
                }
                seen_version = true;
            }
            "scene" => {
                if seen_scene {
                    return Err(pos.err("duplicate scene"));
                }
                scene.pos = pos;
                match r.attributes() {
                    Ok(a) => scene.attr = a,
                    Err(e) => err = Some(e),
                }
                seen_scene = true;
            }
            "actor" => {
                if !seen_scene {
                    return Err(pos.err("scene must precede actors"));
                }
                if seen_action {
                    return Err(pos.err("actors must precede actions"));
                }
                let name = r.take();
                if name.2 || !identifier(&name.0) {
                    return Err(pos.err("expected actor identifier"));
                }
                let mut actor = Actor { pos, name: name.0, ..Default::default() };
                r.want("=")?;
                let kind = r.take();
                if kind.2 || !identifier(&kind.0) {
                    return Err(pos.err("expected shape identifier"));
                }
                actor.kind = kind.0;
                actor.args = r.arguments()?;
                r.want("at")?;
                let mut point = r.value()?;
                if point.pair.len() != 2 {
                    return Err(pos.err("expected (x, y) position"));
                }
                actor.y = point.pair.pop().unwrap();
                actor.x = point.pair.pop().unwrap();
                match r.attributes() {
                    Ok(a) => actor.attr = a,
                    Err(e) => err = Some(e),
                }
                scene.actors.push(actor);
                if scene.actors.len() > MAX_ACTORS {
                    return Err(pos.err("actor limit 64 exceeded"));
                }
            }
            "@" => {
                if !seen_scene {
                    return Err(pos.err("scene must precede actions"));
                }
                seen_action = true;
                let value = r.value()?;
                let begin = decimal(value.text.strip_suffix('s').unwrap_or(&value.text));
                let begin = match begin {
                    Some(b) if !value.quoted && value.pair.is_empty() && b >= 0.0 => b,
                    _ => return Err(pos.err("invalid action time")),
                };
                r.want(":")?;
                let name = r.take();
                if name.2 || !identifier(&name.0) {
                    return Err(pos.err("expected actor identifier"));
                }
                let mut action = Action { pos, begin, actor: name.0, ..Default::default() };
                r.want(".")?;
                let verb = r.take();
                if verb.2 || !identifier(&verb.0) {
                    return Err(pos.err("expected action identifier"));
                }
                action.verb = verb.0;
                match r.arguments() {
                    Ok(a) => {
                        action.args = a;
                        if !r.end() {
                            err = Some(r.failure(format!("unexpected token {}", quote(&r.peek().0))));
                        }
                    }
                    Err(e) => err = Some(e),
                }
                scene.actions.push(action);
                if scene.actions.len() > MAX_ACTIONS {
                    return Err(pos.err("action limit 1024 exceeded"));
                }
            }
            "camera" | "light" | "mesh" | "material" | "threejs" => {
                return Err(pos.err(format!("{} is reserved; not yet supported in 0.1", head.0)));
            }
            h => {
                let mut m = unknown("statement", h, &["mdgl", "scene", "actor", "@"]);
                m += "; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)";
                if matches!(h, "text" | "rect" | "circle" | "cube") {
                    m += &format!("; use actor NAME = {h}(...) at (X,Y)");
                }
                return Err(pos.err(m));
            }
        }
        if let Some(e) = err {
            return Err(e);
        }
    }
    if !seen_scene {
        return Err(p11.err("missing scene"));
    }
    Ok(scene)
}

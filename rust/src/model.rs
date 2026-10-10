//! Source-located parsed/checked scene model.
use std::collections::BTreeMap;

/// One-based line and UTF-8 byte column.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Pos {
    pub line: usize,
    pub col: usize,
}

/// Diagnostic `line:col: message` (first diagnostic is the conformance observable).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Diag {
    pub line: usize,
    pub col: usize,
    pub message: String,
}

impl Pos {
    pub fn err(self, message: impl Into<String>) -> Diag {
        Diag { line: self.line, col: self.col, message: message.into() }
    }
}

impl std::fmt::Display for Diag {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}:{}: {}", self.line, self.col, self.message)
    }
}

/// A scalar token (`text`), a 2/3-tuple (`pair`) or a quoted string.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Value {
    pub text: String,
    pub pair: Vec<Value>,
    pub quoted: bool,
}

pub type Args = BTreeMap<String, Value>;

#[derive(Debug, Clone, Default)]
pub struct Scene {
    pub pos: Pos,
    pub attr: Args,
    pub actors: Vec<Actor>,
    pub actions: Vec<Action>,
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// Simple duration in seconds (explicit period, or greatest action end).
    pub period: f64,
    pub explicit_period: bool,
    /// 0 means infinite.
    pub repeat: u32,
    pub fallback: String,
}

#[derive(Debug, Clone, Default)]
pub struct Actor {
    pub pos: Pos,
    pub name: String,
    pub kind: String,
    pub args: Args,
    pub x: Value,
    pub y: Value,
    pub attr: Args,
    pub text: String,
    pub color: String,
    pub parent: String,
    pub width: f64,
    pub height: f64,
    pub z: f64,
    pub scale: f64,
}

#[derive(Debug, Clone, Default)]
pub struct Action {
    pub pos: Pos,
    pub actor: String,
    pub verb: String,
    pub args: Args,
    pub begin: f64,
    pub duration: f64,
    pub property: String,
    pub ease: String,
}

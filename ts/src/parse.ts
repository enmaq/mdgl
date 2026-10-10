// MDGL 0.1 lexical + syntactic parser. Builds a source-located model; statement
// order and semantic rules live in check.ts. Written from SPEC.md and the
// conformance corpus only.

declare const Buffer: { byteLength(s: string, enc: string): number };

/** One diagnostic: 1-based line, 1-based UTF-8 byte column. */
export interface Diag { line: number; col: number; message: string }

export type Coord =
  | { kind: 'num'; value: number; percent: boolean }
  | { kind: 'anchor'; name: string; offset: number };
export interface Point { x: Coord; y: Coord; col: number }

export type Shape =
  | { kind: 'text'; text: string; big: boolean }
  | { kind: 'rect'; width: number; height: number; border?: string; title?: string }
  | { kind: 'circle'; radius: number }
  | { kind: 'cube'; size: number; style?: string };

export type Value =
  | { kind: 'number'; value: number; suffix: string; raw: string }
  | { kind: 'keyword'; value: string; raw: string }
  | { kind: 'string'; value: string; raw: string }
  | { kind: 'point'; value: Point; raw: string };
export interface Arg { key: string; value?: Value; col: number }

export interface SceneStmt { kind: 'scene'; line: number; col: number; attrs: Array<{ key: string; value: string; col: number }> }
export interface ActorStmt {
  kind: 'actor'; line: number; col: number; name: string; shape: Shape; at: Point;
  color?: string; parent?: string; z?: number; anchor?: Point;
}
export interface ActionStmt { kind: 'action'; line: number; col: number; timeNs: number; actor: string; verb: string; args: Arg[] }
export interface VersionStmt { kind: 'version'; line: number; col: number; ok: boolean }
export interface UnknownStmt { kind: 'unknown'; line: number; col: number }
export type Stmt = SceneStmt | ActorStmt | ActionStmt | VersionStmt | UnknownStmt;

/** Parsed (unchecked) document. `syntax` is the first syntax error, if any; statements before it are complete. */
export interface Document { statements: Stmt[]; syntax?: Diag; inputError?: Diag }

export const MAX_INPUT = 256 * 1024;
export const MAX_LINE = 16384;
export const bytes = (s: string): number => Buffer.byteLength(s, 'utf8');

class SyntaxErr { constructor(public d: Diag) {} }

const SIMPLE_ESC: Record<string, string> = { a: '\x07', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t', v: '\v', '\\': '\\', '"': '"' };
const isDigit = (c: string): boolean => c >= '0' && c <= '9';
const isIdStart = (c: string): boolean => /[A-Za-z_]/.test(c);
const isIdChar = (c: string): boolean => /[A-Za-z0-9_]/.test(c);
const hex = (s: string): boolean => /^[0-9a-fA-F]+$/.test(s);

/** Nanoseconds from a nonnegative decimal-seconds token (optional trailing s already removed). */
export function decimalToNs(tok: string): number {
  const [w, f = ''] = tok.split('.');
  const frac = (f + '0000000000').slice(0, 10);
  let ns = Number(w || '0') * 1e9 + Number(frac.slice(0, 9)) + (frac[9] >= '5' ? 1 : 0);
  return ns;
}

class Cur {
  i = 0;
  constructor(public s: string, public line: number) {}
  col(at = this.i): number { return bytes(this.s.slice(0, at)) + 1; }
  err(msg: string, at = this.i): never { throw new SyntaxErr({ line: this.line, col: this.col(at), message: msg }); }
  ws(): void { while (this.i < this.s.length && (this.s[this.i] === ' ' || this.s[this.i] === '\t')) this.i++; }
  eof(): boolean { return this.i >= this.s.length; }
  peek(): string { return this.s[this.i] ?? ''; }
  eat(c: string): boolean { if (this.s.startsWith(c, this.i)) { this.i += c.length; return true; } return false; }
  expect(c: string): void { this.ws(); if (!this.eat(c)) this.err(this.eof() ? `unexpected end of line, expected ${JSON.stringify(c)}` : `expected ${JSON.stringify(c)} but found ${JSON.stringify(this.peek())}`); }
  ident(what = 'identifier'): string {
    this.ws();
    if (!isIdStart(this.peek())) this.err(this.eof() ? `unexpected end of line, expected ${what}` : `unexpected character ${JSON.stringify(this.peek())}`);
    const st = this.i;
    while (isIdChar(this.peek())) this.i++;
    return this.s.slice(st, this.i);
  }
  /** unsigned decimal; returns raw text */
  unsigned(): string {
    const st = this.i;
    let n = 0;
    while (isDigit(this.peek())) { this.i++; n++; }
    if (this.peek() === '.') { this.i++; while (isDigit(this.peek())) { this.i++; n++; } }
    if (n === 0) this.err('expected number', st);
    return this.s.slice(st, this.i);
  }
  number(): number {
    this.ws();
    const st = this.i;
    let neg = false;
    if (this.peek() === '+' || this.peek() === '-') { neg = this.peek() === '-'; this.i++; }
    const u = this.unsigned();
    if (this.peek() === 'e' || this.peek() === 'E') this.err('exponents are not allowed', this.i);
    void st;
    return neg ? -Number(u) : Number(u);
  }
  string(): string {
    this.ws();
    const st = this.i;
    if (!this.eat('"')) this.err('expected string');
    let out = '';
    for (;;) {
      if (this.eof()) this.err('unterminated string', st);
      const c = this.s[this.i];
      if (c === '"') { this.i++; return out; }
      if (c !== '\\') { out += c; this.i++; continue; }
      const eAt = this.i;
      this.i++;
      const e = this.s[this.i] ?? '';
      if (e in SIMPLE_ESC) { out += SIMPLE_ESC[e]; this.i++; }
      else if (e === 'x' || e === 'u' || e === 'U') {
        const n = e === 'x' ? 2 : e === 'u' ? 4 : 8;
        const h = this.s.slice(this.i + 1, this.i + 1 + n);
        if (h.length !== n || !hex(h)) this.err('invalid escape in string', eAt);
        const cp = parseInt(h, 16);
        if (e !== 'x' && (cp > 0x10ffff || (cp >= 0xd800 && cp < 0xe000))) this.err('invalid escape in string', eAt);
        out += e === 'x' ? String.fromCharCode(cp) : String.fromCodePoint(cp);
        this.i += 1 + n;
      } else if (e >= '0' && e <= '7') {
        const o = this.s.slice(this.i, this.i + 3);
        if (!/^[0-7]{3}$/.test(o) || parseInt(o, 8) > 255) this.err('invalid escape in string', eAt);
        out += String.fromCharCode(parseInt(o, 8));
        this.i += 3;
      } else this.err('invalid escape in string', eAt);
    }
  }
  coord(): Coord {
    this.ws();
    const c = this.peek();
    if (isIdStart(c)) {
      const at = this.i;
      const name = this.ident();
      if (!['center', 'left', 'right', 'top', 'bottom'].includes(name)) this.err(`unknown anchor ${JSON.stringify(name)}`, at);
      let offset = 0;
      this.ws();
      if (this.peek() === '+' || this.peek() === '-') {
        const neg = this.peek() === '-';
        this.i++;
        this.ws();
        offset = Number(this.unsigned());
        if (neg) offset = -offset;
      }
      return { kind: 'anchor', name, offset };
    }
    const value = this.number();
    const percent = this.eat('%');
    return { kind: 'num', value, percent };
  }
  point(): Point {
    this.ws();
    const col = this.col();
    this.expect('(');
    const x = this.coord();
    this.expect(',');
    const y = this.coord();
    this.expect(')');
    return { x, y, col };
  }
  value(): Value {
    this.ws();
    const st = this.i;
    const c = this.peek();
    if (c === '(') { const value = this.point(); return { kind: 'point', value, raw: this.s.slice(st, this.i) }; }
    if (c === '"') { const value = this.string(); return { kind: 'string', value, raw: this.s.slice(st, this.i) }; }
    if (c === '+' || c === '-' || c === '.' || isDigit(c)) {
      const value = this.number();
      const sst = this.i;
      while (/[A-Za-z]/.test(this.peek())) this.i++;
      return { kind: 'number', value, suffix: this.s.slice(sst, this.i), raw: this.s.slice(st, this.i) };
    }
    if (isIdStart(c)) {
      this.ident();
      while (this.peek() === '-' && isIdStart(this.s[this.i + 1] ?? '')) { this.i++; this.ident(); }
      return { kind: 'keyword', value: this.s.slice(st, this.i), raw: this.s.slice(st, this.i) };
    }
    return this.err(this.eof() ? 'unexpected end of line, expected value' : `unexpected character ${JSON.stringify(c)}`);
  }
  end(): void { this.ws(); if (!this.eof()) this.err(`unexpected character ${JSON.stringify(this.peek())}`); }
}

function parseShape(c: Cur): Shape {
  const at = c.i;
  const kind = c.ident('shape');
  c.expect('(');
  if (kind === 'text') {
    const text = c.string();
    let big = false;
    c.ws();
    if (c.eat(',')) { const w = c.ident(); if (w !== 'big') c.err(`unknown text option ${JSON.stringify(w)}`); big = true; }
    c.expect(')');
    return { kind, text, big };
  }
  if (kind === 'circle') { const radius = c.number(); c.expect(')'); return { kind, radius }; }
  if (kind === 'rect') {
    const width = c.number(); c.expect(','); const height = c.number();
    const s: Shape = { kind, width, height };
    const seen = new Set<string>();
    for (c.ws(); c.eat(','); c.ws()) {
      const kat = c.i;
      const k = c.ident();
      if (k !== 'border' && k !== 'title') c.err(`unknown rect argument ${JSON.stringify(k)}`, kat);
      if (seen.has(k)) c.err(`duplicate rect argument ${k}`, kat);
      seen.add(k);
      c.expect('=');
      if (k === 'title') s.title = c.string();
      else { c.ws(); const v = c.ident(); if (v !== 'square' && v !== 'round') c.err(`unknown border ${JSON.stringify(v)}`); s.border = v; }
    }
    c.expect(')');
    return s;
  }
  if (kind === 'cube') {
    let size: number | undefined;
    let style: string | undefined;
    for (let first = true; ; first = false) {
      c.ws();
      if (!first && !c.eat(',')) break;
      const kat = c.i;
      c.ws();
      const k = c.ident();
      c.expect('=');
      if (k === 'size') { if (size !== undefined) c.err('duplicate cube argument size', kat); size = c.number(); }
      else if (k === 'style') { if (style !== undefined) c.err('duplicate cube argument style', kat); c.ws(); style = c.ident(); if (style !== 'wire') c.err('cube style must be wire'); }
      else c.err(`unknown cube argument ${JSON.stringify(k)}`, kat);
    }
    c.expect(')');
    if (size === undefined) c.err('cube requires size', at);
    return { kind, size, style };
  }
  return c.err(`unknown shape ${JSON.stringify(kind)}`, at);
}

function parseActor(c: Cur, line: number, col: number): ActorStmt {
  const name = c.ident('actor name');
  c.expect('=');
  c.ws();
  const shape = parseShape(c);
  c.ws();
  const kw = c.i;
  if (c.ident('"at"') !== 'at') c.err('expected "at"', kw);
  const at = c.point();
  const a: ActorStmt = { kind: 'actor', line, col, name, shape, at };
  const seen = new Set<string>();
  for (c.ws(); !c.eof(); c.ws()) {
    const kat = c.i;
    const k = c.ident();
    if (!['color', 'parent', 'z', 'anchor'].includes(k)) c.err(`unknown actor attribute ${JSON.stringify(k)}`, kat);
    if (seen.has(k)) c.err(`duplicate actor attribute ${k}`, kat);
    seen.add(k);
    c.expect('=');
    c.ws();
    if (k === 'z') a.z = c.number();
    else if (k === 'anchor') a.anchor = c.point();
    else a[k as 'color' | 'parent'] = c.ident();
  }
  return a;
}

function parseAction(c: Cur, line: number, col: number): ActionStmt {
  c.ws();
  const tat = c.i;
  const t0 = c.unsigned();
  const tok = c.eat('s') ? t0 : t0;
  const timeNs = decimalToNs(tok);
  if (!(timeNs >= 0) || timeNs > 1e15) c.err('time out of range', tat);
  c.expect(':');
  const actor = c.ident('actor name');
  c.expect('.');
  const verb = c.ident('action verb');
  c.expect('(');
  const args: Arg[] = [];
  c.ws();
  for (let first = true; ; first = false) {
    c.ws();
    if (first && c.peek() === ')') c.err('expected argument');
    if (!first && !c.eat(',')) break;
    c.ws();
    const kcol = c.col();
    const key = c.ident('argument');
    c.ws();
    if (c.eat('=')) args.push({ key, value: c.value(), col: kcol });
    else args.push({ key, col: kcol });
  }
  c.expect(')');
  return { kind: 'action', line, col, timeNs, actor, verb, args };
}

/** Parse source into a statement list. Never throws for string input. */
export function parse(source: string): Document {
  if (typeof source !== 'string') throw new TypeError('mdgl.parse: source must be a string');
  const doc: Document = { statements: [] };
  if (bytes(source) > MAX_INPUT) { doc.inputError = { line: 1, col: 1, message: 'input exceeds 256 KiB' }; return doc; }
  const lines = source.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const n = i + 1;
    if (bytes(lines[i]) > MAX_LINE) { doc.inputError = { line: n, col: 1, message: 'line exceeds 16 KiB' }; return doc; }
  }
  for (let i = 0; i < lines.length; i++) {
    const n = i + 1;
    const raw = lines[i].endsWith('\r') ? lines[i].slice(0, -1) : lines[i];
    const c = new Cur(raw, n);
    c.ws();
    if (c.eof() || c.peek() === '#') continue;
    const col = c.col();
    try {
      if (c.peek() === '@') {
        c.i++;
        doc.statements.push(parseAction(c, n, col));
        c.end();
        continue;
      }
      const at = c.i;
      const head = c.ident('statement');
      void at;
      if (head === 'mdgl') {
        c.ws();
        const ok = raw.slice(c.i).trim() === '0.1';
        c.i = raw.length;
        doc.statements.push({ kind: 'version', line: n, col, ok });
      } else if (head === 'scene') {
        const attrs: SceneStmt['attrs'] = [];
        for (c.ws(); !c.eof(); c.ws()) {
          const acol = c.col();
          const key = c.ident('scene attribute');
          c.expect('=');
          const st = c.i;
          while (!c.eof() && c.peek() !== ' ' && c.peek() !== '\t') c.i++;
          if (c.i === st) c.err('expected scene attribute value');
          attrs.push({ key, value: raw.slice(st, c.i), col: acol });
        }
        doc.statements.push({ kind: 'scene', line: n, col, attrs });
      } else if (head === 'actor') {
        doc.statements.push(parseActor(c, n, col));
        c.end();
      } else doc.statements.push({ kind: 'unknown', line: n, col });
    } catch (e) {
      if (e instanceof SyntaxErr) { doc.syntax = e.d; return doc; }
      throw e;
    }
  }
  return doc;
}

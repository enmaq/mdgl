// Conformance adapter core (PROTOCOL v1): one request line in, one response line out.
// Pure string -> string; bin/mdgl-adapter.js wires stdin/stdout. JSON numbers are kept as
// lexemes and validated as exact mathematical integers (9007199254740991.1 rejects).
import { parseChecked } from './check';
import { compileDocument, fallbackFrame, frameNs } from './eval';

export const MAX_REQUEST_LINE = 2097152;

interface Num { num: string }
type J = null | boolean | string | Num | J[] | { [k: string]: J };
class Bad extends Error {}

function parseJson(t: string): { v: J; lone: boolean } {
  let i = 0, lone = false, depth = 0;
  const ws = (): void => { while (i < t.length && (t[i] === ' ' || t[i] === '\t' || t[i] === '\n' || t[i] === '\r')) i++; };
  const lit = (w: string, v: J): J => { if (!t.startsWith(w, i)) throw new Bad(); i += w.length; return v; };
  const str = (): string => {
    i++;
    let o = '';
    for (;;) {
      if (i >= t.length) throw new Bad();
      const c = t[i];
      if (c === '"') { i++; return o; }
      if (c < ' ') throw new Bad();
      if (c !== '\\') { o += c; i++; continue; }
      const e = t[i + 1];
      const m: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' };
      if (e in m) { o += m[e]; i += 2; } else if (e === 'u') {
        const h = t.slice(i + 2, i + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(h)) throw new Bad();
        const cu = parseInt(h, 16);
        if (cu >= 0xd800 && cu < 0xdc00) {
          const lo = /^\\u([dD][c-fC-F][0-9a-fA-F]{2})/.exec(t.slice(i + 6, i + 12));
          if (lo) { o += String.fromCharCode(cu, parseInt(lo[1], 16)); i += 12; continue; }
          lone = true;
        } else if (cu >= 0xdc00 && cu < 0xe000) lone = true;
        o += String.fromCharCode(cu);
        i += 6;
      } else throw new Bad();
    }
  };
  const val = (): J => {
    ws();
    const c = t[i];
    if (++depth > 200) throw new Bad();
    let r: J;
    if (c === '{') {
      i++; const o: { [k: string]: J } = {}; ws();
      if (t[i] === '}') i++;
      else for (;;) { ws(); if (t[i] !== '"') throw new Bad(); const k = str(); ws(); if (t[i++] !== ':') throw new Bad(); o[k] = val(); ws(); if (t[i] === ',') { i++; continue; } if (t[i++] === '}') break; throw new Bad(); }
      r = o;
    } else if (c === '[') {
      i++; const a: J[] = []; ws();
      if (t[i] === ']') i++;
      else for (;;) { a.push(val()); ws(); if (t[i] === ',') { i++; continue; } if (t[i++] === ']') break; throw new Bad(); }
      r = a;
    } else if (c === '"') r = str();
    else if (c === 't') r = lit('true', true);
    else if (c === 'f') r = lit('false', false);
    else if (c === 'n') r = lit('null', null);
    else {
      const m = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(t.slice(i, i + 4096));
      if (!m) throw new Bad();
      i += m[0].length;
      r = { num: m[0] };
    }
    depth--;
    return r;
  };
  const v = val();
  ws();
  if (i !== t.length) throw new Bad();
  return { v, lone };
}

/** Exact mathematical integer value of a JSON number lexeme, or null if it is not an integer. */
export function mathInt(lex: string): bigint | null {
  const m = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(lex);
  if (!m) return null;
  const frac = m[3] ?? '';
  const exp = Number(m[4] ?? '0') - frac.length;
  let d = BigInt(m[2] + frac);
  if (d === 0n) return 0n;
  if (exp > 400) return null; // far beyond any accepted range; treat as out of range by callers
  if (exp >= 0) d *= 10n ** BigInt(exp);
  else { const p = 10n ** BigInt(-exp); if (-exp > 4000 || d % p !== 0n) return null; d /= p; }
  return m[1] ? -d : d;
}

const isNum = (v: J | undefined): v is Num => typeof v === 'object' && v !== null && !Array.isArray(v) && 'num' in v && typeof (v as Num).num === 'string';
function intIn(v: J | undefined, lo: bigint, hi: bigint): number | null {
  if (!isNum(v)) return null;
  const n = mathInt(v.num);
  return n === null || n < lo || n > hi ? null : Number(n);
}
const out = (o: unknown): string => JSON.stringify(o);
const fail = (id: string | null, code: string, message: string, extra?: object): string => out({ v: 1, id, ok: false, error: { code, message, ...extra } });

/** bad_request response for a line whose bytes are not valid UTF-8 (the id is unrecoverable). */
export const invalidUtf8 = (): string => fail(null, 'bad_request', 'request line is not valid UTF-8');

/** Handle one request line (without its newline). Always returns exactly one response line. */
export function handleLine(line: string, lineBytes = line.length): string {
  if (lineBytes > MAX_REQUEST_LINE) return fail(null, 'bad_request', 'request line too long');
  let top: J, lone: boolean;
  try { ({ v: top, lone } = parseJson(line)); } catch (e) {
    return fail(null, 'bad_request', line.trim() === '' ? 'blank line' : 'invalid JSON');
  }
  if (typeof top !== 'object' || top === null || Array.isArray(top) || isNum(top)) return fail(null, 'bad_request', 'request must be a JSON object');
  const o = top as { [k: string]: J };
  const id = typeof o.id === 'string' ? o.id : null;
  if (!isNum(o.v) || mathInt(o.v.num) === null) return fail(id, 'bad_request', 'v must be an integer');
  if (mathInt(o.v.num) !== 1n) return fail(id, 'unsupported_version', `protocol version ${o.v.num} is not supported`);
  if (id === null) return fail(null, 'bad_request', 'id must be a string');
  if (o.op !== 'check' && o.op !== 'frame') return fail(id, 'bad_request', 'op must be "check" or "frame"');
  if (typeof o.source !== 'string') return fail(id, 'bad_request', 'source must be a string');
  if (lone) return fail(id, 'bad_request', 'source contains a lone surrogate');
  let width = 0, height = 0, tNs = 0, fb = false;
  if (o.op === 'frame') {
    const w = intIn(o.width, 1n, 200n), h = intIn(o.height, 1n, 60n);
    if (w === null || h === null) return fail(id, 'bad_request', 'width and height must be integers in 1..200 and 1..60');
    width = w; height = h;
    if ('fallback' in o && typeof o.fallback !== 'boolean') return fail(id, 'bad_request', 'fallback must be a boolean');
    fb = o.fallback === true;
    if (!fb) {
      const t = intIn(o.time_ns, 0n, 9007199254740991n);
      if (t === null) return fail(id, 'bad_request', 'time_ns must be an integer in 0..2^53-1');
      tNs = t;
    }
  }
  const r = parseChecked(o.source);
  if (o.op === 'check') return out({ v: 1, id, ok: true, diagnostics: r.ok ? [] : r.diagnostics });
  if (!r.ok) return fail(id, 'invalid_source', 'source has diagnostics', { diagnostics: r.diagnostics });
  const sc = compileDocument(r.doc);
  const f = fb ? fallbackFrame(sc, width, height) : frameNs(sc, tNs, width, height);
  const cells = f.cells.map((row) => row.map((c) => ({ r: c.r, fg: c.fg, bg: c.bg })));
  return out(fb ? { v: 1, id, ok: true, width: f.width, height: f.height, cells } : { v: 1, id, ok: true, width: f.width, height: f.height, cells, done: f.done });
}

// MDGL 0.1 semantic checker over the parsed Document. Statement-order, reference,
// argument, timing and limit rules from SPEC.md. First error is the compat
// diagnostic (`line:col: message`); checking stops at the first error.

import { graphemeCount as graphemes } from './unicode';
import { ActionStmt, ActorStmt, Arg, Coord, Diag, Document, Point, SceneStmt, Value, bytes, decimalToNs, parse } from './parse';

export const MAX_ACTORS = 64;
export const MAX_ACTIONS = 1024;
const MAX_NS = 60e9;
const SCENE_KEYS = ['width', 'height', 'period', 'repeat', 'fallback', 'fps'];
const COLORS = ['normal', 'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white', 'accent'];
const EASES = ['linear', 'ease', 'ease-in', 'ease-out', 'ease-in-out', 'bounce'];
const VERBS = ['fade', 'move', 'scale', 'color', 'type', 'blink', 'wipe', 'slide', 'rotate'];
const PROP: Record<string, string> = { fade: 'opacity', blink: 'opacity', move: 'position', slide: 'position', scale: 'scale', color: 'color', type: 'reveal', wipe: 'reveal', rotate: 'rotation' };

export type Fallback = { kind: 'start' } | { kind: 'end' } | { kind: 'at'; ns: number };
export interface CheckedScene {
  line: number; width: number; height: number; fps: number;
  /** explicit period in ns, if given */
  period?: number;
  /** repeat count; Infinity for `infinite` */
  repeat: number;
  fallback: Fallback;
  /** simple duration in ns: explicit period, else greatest action end */
  duration: number;
}
export interface CheckedAction extends ActionStmt { beginNs: number; endNs: number; property: string; durNs: number }
export interface CheckedDocument {
  scene: CheckedScene;
  actors: ActorStmt[];
  actions: CheckedAction[];
}
export type ParseResult = { ok: true; doc: CheckedDocument } | { ok: false; diagnostics: Diag[] };

class Stop { constructor(public d: Diag) {} }

const q = (s: string): string => JSON.stringify(s);

function lev(a: string, b: string): number {
  const p = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = p[0];
    p[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const t = p[j];
      p[j] = Math.min(p[j] + 1, p[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = t;
    }
  }
  return p[b.length];
}
/** `; did you mean "x"?` when a candidate is within edit distance 2 (ties: lexical order). */
function suggest(name: string, cands: string[]): string {
  let best: string | undefined, bd = 3;
  for (const c of [...cands].sort()) { const d = lev(name, c); if (d <= 2 && d < bd) { best = c; bd = d; } }
  return best === undefined ? '' : `; did you mean ${q(best)}?`;
}

function checkScene(sc: SceneStmt): CheckedScene {
  const fail = (m: string): never => { throw new Stop({ line: sc.line, col: sc.col, message: m }); };
  const v = new Map<string, string>();
  for (const a of sc.attrs) {
    if (!SCENE_KEYS.includes(a.key)) fail(`unknown scene attribute ${q(a.key)}${suggest(a.key, SCENE_KEYS)}`);
    if (v.has(a.key)) fail(`duplicate scene attribute ${q(a.key)}`);
    v.set(a.key, a.value);
  }
  for (const k of ['width', 'height', 'fallback']) if (!v.has(k)) fail(`missing scene attribute ${k}`);
  const int = (k: string, lo: number, hi: number, def?: string): number => {
    const s = v.get(k) ?? def;
    if (s === undefined || !/^[0-9]{1,9}$/.test(s) || Number(s) < lo || Number(s) > hi) fail(`${k} must be an integer in ${lo}..${hi}`);
    return Number(s);
  };
  const width = int('width', 1, 200), height = int('height', 1, 60), fps = int('fps', 1, 30, '30');
  let period: number | undefined;
  if (v.has('period')) {
    const m = /^((?:[0-9]+\.?[0-9]*|\.[0-9]+))s?$/.exec(v.get('period') as string);
    period = m ? decimalToNs(m[1]) : NaN;
    if (!(period > 0) || period > MAX_NS) fail('period must be positive seconds up to 60');
  }
  let repeat = 1;
  const r = v.get('repeat');
  if (r === 'infinite') repeat = Infinity;
  else if (r !== undefined) repeat = int('repeat', 1, 1000);
  if (repeat !== 1 && period === undefined) fail('repeat requires explicit period');
  const f = v.get('fallback') as string;
  let fallback: Fallback;
  if (f === 'start' || f === 'end') fallback = { kind: f };
  else {
    const m = /^@((?:[0-9]+\.?[0-9]*|\.[0-9]+))s?$/.exec(f);
    if (!m) return fail('fallback must be start, end or @time');
    fallback = { kind: 'at', ns: decimalToNs((m as RegExpExecArray)[1]) };
  }
  return { line: sc.line, width, height, fps, period, repeat, fallback, duration: period ?? 0 };
}

function checkCoord(c: Coord, axis: 'x' | 'y', fail: (m: string) => never): void {
  if (c.kind === 'num') { if (!Number.isFinite(c.value) || Math.abs(c.value) > 10000) fail('coordinate out of range'); return; }
  const ok = axis === 'x' ? ['center', 'left', 'right'] : ['center', 'top', 'bottom'];
  if (!ok.includes(c.name)) fail(`anchor ${c.name} is not valid on the ${axis} axis`);
  if (Math.abs(c.offset) > 10000) fail('coordinate out of range');
}
function checkPoint(p: Point, fail: (m: string) => never): void { checkCoord(p.x, 'x', fail); checkCoord(p.y, 'y', fail); }

function checkActor(a: ActorStmt, names: Set<string>): void {
  const fail = (m: string): never => { throw new Stop({ line: a.line, col: a.col, message: m }); };
  if (names.has(a.name)) fail(`duplicate actor ${a.name}`);
  const s = a.shape;
  const pos = (n: number, what: string, max = 200): void => { if (!(n > 0 && n <= max)) fail(`${what} must be greater than 0 and at most ${max}`); };
  const label = (t: string, what: string): void => {
    if (/[\x00-\x1f\x7f-\x9f]/.test(t)) fail(`${what} must not contain tabs, newlines or control characters`);
    if (graphemes(t) > 1024) fail(`${what} exceeds 1024 grapheme clusters`);
  };
  if (s.kind === 'text') label(s.text, 'text');
  else if (s.kind === 'rect') { pos(s.width, 'rect width'); pos(s.height, 'rect height'); if (s.title !== undefined) label(s.title, 'title'); }
  else if (s.kind === 'circle') { if (!(s.radius > 0 && s.radius <= 100)) fail('circle radius must be positive and <=100'); } // diameter 2N <= 200;
  else pos(s.size, 'cube size');
  checkPoint(a.at, fail);
  if (a.anchor) checkPoint(a.anchor, fail);
  if (a.color !== undefined && !COLORS.includes(a.color)) fail(`unknown color ${q(a.color)}${suggest(a.color, COLORS)}`);
  if (a.z !== undefined && !Number.isInteger(a.z)) fail('z must be an integer'); // SPEC: optional integer z; no other bound
}

function checkParents(actors: ActorStmt[]): void {
  const by = new Map(actors.map((a) => [a.name, a]));
  for (const a of actors) {
    if (a.parent !== undefined && !by.has(a.parent)) throw new Stop({ line: a.line, col: a.col, message: `unknown parent ${q(a.parent)}${suggest(a.parent, [...by.keys()])}` });
  }
  for (const a of actors) {
    const seen = new Set<string>();
    for (let c: ActorStmt | undefined = a; c; c = c.parent === undefined ? undefined : by.get(c.parent)) {
      if (seen.has(c.name)) { if (c === a) throw new Stop({ line: a.line, col: a.col, message: `parent cycle involving ${a.name}` }); break; }
      seen.add(c.name);
    }
  }
}

function checkAction(a: ActionStmt, actors: Map<string, ActorStmt>): CheckedAction {
  const fail = (m: string): never => { throw new Stop({ line: a.line, col: a.col, message: m }); };
  const actor = actors.get(a.actor);
  if (!actor) return fail(`unknown actor ${q(a.actor)}${suggest(a.actor, [...actors.keys()])}`);
  if (!VERBS.includes(a.verb)) return fail(`unknown action ${q(a.verb)}${suggest(a.verb, VERBS)}`);
  if (a.timeNs > MAX_NS) fail('action time must be at most 60 seconds');
  const allowed: Record<string, string[]> = {
    fade: ['in', 'out', 'dur', 'ease'], move: ['to', 'dur', 'ease'], scale: ['to', 'dur', 'ease'], color: ['to', 'dur', 'ease'],
    type: ['per_char'], blink: ['times', 'dur'], wipe: ['in', 'out', 'dur', 'ease'], slide: ['in', 'out', 'to', 'dur', 'ease'],
    rotate: ['x', 'y', 'z', 'dur', 'ease'],
  };
  const args = new Map<string, Arg>();
  for (const g of a.args) {
    if (!allowed[a.verb].includes(g.key)) fail(`unknown argument ${q(g.key)} for ${a.verb}${suggest(g.key, allowed[a.verb])}`);
    if (args.has(g.key)) fail(`duplicate argument ${g.key}`);
    args.set(g.key, g);
  }
  const need = (k: string): Value => {
    const g = args.get(k);
    if (!g) return fail(`${a.verb} requires ${k}`);
    if (!g.value) return fail(`${k} requires a value`);
    return g.value;
  };
  const flag = (k: string): boolean => { const g = args.get(k); if (g && g.value) fail(`${k} takes no value`); return !!g; };
  const seconds = (k: string, v: Value, what: string): number => {
    if (v.kind !== 'number' || !(v.suffix === '' || v.suffix === 's') || v.value < 0 || !/^[+]?[0-9.]+s?$/.test(v.raw)) return fail(`${what} must be positive seconds`);
    const ns = decimalToNs(v.raw.replace(/^\+/, '').replace(/s$/, ''));
    if (!(ns > 0)) return fail(`${what} must be positive`);
    if (ns > MAX_NS) fail(`${what} must be at most 60 seconds`);
    return ns;
  };
  let durNs = 0;
  if (a.verb !== 'type') {
    if (a.verb === 'rotate' || a.verb === 'fade' || a.verb === 'move' || a.verb === 'scale' || a.verb === 'color' || a.verb === 'wipe' || a.verb === 'slide' || a.verb === 'blink') durNs = seconds('dur', need('dur'), 'dur');
  }
  const ease = args.get('ease');
  if (ease) { const e = need('ease'); if (e.kind !== 'keyword' || !EASES.includes(e.value)) fail(`unknown ease ${q(e.raw)}${suggest(e.raw, EASES)}`); }
  const inout = (): void => { const i = flag('in'), o = flag('out'); if (i === o) fail(`${a.verb} requires exactly one of in or out`); };
  const num = (k: string, lo: (n: number) => boolean, msg: string): number => { const v = need(k); if (v.kind !== 'number' || v.suffix !== '') fail(`${k} must be a number`); const n = (v as { value: number }).value; if (!lo(n)) fail(msg); return n; };
  switch (a.verb) {
    case 'fade': inout(); break;
    case 'wipe': inout(); break;
    case 'move': { const v = need('to'); if (v.kind !== 'point') fail('to must be a point'); checkPoint((v as { value: Point }).value, fail); break; }
    case 'scale': num('to', (n) => n > 0 && n <= 16, 'scale must be greater than 0 and at most 16'); break;
    case 'color': { const v = need('to'); if (v.kind !== 'keyword' || !COLORS.includes(v.value)) fail(`unknown color ${q(v.raw)}${suggest(v.raw, COLORS)}`); break; }
    case 'blink': num('times', (n) => Number.isInteger(n) && n > 0, 'times must be a positive integer'); break;
    case 'slide': {
      inout();
      const v = need('to');
      if (v.kind !== 'keyword' || !['left', 'right', 'top', 'bottom'].includes(v.value)) fail('slide to must be left, right, top or bottom');
      break;
    }
    case 'rotate': {
      if (actor.shape.kind !== 'cube') fail('rotate is only valid on cube actors');
      if (!['x', 'y', 'z'].some((k) => args.has(k))) fail('rotate requires at least one of x, y, z');
      for (const k of ['x', 'y', 'z']) {
        if (!args.has(k)) continue;
        const v = need(k);
        if (v.kind !== 'number' || !['', 'deg', 'rad'].includes(v.suffix)) fail(`${k} must be an angle in degrees or radians`);
        const deg = v.kind === 'number' ? (v.suffix === 'rad' ? (v.value * 180) / Math.PI : v.value) : 0;
        if (Math.abs(deg) > 10000) fail('rotation out of range');
      }
      break;
    }
    case 'type': {
      const sh = actor.shape;
      if (sh.kind !== 'text') return fail('type is only valid on text actors');
      const per = seconds('per_char', need('per_char'), 'per_char');
      durNs = per * graphemes(sh.text);
      break;
    }
  }
  const endNs = a.timeNs + durNs;
  if (endNs > MAX_NS) fail('action end must be at most 60 seconds');
  return { ...a, beginNs: a.timeNs, endNs, property: PROP[a.verb], durNs };
}

/** Check a parsed document; returns the checked model or the first diagnostic. */
export function checkDocument(doc: Document): ParseResult {
  const stop = (d: Diag): ParseResult => ({ ok: false, diagnostics: [d] });
  if (doc.inputError) return stop(doc.inputError);
  let scene: CheckedScene | undefined;
  let sawAction = false, sawContent = false;
  const actors: ActorStmt[] = [];
  const names = new Map<string, ActorStmt>();
  const actions: CheckedAction[] = [];
  let parentsChecked = false;
  try {
    for (const s of doc.statements) {
      const fail = (m: string): never => { throw new Stop({ line: s.line, col: s.col, message: m }); };
      switch (s.kind) {
        case 'version':
          if (sawContent || !s.ok) fail('expected initial mdgl 0.1');
          break;
        case 'unknown':
          fail('unsupported statement (expected mdgl, scene, actor or @)');
          break;
        case 'scene':
          if (scene) fail('duplicate scene');
          sawContent = true;
          scene = checkScene(s);
          break;
        case 'actor':
          sawContent = true;
          if (!scene) fail('scene must precede actors');
          if (sawAction) fail('actors must precede actions');
          if (actors.length >= MAX_ACTORS) fail('actor limit 64 exceeded');
          checkActor(s, new Set(names.keys()));
          actors.push(s);
          names.set(s.name, s);
          break;
        case 'action': {
          sawContent = true;
          if (!scene) fail('scene must precede actions');
          if (!parentsChecked) { checkParents(actors); parentsChecked = true; }
          sawAction = true;
          if (actions.length >= MAX_ACTIONS) fail('action limit 1024 exceeded');
          const ca = checkAction(s, names);
          for (const p of actions) {
            if (p.actor === ca.actor && p.property === ca.property && p.beginNs < ca.endNs && ca.beginNs < p.endNs) fail(`overlapping ${ca.property} actions on ${ca.actor}`);
          }
          actions.push(ca);
          break;
        }
      }
    }
    if (!parentsChecked) checkParents(actors);
    if (doc.syntax) throw new Stop(doc.syntax);
    if (!scene) throw new Stop({ line: 1, col: 1, message: 'missing scene' });
    const end = actions.reduce((m, a) => Math.max(m, a.endNs), 0);
    scene.duration = scene.period ?? end;
    if (scene.fallback.kind === 'at' && scene.fallback.ns > scene.duration) throw new Stop({ line: scene.line, col: 1, message: 'fallback time exceeds the simple duration' });
    return { ok: true, doc: { scene, actors, actions } };
  } catch (e) {
    if (e instanceof Stop) return stop(e.d);
    throw e;
  }
}

/** Parse and check; returns the checked, source-located scene model or diagnostics. */
export function parseChecked(source: string): ParseResult { return checkDocument(parse(source)); }

/** Compat API: `[]` means the source is valid; otherwise the first diagnostic. */
export function check(source: string): Diag[] {
  if (typeof source !== 'string') throw new TypeError('mdgl.check: source must be a string');
  const r = parseChecked(source);
  return r.ok ? [] : r.diagnostics;
}
void bytes;

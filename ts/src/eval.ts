// MDGL 0.1 evaluator + terminal-cell renderer. Pure and seekable: compile() a checked
// document once, then frameNs()/fallbackFrame() are functions of (scene, time) only.
// Implemented from SPEC.md alone. Choices SPEC leaves open are marked IMPL-DEFINED.

import { CheckedAction, CheckedDocument, parseChecked } from './check';
import { Coord, Diag, Point, Value, decimalToNs } from './parse';
import { cellRune, graphemes } from './unicode';

export interface Cell { r: string; fg: string; bg: string }
export interface Frame { width: number; height: number; cells: Cell[][]; done?: boolean }

type Vec = [number, number, number];
type Mat = number[]; // column-major 4x4

const I4 = (): Mat => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const mul = (a: Mat, b: Mat): Mat => {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) for (let k = 0; k < 4; k++) o[c * 4 + r] += a[k * 4 + r] * b[c * 4 + k];
  return o;
};
const trans = (x: number, y: number, z: number): Mat => { const m = I4(); m[12] = x; m[13] = y; m[14] = z; return m; };
const scaleM = (s: number): Mat => { const m = I4(); m[0] = s; m[5] = s; m[10] = s; return m; };
const rotM = (xd: number, yd: number, zd: number): Mat => {
  const [x, y, z] = [xd, yd, zd].map((d) => (d * Math.PI) / 180);
  const [cx, sx, cy, sy, cz, sz] = [Math.cos(x), Math.sin(x), Math.cos(y), Math.sin(y), Math.cos(z), Math.sin(z)];
  // SPEC rows (intrinsic XYZ, R = Rx*Ry*Rz)
  const rows = [
    [cy * cz, -cy * sz, sy, 0],
    [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy, 0],
    [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy, 0],
    [0, 0, 0, 1],
  ];
  const m = new Array(16);
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) m[c * 4 + r] = rows[r][c];
  return m;
};
const xf = (m: Mat, v: Vec): [number, number, number, number] => {
  const o: [number, number, number, number] = [0, 0, 0, 0];
  for (let r = 0; r < 4; r++) o[r] = m[r] * v[0] + m[4 + r] * v[1] + m[8 + r] * v[2] + m[12 + r];
  return o;
};

/** half away from zero */
const rnd = (v: number): number => (v < 0 ? -Math.floor(-v + 0.5) : Math.floor(v + 0.5));

// ---- easing (SPEC: CSS cubic-bezier controls with numeric X solve; bounce = standard ease-out-bounce) ----
function bezier(x1: number, y1: number, x2: number, y2: number): (u: number) => number {
  const cx = (s: number): number => 3 * (1 - s) * (1 - s) * s * x1 + 3 * (1 - s) * s * s * x2 + s * s * s;
  const cy = (s: number): number => 3 * (1 - s) * (1 - s) * s * y1 + 3 * (1 - s) * s * s * y2 + s * s * s;
  return (u) => {
    if (u <= 0) return 0;
    if (u >= 1) return 1;
    let lo = 0, hi = 1;
    for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; if (cx(m) < u) lo = m; else hi = m; }
    return cy((lo + hi) / 2);
  };
}
const bounce = (u: number): number => {
  const n1 = 7.5625, d1 = 2.75;
  if (u < 1 / d1) return n1 * u * u;
  if (u < 2 / d1) { u -= 1.5 / d1; return n1 * u * u + 0.75; }
  if (u < 2.5 / d1) { u -= 2.25 / d1; return n1 * u * u + 0.9375; }
  u -= 2.625 / d1;
  return n1 * u * u + 0.984375;
};
const EASE: Record<string, (u: number) => number> = {
  linear: (u) => u,
  ease: bezier(0.25, 0.1, 0.25, 1),
  'ease-in': bezier(0.42, 0, 1, 1),
  'ease-out': bezier(0, 0, 0.58, 1),
  'ease-in-out': bezier(0.42, 0, 0.58, 1),
  bounce,
};

// ---- colours ----
const RGB: Record<string, [number, number, number]> = {
  normal: [255, 255, 255], white: [255, 255, 255], black: [0, 0, 0], red: [255, 0, 0], green: [0, 255, 0], yellow: [255, 255, 0],
  blue: [0, 0, 255], magenta: [255, 0, 255], cyan: [0, 255, 255], accent: [0, 255, 255],
};
const hex2 = (n: number): string => n.toString(16).padStart(2, '0');
/** IMPL-DEFINED rounding: nearest, ties up (SPEC gives only the source-over formula). */
function blend(fg: string, alpha: number, bg: string): string {
  if (alpha >= 1) return fg;
  const s = RGB[fg] ?? RGB.normal;
  let d: number[] = [0, 0, 0];
  if (bg !== '') { if (bg[0] === '#') d = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16)); else d = RGB[bg] ?? [0, 0, 0]; }
  return '#' + [0, 1, 2].map((i) => hex2(Math.max(0, Math.min(255, Math.floor(s[i] * alpha + d[i] * (1 - alpha) + 0.5))))).join('');
}

// ---- model ----
interface Act {
  name: string; index: number; z: number; parent: Act | null; shape: CheckedDocument['actors'][number]['shape'];
  w: number; h: number; clusters: string[];
  atPoint: Point; anchorPoint?: Point; color: string;
  acts: CheckedAction[];
}
export interface Compiled {
  width: number; height: number; fps: number;
  /** simple duration in ns */
  durationNs: number; periodNs?: number; repeat: number;
  fallback: CheckedDocument['scene']['fallback'];
  actors: Act[];
  order: Act[];
}

export type CompileResult = { ok: true; scene: Compiled } | { ok: false; diagnostics: Diag[] };

function sizeOf(sh: Act['shape']): [number, number, string[]] {
  if (sh.kind === 'text') { const g = graphemes(sh.text); return [g.length, 1, g]; }
  if (sh.kind === 'rect') return [sh.width, sh.height, []];
  if (sh.kind === 'circle') return [2 * sh.radius, 2 * sh.radius, []];
  return [sh.size, sh.size, []];
}

export function compileDocument(doc: CheckedDocument): Compiled {
  const by = new Map<string, Act>();
  const actors: Act[] = doc.actors.map((a, index) => {
    const [w, h, clusters] = sizeOf(a.shape);
    const act: Act = { name: a.name, index, z: a.z ?? 0, parent: null, shape: a.shape, w, h, clusters, atPoint: a.at, anchorPoint: a.anchor, color: a.color ?? 'normal', acts: [] };
    by.set(a.name, act);
    return act;
  });
  doc.actors.forEach((a, i) => { if (a.parent !== undefined) actors[i].parent = by.get(a.parent) as Act; });
  const sorted = [...doc.actions].sort((p, q) => p.beginNs - q.beginNs); // stable: source order breaks ties
  for (const a of sorted) (by.get(a.actor) as Act).acts.push(a);
  const s = doc.scene;
  const order = [...actors].sort((p, q) => p.z - q.z || p.index - q.index);
  return { width: s.width, height: s.height, fps: s.fps, durationNs: s.duration, periodNs: s.period, repeat: s.repeat, fallback: s.fallback, actors, order };
}

export function compile(source: string): CompileResult {
  const r = parseChecked(source);
  return r.ok ? { ok: true, scene: compileDocument(r.doc) } : { ok: false, diagnostics: r.diagnostics };
}

// ---- argument helpers ----
const arg = (a: CheckedAction, k: string): Value | undefined => a.args.find((g) => g.key === k)?.value;
const has = (a: CheckedAction, k: string): boolean => a.args.some((g) => g.key === k);
const secs = (v: Value | undefined): number => decimalToNs((v as { raw: string }).raw.replace(/^\+/, '').replace(/s$/, ''));
const num = (v: Value | undefined): number => (v as { value: number }).value;
const deg = (v: Value | undefined): number => { const n = v as { value: number; suffix: string }; return n.suffix === 'rad' ? (n.value * 180) / Math.PI : n.value; };

function coord(c: Coord, size: number, box: number, anchorNames: [string, string]): number {
  if (c.kind === 'num') return c.percent ? (c.value / 100) * (box - size) : c.value;
  const rem = box - size;
  const base = c.name === anchorNames[0] ? 0 : c.name === anchorNames[1] ? rem : rem / 2;
  return base + c.offset;
}
const resolve = (p: Point, w: number, h: number, bw: number, bh: number): [number, number] =>
  [coord(p.x, w, bw, ['left', 'right']), coord(p.y, h, bh, ['top', 'bottom'])];

interface State { opacity: number; x: number; y: number; scale: number; color: string; reveal: number; count: number | null; rot: Vec }

function evalActor(sc: Compiled, a: Act, T: number): State {
  const box: [number, number] = a.parent ? [a.parent.w, a.parent.h] : [sc.width, sc.height];
  const [x0, y0] = resolve(a.atPoint, a.w, a.h, box[0], box[1]);
  const st: State = { opacity: 1, x: x0, y: y0, scale: 1, color: a.color, reveal: 1, count: null, rot: [0, 0, 0] };
  const done: Record<string, boolean> = {};
  for (const ac of a.acts) {
    const b = ac.beginNs, e = ac.endNs, dur = ac.durNs;
    const started = T >= b, over = T >= e;
    const ease = EASE[(arg(ac, 'ease') as { value: string } | undefined)?.value ?? 'linear'];
    const p = started && !over && dur > 0 ? ease((T - b) / dur) : over ? 1 : 0;
    const prop = ac.property;
    if (done[prop]) continue;
    if (T < b && !(ac.verb === 'fade' || ac.verb === 'wipe' || ac.verb === 'type' || ac.verb === 'slide')) { done[prop] = true; continue; }
    switch (ac.verb) {
      case 'fade': {
        const inn = has(ac, 'in');
        st.opacity = over ? (inn ? 1 : 0) : !started ? (inn ? 0 : st.opacity) : inn ? p : 1 - p;
        break;
      }
      case 'blink': {
        if (started && !over) { const half = dur / (2 * num(arg(ac, 'times'))); if (Math.floor((T - b) / half) % 2 === 1) st.opacity = 0; }
        break;
      }
      case 'wipe': {
        const inn = has(ac, 'in');
        st.count = null;
        st.reveal = over ? (inn ? 1 : 0) : !started ? (inn ? 0 : st.reveal) : inn ? p : st.reveal * (1 - p);
        break;
      }
      case 'type': {
        const per = secs(arg(ac, 'per_char'));
        st.count = over ? a.clusters.length : !started ? 0 : Math.min(a.clusters.length, Math.floor((T - b) / per));
        st.reveal = 1;
        break;
      }
      case 'move': {
        const [tx, ty] = resolve((arg(ac, 'to') as { value: Point }).value, a.w, a.h, box[0], box[1]);
        if (over) { st.x = tx; st.y = ty; } else { st.x += (tx - st.x) * p; st.y += (ty - st.y) * p; }
        break;
      }
      case 'slide': {
        const edge = (arg(ac, 'to') as { value: string }).value;
        const inn = has(ac, 'in');
        let ex = st.x, ey = st.y;
        if (edge === 'left') ex = -a.w; else if (edge === 'right') ex = box[0]; else if (edge === 'top') ey = -a.h; else ey = box[1];
        if (inn) { if (over) { /* ends at current origin */ } else { st.x = ex + (st.x - ex) * p; st.y = ey + (st.y - ey) * p; } }
        else if (over) { st.x = ex; st.y = ey; } else if (started) { st.x += (ex - st.x) * p; st.y += (ey - st.y) * p; }
        break;
      }
      case 'scale': {
        const t = num(arg(ac, 'to'));
        st.scale = over ? t : st.scale + (t - st.scale) * p;
        break;
      }
      case 'color': {
        const t = (arg(ac, 'to') as { value: string }).value;
        if (over || p >= 0.5) st.color = t;
        break;
      }
      case 'rotate': {
        ['x', 'y', 'z'].forEach((k, i) => { if (has(ac, k)) { const t = deg(arg(ac, k)); st.rot[i] = over ? t : st.rot[i] + (t - st.rot[i]) * p; } });
        break;
      }
    }
    if (T < b) done[prop] = true;
  }
  return st;
}

// ---- raster ----
const BIT = [[1, 8], [2, 16], [4, 32], [64, 128]]; // [row][col]

class Grid {
  cells: Cell[][];
  constructor(public w: number, public h: number) {
    this.cells = Array.from({ length: h }, () => Array.from({ length: w }, () => ({ r: ' ', fg: 'normal', bg: '' })));
  }
  put(col: number, row: number, r: string, color: string, alpha: number): void {
    if (col < 0 || row < 0 || col >= this.w || row >= this.h || r === ' ' || alpha <= 0) return;
    const c = this.cells[row][col];
    c.r = r;
    c.fg = alpha >= 1 ? color : blend(color, alpha, c.bg);
  }
}
const q9 = (v: number): number => Math.round(v * 1e9) / 1e9;

function worldMatrices(sc: Compiled, T: number): Map<Act, { m: Mat; st: State; alpha: number; frac: number; ax: number; ay: number }> {
  const out = new Map<Act, { m: Mat; st: State; alpha: number; frac: number; ax: number; ay: number }>();
  const get = (a: Act): { m: Mat; st: State; alpha: number; frac: number; ax: number; ay: number } => {
    const hit = out.get(a);
    if (hit) return hit;
    const st = evalActor(sc, a, T);
    const par = a.parent ? get(a.parent) : null;
    let ax = a.w / 2, ay = a.h / 2;
    if (a.anchorPoint) { ax = coord(a.anchorPoint.x, 0, a.w, ['left', 'right']); ay = coord(a.anchorPoint.y, 0, a.h, ['top', 'bottom']); }
    let local = mul(trans(st.x + ax, -2 * (st.y + ay), 0), mul(rotM(st.rot[0], st.rot[1], st.rot[2]), mul(scaleM(st.scale), trans(-ax, 2 * ay, 0))));
    if (par) local = mul(par.m, local);
    const fr = st.count !== null ? (a.clusters.length ? st.count / a.clusters.length : 1) : st.reveal;
    const r = { m: local, st, alpha: st.opacity * (par ? par.alpha : 1), frac: fr * (par ? par.frac : 1), ax, ay };
    out.set(a, r);
    return r;
  };
  for (const a of sc.actors) get(a);
  return out;
}

/** cell-space point (col,row) of a local cell-space point through the model matrix */
function toCell(m: Mat, cx: number, cy: number): [number, number] {
  const p = xf(m, [cx, -2 * cy, 0]);
  return [p[0], -p[1] / 2];
}
const dotOf = (col: number, row: number): [number, number] => [2 * col - 0.5, 4 * row - 0.5];

function line(dots: Set<number>, W: number, H: number, a: [number, number], b: [number, number]): void {
  let x0 = q9(a[0]), y0 = q9(a[1]), x1 = q9(b[0]), y1 = q9(b[1]);
  // clip the quantized segment to the stage dot box [0,2W-1]x[0,4H-1] before stepping (Liang-Barsky)
  let t0 = 0, t1 = 1;
  const dx0 = x1 - x0, dy0 = y1 - y0;
  for (const [p, qd] of [[-dx0, x0], [dx0, 2 * W - 1 - x0], [-dy0, y0], [dy0, 4 * H - 1 - y0]] as Array<[number, number]>) {
    if (p === 0) { if (qd < 0) return; continue; }
    const r = qd / p;
    if (p < 0) { if (r > t1) return; if (r > t0) t0 = r; } else { if (r < t0) return; if (r < t1) t1 = r; }
  }
  [x0, y0, x1, y1] = [x0 + dx0 * t0, y0 + dy0 * t0, x0 + dx0 * t1, y0 + dy0 * t1];
  const n = Math.min(800, Math.max(1, Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0))))); // reference profile: capped 800, min 1
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const dx = Math.round(x0 + (x1 - x0) * t), dy = Math.round(y0 + (y1 - y0) * t);
    if (dx >= 0 && dy >= 0 && dx < W * 2 && dy < H * 4) dots.add(dy * W * 2 + dx);
  }
}

function paintDots(g: Grid, dots: Set<number>, color: string, alpha: number): void {
  const bits = new Map<number, number>();
  for (const d of dots) {
    const dy = Math.floor(d / (g.w * 2)), dx = d % (g.w * 2);
    const key = Math.floor(dy / 4) * g.w + Math.floor(dx / 2);
    bits.set(key, (bits.get(key) ?? 0) | BIT[dy % 4][dx % 2]);
  }
  for (const [key, b] of bits) g.put(key % g.w, Math.floor(key / g.w), String.fromCodePoint(0x2800 + b), color, alpha);
}

function clipLine(p0: number[], p1: number[]): [number[], number[]] | null {
  let t0 = 0, t1 = 1;
  for (let axis = 0; axis < 3; axis++) {
    for (const sgn of [1, -1]) {
      const d0 = p0[3] - sgn * p0[axis], d1 = p1[3] - sgn * p1[axis]; // >= 0 inside: w - s*c
      if (d0 < 0 && d1 < 0) return null;
      if (d0 < 0) t0 = Math.max(t0, d0 / (d0 - d1));
      else if (d1 < 0) t1 = Math.min(t1, d0 / (d0 - d1));
    }
  }
  if (t0 > t1) return null;
  const at = (t: number): number[] => p0.map((v, i) => v + (p1[i] - v) * t);
  return [at(t0), at(t1)];
}

function renderActor(sc: Compiled, g: Grid, a: Act, w: { m: Mat; st: State; alpha: number; frac: number }): void {
  const color = w.st.color, alpha = w.alpha;
  if (alpha <= 0 || w.frac <= 0 && a.shape.kind !== 'text') return;
  const sh = a.shape;
  if (sh.kind === 'text') {
    const n = a.clusters.length;
    const shown = w.st.count !== null ? Math.min(w.st.count, Math.floor(w.frac * n + 1e-9) === n ? n : Math.floor(w.frac * n + 1e-9)) : Math.floor(w.frac * n + 1e-9);
    const cnt = w.st.count !== null && w.frac >= 1 ? w.st.count : shown;
    for (let i = 0; i < Math.min(cnt, n); i++) {
      const [c, r] = toCell(w.m, i, 0);
      g.put(rnd(c), rnd(r), cellRune(a.clusters[i]), color, alpha);
    }
    return;
  }
  const dots = new Set<number>();
  const cellToDot = (cx: number, cy: number): [number, number] => { const [c, r] = toCell(w.m, cx, cy); return dotOf(c, r); };
  // local dot (dx,dy) -> local cell-space centre -> model -> dot
  const dotThrough = (dx: number, dy: number): [number, number] => cellToDot((dx + 0.5) / 2, (dy + 0.5) / 4);
  const clipX = w.frac < 1 ? w.frac * 2 * a.w : Infinity; // IMPL-DEFINED left-to-right reveal on local dot columns
  if (sh.kind === 'rect') {
    const W = 2 * sh.width - 1, H = 4 * sh.height - 1;
    const corners: Array<[number, number]> = [[0, 0], [W, 0], [W, H], [0, H]];
    for (let i = 0; i < 4; i++) line(dots, g.w, g.h, dotThrough(...corners[i]), dotThrough(...corners[(i + 1) % 4]));
  } else if (sh.kind === 'circle') {
    const rx = 2 * sh.radius - 0.5, ry = 4 * sh.radius - 0.5; // dot radii of the 2N x 2N cell bounding box
    // 720 chords, k=1..720, angle k*pi/360, starting at the rightmost point (reference profile, not SPEC)
    let prev = dotThrough(2 * rx, ry);
    for (let k = 1; k <= 720; k++) {
      const t = (k * Math.PI) / 360;
      const lx = rx + rx * Math.cos(t), ly = ry + ry * Math.sin(t);
      const cur = dotThrough(lx, ly);
      if (lx <= clipX) line(dots, g.w, g.h, prev, cur);
      prev = cur;
    }
  } else {
    cubeDots(dots, g, a, sh.size, w.m);
  }
  paintDots(g, dots, color, alpha);
  if (sh.kind === 'rect' && sh.title) {
    const t = graphemes(sh.title);
    for (let i = 0; i < Math.min(t.length, sh.width - 2); i++) {
      const [c, r] = toCell(w.m, 1 + i, 0);
      g.put(rnd(c), rnd(r), cellRune(t[i]), color, alpha);
    }
  }
}

function cubeDots(dots: Set<number>, g: Grid, a: Act, size: number, M: Mat): void {
  const n = size;
  const verts: Vec[] = [];
  for (const dx of [0, 1]) for (const dy of [0, 1]) for (const dz of [0, 1]) verts.push([n / 2 + (dx ? n / 2 : -n / 2), -n + (dy ? n / 2 : -n / 2), dz ? n / 2 : -n / 2]);
  const centre = xf(M, [n / 2, -n, 0]);
  const tm = trans(-centre[0], -centre[1], -(centre[2] + 3 * n));
  const fov = (50 * Math.PI) / 180, qq = 1 / Math.tan(fov / 2), asp = n / (2 * n), near = 0.1, far = 1000;
  const P: Mat = [qq / asp, 0, 0, 0, 0, qq, 0, 0, 0, 0, -(far + near) / (far - near), -1, 0, 0, (-2 * far * near) / (far - near), 0];
  const PV = mul(P, tm);
  const clip = verts.map((v) => xf(PV, xf(M, v).slice(0, 3) as Vec));
  // viewport: n x n cells centred on the transformed cube centre (cell space)
  const [ccol, crow] = (() => { const p = centre; return [p[0], -p[1] / 2] as [number, number]; })();
  const left = ccol - n / 2, top = crow - n / 2;
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < 8; i++) for (const bit of [1, 2, 4]) if (!(i & bit)) edges.push([i, i | bit]);
  for (const [i, j] of edges) {
    const c = clipLine(clip[i], clip[j]);
    if (!c) continue;
    const pr = c.map((p) => {
      const ndcX = p[0] / p[3], ndcY = p[1] / p[3];
      const col = left + ((ndcX + 1) * n) / 2, row = top + ((1 - ndcY) * n) / 2;
      return dotOf(col, row);
    });
    line(dots, g.w, g.h, pr[0], pr[1]);
  }
}

function compose(sc: Compiled, T: number, W: number, H: number): Grid {
  const g = new Grid(Math.min(W, sc.width), Math.min(H, sc.height));
  // paint on the full stage then crop, so clipping/clamping stays stage-relative
  const full = new Grid(sc.width, sc.height);
  const wm = worldMatrices(sc, T);
  for (const a of sc.order) renderActor(sc, full, a, wm.get(a) as { m: Mat; st: State; alpha: number; frac: number });
  for (let r = 0; r < g.h; r++) for (let c = 0; c < g.w; c++) g.cells[r][c] = full.cells[r][c];
  return g;
}

/** Frame at absolute time `tNs` (integer nanoseconds). `Done` per SPEC; repeat semantics included. */
export function frameNs(sc: Compiled, tNs: number, width = sc.width, height = sc.height): Frame {
  const D = sc.durationNs;
  let local = tNs, done = D === 0;
  if (D > 0) {
    const total = sc.repeat === Infinity ? Infinity : D * sc.repeat;
    if (tNs >= total) { local = D; done = true; } else { local = tNs % D; }
  } else local = 0;
  const g = compose(sc, local, width, height);
  return { width: g.w, height: g.h, cells: g.cells, done };
}

/** Fallback sample of the simple timeline (no repeat); `done` is omitted. */
export function fallbackFrame(sc: Compiled, width = sc.width, height = sc.height): Frame {
  const f = sc.fallback;
  const T = f.kind === 'start' ? 0 : f.kind === 'end' ? Infinity : f.ns;
  const g = compose(sc, T, width, height);
  return { width: g.w, height: g.h, cells: g.cells };
}

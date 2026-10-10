// Pinned Unicode compatibility profile (NOT a normative MDGL rule): UAX #29 extended
// grapheme clusters, Unicode 15.0.0 (no GB9c), from the generated tables in
// unicode-tables.ts (scripts/gen-unicode.js). No runtime Intl dependency.
import { EXT_PICT, GCB, IGNORABLE, MARK, VS16_BASE, WIDE } from './unicode-tables';

export const UNICODE_VERSION = '15.0.0';

/** Class of `cp` in a flat [start,end,class] triple table, or -1. */
function lookup(t: number[], cp: number): number {
  let lo = 0, hi = t.length / 3 - 1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1, s = t[3 * m];
    if (cp < s) hi = m - 1;
    else if (cp > t[3 * m + 1]) lo = m + 1;
    else return t[3 * m + 2];
  }
  return -1;
}
const [PREPEND, CR, LF, CONTROL, EXTEND, ZWJ, RI, SPACING, L, V, T, LV, LVT] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const OTHER = 13;

/** Cluster boundaries as UTF-16 index pairs [start, end). */
export function graphemeRanges(s: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  let start = 0, prev = -1, ri = 0, pict = 0 /* 0 none, 1 ExtPict Extend*, 2 +ZWJ */;
  for (let i = 0; i < s.length;) {
    const cp = s.codePointAt(i) as number;
    const n = cp > 0xffff ? 2 : 1;
    const g0 = lookup(GCB, cp), g = g0 < 0 ? OTHER : g0, ep = lookup(EXT_PICT, cp) >= 0;
    if (prev >= 0) {
      let brk: boolean;
      if (prev === CR && g === LF) brk = false;
      else if (prev === CONTROL || prev === CR || prev === LF || g === CONTROL || g === CR || g === LF) brk = true;
      else if (prev === L && (g === L || g === V || g === LV || g === LVT)) brk = false;
      else if ((prev === LV || prev === V) && (g === V || g === T)) brk = false;
      else if ((prev === LVT || prev === T) && g === T) brk = false;
      else if (g === EXTEND || g === ZWJ || g === SPACING || prev === PREPEND) brk = false;
      else if (pict === 2 && ep) brk = false;
      else if (prev === RI && g === RI) brk = ri % 2 === 0;
      else brk = true;
      if (brk) { out.push([start, i]); start = i; }
    }
    // state for the next boundary decision
    if (prev < 0 || start === i) { ri = 0; pict = 0; }
    ri = g === RI ? ri + 1 : 0;
    pict = ep ? 1 : g === EXTEND && pict === 1 ? 1 : g === ZWJ && pict === 1 ? 2 : 0;
    prev = g;
    i += n;
  }
  if (s.length) out.push([start, s.length]);
  return out;
}

export function graphemes(s: string): string[] { return graphemeRanges(s).map(([a, b]) => s.slice(a, b)); }
export function graphemeCount(s: string): number { return graphemeRanges(s).length; }
export const isMark = (cp: number): boolean => lookup(MARK, cp) >= 0;
export const isWide = (cp: number): boolean => lookup(WIDE, cp) >= 0;

export const isIgnorable = (cp: number): boolean => lookup(IGNORABLE, cp) >= 0;
const CF = /^\p{Cf}$/u;
const first = (cluster: string): string => {
  const cps = Array.from(cluster);
  return cps.find((c) => !isMark(c.codePointAt(0) as number)) ?? cps[0];
};

/** Terminal width of one cluster: 0 (only marks / default-ignorable / format characters), 2 (first non-mark rune East Asian W/F or a regional indicator, or an emoji-style VS16/keycap sequence), else 1. */
export function clusterWidth(cluster: string): 0 | 1 | 2 {
  const cps = Array.from(cluster, (c) => c.codePointAt(0) as number);
  if (cps.every((c) => isMark(c) || isIgnorable(c) || CF.test(String.fromCodePoint(c)))) return 0;
  const f = first(cluster).codePointAt(0) as number;
  if (isWide(f) || lookup(GCB, f) === RI) return 2; // RI: single and paired flag clusters are width 2 (reference contract)
  const i = cps.indexOf(f);
  if (cps[i + 1] === 0xfe0f && lookup(VS16_BASE, f) >= 0) return 2;
  return 1;
}

/** SPEC Cells: the first non-mark rune of a cluster (even if zero-width Cf/default-ignorable); U+FFFD when the cluster is wider than one cell; a blank only for an all-mark cluster. Every cluster consumes exactly one cell, so later cells never shift. */
export function cellRune(cluster: string): string {
  if (clusterWidth(cluster) === 2) return '�';
  const r = Array.from(cluster).find((c) => !isMark(c.codePointAt(0) as number));
  return r ?? ' ';
}

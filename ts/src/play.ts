// Terminal playback over the pure evaluator (SPEC "Limits and API": play uses absolute
// elapsed time, dirty cells and DEC synchronized output 2026, stops its timer on finite
// completion or interrupt; redirected output and reduced motion use the fallback frame).
// No I/O of its own: the caller injects the writer, clock and interrupt source.

import { Cell, Compiled, fallbackFrame, frameNs } from './eval';

export interface Clock {
  /** monotonic milliseconds */
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}
export interface PlayDeps {
  /** Write one chunk; may throw (e.g. EPIPE). One call is one atomic frame update. */
  write(chunk: string): void;
  clock: Clock;
  /** Subscribe to asynchronous output errors; returns the unsubscribe function. */
  onWriteError?(cb: (e: unknown) => void): () => void;
  /** Subscribe to interrupts; cb receives the exit code (130 SIGINT, 143 SIGTERM). Returns unsubscribe. */
  onInterrupt?(cb: (code: number) => void): () => void;
}
export type PlayEnd = 'done' | 'interrupt' | 'write-error' | 'stopped';
export interface PlayResult { code: number; reason: PlayEnd; error?: unknown }
export interface PlayHandle { done: Promise<PlayResult>; stop(): void }

export const SYNC_BEGIN = '\x1b[?2026h';
export const SYNC_END = '\x1b[?2026l';
export const HIDE_CURSOR = '\x1b[?25l';
export const SHOW_CURSOR = '\x1b[?25h';
export const RESET = '\x1b[0m';

const FG: Record<string, number> = { black: 30, red: 31, green: 32, yellow: 33, blue: 34, magenta: 35, cyan: 36, white: 37, accent: 36 };

/** Never let a cell glyph act as a terminal escape: controls, DEL and C1 become a space. */
export function sanitizeRune(r: string): string {
  const cp = r.codePointAt(0) ?? 32;
  return cp < 0x20 || (cp >= 0x7f && cp <= 0x9f) || cp === 0x2028 || cp === 0x2029 ? ' ' : r;
}

function color(c: string, bg: boolean): string {
  if (c === '' || c === 'normal') return bg ? '49' : '39';
  if (c[0] === '#') return `${bg ? 48 : 38};2;${parseInt(c.slice(1, 3), 16)};${parseInt(c.slice(3, 5), 16)};${parseInt(c.slice(5, 7), 16)}`;
  return String((FG[c] ?? 37) + (bg ? 10 : 0));
}
const style = (c: Cell): string => `\x1b[0;${color(c.fg, false)};${color(c.bg, true)}m`;
const same = (a: Cell, b: Cell): boolean => a.r === b.r && a.fg === b.fg && a.bg === b.bg;

/** Plain text of a frame (one row per line, trailing newline); no ANSI. */
export function plainText(cells: Cell[][]): string {
  return cells.map((row) => row.map((c) => sanitizeRune(c.r)).join('')).join('\n') + '\n';
}
/** The fallback frame as plain text, for redirected output and reduced motion. */
export function plainFallback(scene: Compiled): string { return plainText(fallbackFrame(scene).cells); }

/** First frame: all rows, each ended by CRLF, leaving the cursor at column 0 below the frame. */
function fullDraw(cells: Cell[][]): string {
  let out = '';
  for (const row of cells) {
    let last = '';
    for (const c of row) { const s = style(c); if (s !== last) { out += s; last = s; } out += sanitizeRune(c.r); }
    out += RESET + '\r\n';
  }
  return out;
}
/** Changed cells only; the cursor is parked below the frame before and after. */
function diffDraw(prev: Cell[][], next: Cell[][]): string {
  const h = next.length;
  let out = '';
  for (let r = 0; r < h; r++) {
    const a = prev[r], b = next[r];
    for (let c = 0; c < b.length;) {
      if (same(a[c], b[c])) { c++; continue; }
      let e = c;
      while (e < b.length && !same(a[e], b[e])) e++;
      const up = h - r;
      out += `\x1b[${up}A\x1b[${c + 1}G`;
      let last = '';
      for (let i = c; i < e; i++) { const s = style(b[i]); if (s !== last) { out += s; last = s; } out += sanitizeRune(b[i].r); }
      out += RESET + `\x1b[${up}B\r`;
      c = e;
    }
  }
  return out;
}

/**
 * Start playback. Frame time is always computed from the monotonic clock (elapsed since start),
 * never accumulated from tick counts, so late timers drop frames without changing state.
 * Finite scenes stop when the evaluator reports done; every exit path clears the timer,
 * unsubscribes listeners and restores the cursor and attributes exactly once.
 */
export function play(scene: Compiled, deps: PlayDeps): PlayHandle {
  const frameMs = 1000 / scene.fps;
  const t0 = deps.clock.now();
  let timer: unknown;
  let prev: Cell[][] | null = null;
  let finished = false;
  const unsub: Array<() => void> = [];
  let resolve!: (r: PlayResult) => void;
  const done = new Promise<PlayResult>((res) => { resolve = res; });

  const finish = (code: number, reason: PlayEnd, error?: unknown): void => {
    if (finished) return;
    finished = true;
    if (timer !== undefined) deps.clock.clearTimeout(timer);
    timer = undefined;
    for (const u of unsub.splice(0)) { try { u(); } catch { /* ignore */ } }
    try { deps.write(RESET + SHOW_CURSOR); } catch (e) { if (error === undefined) error = e; }
    resolve(error === undefined ? { code, reason } : { code, reason, error });
  };
  const tick = (): void => {
    timer = undefined;
    if (finished) return;
    const elapsed = deps.clock.now() - t0;
    const f = frameNs(scene, Math.floor(elapsed * 1e6));
    try {
      const body = prev === null ? fullDraw(f.cells) : diffDraw(prev, f.cells);
      if (body !== '' || prev === null) deps.write(prev === null ? SYNC_BEGIN + HIDE_CURSOR + body + SYNC_END : SYNC_BEGIN + body + SYNC_END);
      prev = f.cells;
    } catch (e) { finish(1, 'write-error', e); return; }
    if (f.done) { finish(0, 'done'); return; }
    const next = (Math.floor(elapsed / frameMs) + 1) * frameMs;
    timer = deps.clock.setTimeout(tick, Math.max(1, next - elapsed));
  };

  if (deps.onWriteError) unsub.push(deps.onWriteError((e) => finish(1, 'write-error', e)));
  if (deps.onInterrupt) unsub.push(deps.onInterrupt((code) => finish(code, 'interrupt')));
  tick();
  return { done, stop: () => finish(0, 'stopped') };
}

// MDGL 0.0.1 -- SUBSET limit/header checker. NOT a conformant MDGL implementation.
// Checks only: input <= 256 KiB, line <= 16 KiB, scene header (width 1..200,
// height 1..60, fallback; no unknown/duplicate keys), statement order,
// <= 64 actors, <= 1024 actions. Does NOT parse actor/action bodies or check
// grammar, timing, references or rendering. An empty result means
// "no limit/header problems found", NOT "valid MDGL". Reference: the Go module.
// Spec: https://github.com/enmaq/mdgl/blob/main/SPEC.md

declare const Buffer: { byteLength(s: string, enc: string): number };

export const VERSION: string = '0.2.0';
const MAX_INPUT = 256 * 1024;
const MAX_LINE = 16384;
const MAX_ACTORS = 64;
const MAX_ACTIONS = 1024;
const KEYS = ['width', 'height', 'period', 'repeat', 'fallback', 'fps'];

/** One diagnostic. `line` is 1-based. */
export interface Diag {
  line: number;
  col: number;
  message: string;
}
/** Alias of {@link Diag}. */
export type Problem = Diag;
/** Result of {@link check}: an empty array means no limit/header problems. */
export type CheckResult = Diag[];

const d = (line: number, message: string): Diag[] => [{ line, col: 1, message }];
const bytes = (s: string): number => Buffer.byteLength(s, 'utf8');

function sceneHeader(n: number, rest: string): Diag[] {
  const seen = new Map<string, string>();
  for (const tok of rest.split(/[ \t\r]+/).filter(Boolean)) {
    const i = tok.indexOf('=');
    if (i <= 0 || i === tok.length - 1) return d(n, `malformed scene attribute ${JSON.stringify(tok)}`);
    const k = tok.slice(0, i);
    if (!KEYS.includes(k)) return d(n, `unknown scene attribute ${JSON.stringify(k)}`);
    if (seen.has(k)) return d(n, `duplicate scene attribute ${JSON.stringify(k)}`);
    seen.set(k, tok.slice(i + 1));
  }
  const out: Diag[] = ['width', 'height', 'fallback']
    .filter((k) => !seen.has(k))
    .map((k) => ({ line: n, col: 1, message: `scene header missing ${k}=` }));
  if (out.length) return out;
  for (const [k, max] of [['width', 200], ['height', 60]] as Array<[string, number]>) {
    const v = seen.get(k) as string;
    if (!/^[0-9]{1,9}$/.test(v) || Number(v) < 1 || Number(v) > max) {
      return d(n, `${k} must be an integer 1..${max}`);
    }
  }
  return [];
}

/**
 * Subset check. Returns diagnostics; [] means "no limit/header problems found"
 * (NOT "valid MDGL"). Throws TypeError for non-string input.
 */
export function check(source: string): CheckResult {
  if (typeof source !== 'string') throw new TypeError('mdgl.check: source must be a string');
  if (bytes(source) > MAX_INPUT) return d(1, 'input exceeds 256 KiB');
  let scene = false, action = false, version = false, actors = 0, actions = 0;
  const lines = source.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const n = i + 1;
    if (bytes(lines[i]) > MAX_LINE) return d(n, 'line exceeds 16 KiB');
    const t = lines[i].replace(/^[ \t\r]+|[ \t\r]+$/g, '');
    if (t === '' || t[0] === '#') continue;
    const head = t[0] === '@' ? '@' : t.split(/[ \t]/)[0];
    switch (head) {
      case 'mdgl':
        if (scene || version || t.slice(4).trim() !== '0.1') return d(n, 'expected initial mdgl 0.1');
        version = true;
        break;
      case 'scene': {
        if (scene) return d(n, 'duplicate scene');
        scene = true;
        const r = sceneHeader(n, t.slice(5));
        if (r.length) return r;
        break;
      }
      case 'actor':
        if (!scene) return d(n, 'scene must precede actors');
        if (action) return d(n, 'actors must precede actions');
        if (++actors > MAX_ACTORS) return d(n, 'actor limit 64 exceeded');
        break;
      case '@':
        if (!scene) return d(n, 'scene must precede actions');
        action = true;
        if (++actions > MAX_ACTIONS) return d(n, 'action limit 1024 exceeded');
        break;
      default:
        return d(n, 'unsupported statement (expected mdgl, scene, actor or @)');
    }
  }
  return scene ? [] : d(1, 'missing scene');
}

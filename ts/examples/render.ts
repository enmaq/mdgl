// Typed version of render.mjs: check, compile and print one frame.
//   npm run example:ts            (builds the package, compiles this file, runs it)
//   node .examples/render.js [scene.mdgl] [--time SECONDS | --fallback]
import { check, compile, fallbackFrame, frameNs } from '../dist/index';
import type { Diag, Frame } from '../dist/index';

declare const __dirname: string;
declare const process: { argv: string[]; exit(code: number): never };
declare function require(id: string): any;
const { readFileSync } = require('node:fs');
const path = require('node:path');

const args: string[] = process.argv.slice(2);
const fallback: boolean = args.includes('--fallback');
const ti = args.indexOf('--time');
const seconds: number = ti >= 0 ? Number(args[ti + 1]) : 0;
const file: string = args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--time') ?? path.join(__dirname, '..', '..', 'examples', 'text.mdgl');
if (!Number.isFinite(seconds) || seconds < 0) { console.error('--time needs a non-negative number of seconds'); process.exit(2); }

let source: string;
try { source = readFileSync(file, 'utf8'); } catch { console.error(`cannot read ${file}`); process.exit(2); }
const problems: Diag[] = check(source);
if (problems.length > 0) {
  for (const d of problems) console.error(`${file}:${d.line}:${d.col}: ${d.message}`);
  process.exit(1);
}
const compiled = compile(source);
if (!compiled.ok) process.exit(1); // unreachable after check(); narrows the type
const frame: Frame = fallback ? fallbackFrame(compiled.scene) : frameNs(compiled.scene, Math.round(seconds * 1e9));
console.log(frame.cells.map((row) => row.map((c) => c.r).join('')).join('\n'));
if (frame.done !== undefined) console.error(`done=${frame.done}`);

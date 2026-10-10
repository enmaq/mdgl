// Render one frame of an MDGL scene to the terminal.
//   npm run build && node examples/render.mjs [scene.mdgl] [--time SECONDS | --fallback]
// With the package installed, replace the import below by: import mdgl from '@enmaq/mdgl';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import mdgl from '../dist/index.js';

const { compile, frameNs, fallbackFrame } = mdgl;
const args = process.argv.slice(2);
const fallback = args.includes('--fallback');
const ti = args.indexOf('--time');
const seconds = ti >= 0 ? Number(args[ti + 1]) : 0;
const file = args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--time') ?? fileURLToPath(new URL('../../examples/text.mdgl', import.meta.url));
if (!Number.isFinite(seconds) || seconds < 0) { console.error('--time needs a non-negative number of seconds'); process.exit(2); }

let source;
try { source = readFileSync(file, 'utf8'); } catch { console.error(`cannot read ${file}`); process.exit(2); }
const result = compile(source);
if (!result.ok) {
  for (const d of result.diagnostics) console.error(`${file}:${d.line}:${d.col}: ${d.message}`);
  process.exit(1);
}
const frame = fallback ? fallbackFrame(result.scene) : frameNs(result.scene, Math.round(seconds * 1e9));
console.log(frame.cells.map((row) => row.map((c) => c.r).join('')).join('\n'));
if (frame.done !== undefined) console.error(`done=${frame.done}`);

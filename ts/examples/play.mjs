// Play a scene with the library API (what `mdgl play FILE` does, without the CLI).
//   npm run build && node examples/play.mjs [scene.mdgl]
// With the package installed, replace the import below by: import mdgl from '@enmaq/mdgl';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import mdgl from '../dist/index.js';

const file = process.argv[2] ?? fileURLToPath(new URL('../../examples/text.mdgl', import.meta.url));
const result = mdgl.compile(readFileSync(file, 'utf8'));
if (!result.ok) { for (const d of result.diagnostics) console.error(`${file}:${d.line}:${d.col}: ${d.message}`); process.exit(1); }

if (!process.stdout.isTTY) { process.stdout.write(mdgl.plainFallback(result.scene)); process.exit(0); }
const handle = mdgl.play(result.scene, {
  write: (s) => { process.stdout.write(s); },
  clock: { now: () => performance.now(), setTimeout, clearTimeout },
  onInterrupt: (cb) => { const f = () => cb(130); process.on('SIGINT', f); return () => process.off('SIGINT', f); },
});
const end = await handle.done;
process.exitCode = end.code;

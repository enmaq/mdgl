#!/usr/bin/env node
'use strict';
// mdgl command line: check FILE | frames FILE --at t1,t2 | play FILE.
// Exit codes: 0 ok, 1 invalid scene or output error, 2 usage or unreadable file,
// 130 interrupted by Ctrl+C (SIGINT), 143 terminated (SIGTERM).
const fs = require('node:fs');
const { performance } = require('node:perf_hooks');
const mdgl = require('../dist/index.js');
const pkg = require('../package.json');

const USAGE = `usage: mdgl <command> [options]

commands:
  play FILE             play FILE in the terminal (Ctrl+C stops it)
  check FILE            validate FILE; prints file:line:col: message and exits 1 if invalid
  frames FILE --at T,T  print the frame at each absolute time T (seconds), conformance format

play shows the fallback frame once, without escapes or timers, when stdout is not a terminal
or NO_COLOR or MDGL_REDUCED_MOTION is set to a non-empty value.

options:
  -h, --help     show this help
  -V, --version  show the version

exit codes: 0 ok, 1 invalid scene or output error, 2 usage or unreadable file, 130 Ctrl+C
`;
const usage = (msg) => { if (msg) process.stderr.write(`mdgl: ${msg}\n`); process.stderr.write(USAGE); process.exitCode = 2; };

function load(file) {
  let src;
  try { src = fs.readFileSync(file, 'utf8'); } catch (e) { process.stderr.write(`mdgl: cannot read ${file}\n`); process.exitCode = 2; return null; }
  const r = mdgl.compile(src);
  if (!r.ok) {
    for (const d of r.diagnostics) process.stderr.write(`${file}:${d.line}:${d.col}: ${d.message}\n`);
    process.exitCode = 1;
    return null;
  }
  return r.scene;
}
/** decimal seconds -> integer nanoseconds, or null */
function seconds(s) {
  const m = /^([0-9]+)(?:\.([0-9]+))?$/.exec(s);
  if (!m) return null;
  const ns = Number(m[1]) * 1e9 + Number(((m[2] || '') + '000000000').slice(0, 9));
  return Number.isSafeInteger(ns) ? ns : null;
}
function writeOut(text) {
  return new Promise((resolve) => {
    const onErr = (e) => { process.stderr.write(`mdgl: write error: ${e && e.code ? e.code : 'failed'}\n`); process.exitCode = 1; resolve(); };
    process.stdout.once('error', onErr);
    process.stdout.write(text, () => { process.stdout.off('error', onErr); resolve(); });
  });
}

async function play(file) {
  const scene = load(file);
  if (!scene) return;
  const reduced = (process.env.NO_COLOR || '') !== '' || (process.env.MDGL_REDUCED_MOTION || '') !== '';
  if (!process.stdout.isTTY || reduced) { await writeOut(mdgl.plainFallback(scene)); return; }
  const out = process.stdout;
  const handle = mdgl.play(scene, {
    write: (s) => { out.write(s); },
    clock: { now: () => performance.now(), setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: (h) => clearTimeout(h) },
    onWriteError: (cb) => { out.on('error', cb); return () => out.off('error', cb); },
    onInterrupt: (cb) => {
      const a = () => cb(130), b = () => cb(143);
      process.on('SIGINT', a);
      process.on('SIGTERM', b);
      return () => { process.off('SIGINT', a); process.off('SIGTERM', b); };
    },
  });
  const res = await handle.done;
  // keep a late stream error from crashing during teardown
  out.on('error', () => {});
  if (res.reason === 'write-error') process.stderr.write(`mdgl: write error: ${res.error && res.error.code ? res.error.code : 'failed'}\n`);
  process.exitCode = res.code;
}

async function main(argv) {
  const [cmd, ...rest] = argv;
  if (cmd === undefined) return usage();
  if (cmd === '-h' || cmd === '--help' || cmd === 'help') { process.stdout.write(USAGE); return; }
  if (cmd === '-V' || cmd === '--version') { process.stdout.write(`${pkg.version}\n`); return; }
  if (!['play', 'check', 'frames'].includes(cmd)) return usage(`unknown command ${JSON.stringify(cmd)}`);
  if (rest.includes('-h') || rest.includes('--help')) { process.stdout.write(USAGE); return; }
  const at = rest.indexOf('--at');
  const times = at >= 0 ? rest.splice(at, 2)[1] : undefined;
  const flags = rest.filter((a) => a.startsWith('-'));
  if (flags.length) return usage(`unknown option ${flags[0]}`);
  if (rest.length !== 1) return usage('expected exactly one FILE');
  const file = rest[0];
  if (cmd === 'check') { if (load(file)) process.stdout.write('ok\n'); return; }
  if (cmd === 'frames') {
    if (times === undefined) return usage('frames needs --at T,T');
    const list = times.split(',');
    const ns = list.map(seconds);
    if (ns.includes(null)) return usage('--at takes non-negative decimal seconds');
    const scene = load(file);
    if (!scene) return;
    await writeOut(list.map((t, i) => `@${t}\n${mdgl.frameNs(scene, ns[i]).cells.map((r) => r.map((c) => mdgl.sanitizeRune(c.r)).join('').replace(/ +$/, '')).join('\n')}\n`).join(''));
    return;
  }
  await play(file);
}
main(process.argv.slice(2)).catch((e) => { process.stderr.write(`mdgl: ${e && e.message ? e.message : e}\n`); process.exitCode = 1; });

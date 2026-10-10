// Runnable examples (examples/render.mjs, examples/render.ts) against the built package.
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.join(__dirname, '..');
const node = (args) => spawnSync(process.execPath, args, { cwd: root, encoding: 'utf8' });
const rows = (out) => out.split('\n').slice(0, -1);

test('tsc compiles the typed example', () => {
  const r = spawnSync(process.execPath, [path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'), '-p', 'examples'], { cwd: root, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});
for (const [name, entry] of [['js', 'examples/render.mjs'], ['ts', '.examples/render.js']]) {
  test(`${name} example: default, time, fallback`, () => {
    const d = node([entry]);
    assert.equal(d.status, 0, d.stderr);
    assert.equal(rows(d.stdout).length, 10); // text.mdgl is 48x10
    assert.match(d.stderr, /done=false/);
    const t = node([entry, '--time', '1.5']);
    assert.match(t.stdout, /MDGL 0\.1: animation in Markdown/);
    const f = node([entry, '--fallback']);
    assert.equal(f.status, 0);
    assert.match(f.stdout, /like WebGL, in your terminal/);
    assert.ok(!/done=/.test(f.stderr)); // fallback frames carry no done
  });
  test(`${name} example: invalid input`, () => {
    const bad = node([entry, path.join(root, 'package.json')]);
    assert.equal(bad.status, 1); // not MDGL -> diagnostic
    assert.match(bad.stderr, /:1:1: /);
    assert.equal(node([entry, '/no/such/file.mdgl']).status, 2);
    assert.equal(node([entry, '--time', '-1']).status, 2);
    assert.equal(node([entry, '--time', 'x']).status, 2);
  });
}
test('js and ts examples print identical frames', () => {
  for (const extra of [[], ['--time', '2'], ['--fallback']]) assert.equal(node(['examples/render.mjs', ...extra]).stdout, node(['.examples/render.js', ...extra]).stdout);
});

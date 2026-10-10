// Legacy glyph fixtures (conformance/NAME.mdgl + NAME.expect) through the evaluator; no adapter.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { compile, frameNs } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');
const dir = path.join(__dirname, '..', '..', 'conformance');
const toNs = (s) => { const [w, f = ''] = s.split('.'); return Number(w || '0') * 1e9 + Number((f + '000000000').slice(0, 9)); };
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.expect'))) {
  const n = f.slice(0, -7);
  test('expect ' + n, () => {
    const r = compile(fs.readFileSync(path.join(dir, n + '.mdgl'), 'utf8'));
    assert.ok(r.ok, JSON.stringify(r.diagnostics));
    const lines = fs.readFileSync(path.join(dir, f), 'utf8').split('\n');
    if (lines[lines.length - 1] === '') lines.pop();
    const H = r.scene.height, W = r.scene.width;
    for (let i = 0; i < lines.length;) {
      assert.match(lines[i], /^@/);
      const t = lines[i].slice(1);
      const rows = lines.slice(i + 1, i + 1 + H).map((l) => l.padEnd(W, ' '));
      const fr = frameNs(r.scene, toNs(t));
      const got = fr.cells.map((row) => row.map((c) => c.r).join(''));
      assert.deepEqual(got, rows, '@' + t);
      i += 1 + H;
    }
  });
}

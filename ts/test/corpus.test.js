const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { check } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');
const dir = path.join(__dirname, '..', '..', 'conformance');
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.mdgl'))) {
  const n = f.slice(0, -5);
  const src = fs.readFileSync(path.join(dir, f), 'utf8');
  const errF = path.join(dir, n + '.err');
  test('corpus ' + n, () => {
    const d = check(src);
    const obsF = path.join(dir, n + '.obs.json');
    const obs = fs.existsSync(obsF) ? JSON.parse(fs.readFileSync(obsF, 'utf8')) : null;
    if (obs && obs.class === 'diagnostic') return assert.deepEqual(d[0], obs.diagnostic);
    if (obs && obs.diagnostic === undefined && !fs.existsSync(errF) && obs.class !== 'diagnostic') { /* frame fixture: source must be valid */ }
    if (fs.existsSync(errF)) {
      assert.ok(d.length > 0, 'expected a diagnostic');
      assert.equal(`${d[0].line}:${d[0].col}: ${d[0].message}`, fs.readFileSync(errF, 'utf8').trim());
    } else assert.deepEqual(d, []);
  });
}

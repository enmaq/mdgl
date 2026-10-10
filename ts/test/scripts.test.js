// Regression: the npm test script must pass test FILES to `node --test`. Node 22 treats a bare
// directory argument as a module to run ("Cannot find module .../test"), which failed public CI
// while Node 18 accepted it.
const test = require('node:test');
const assert = require('node:assert');
const pkg = require('../package.json');
test('npm test passes files, not a directory, to node --test', () => {
  const m = /node --test (\S+)/.exec(pkg.scripts.test);
  assert.ok(m, pkg.scripts.test);
  assert.match(m[1], /\*\.test\.js$/);
  assert.ok(!m[1].endsWith('/'));
});
test('every test file is matched by the script glob', () => {
  const fs = require('node:fs');
  const files = fs.readdirSync(__dirname).filter((f) => f.endsWith('.test.js'));
  assert.ok(['adapter', 'check', 'corpus', 'example', 'expect', 'parse', 'scripts', 'unicode'].every((n) => files.includes(n + '.test.js')), files.join());
});

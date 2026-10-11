// Installed-package inclusion: the published tarball must carry the CLI, library build and licences.
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const root = path.join(__dirname, '..');
test('npm pack contains bin/mdgl.js, dist/play.js, types and licences; bin map is declared', () => {
  const cache = fs.mkdtempSync(path.join(os.tmpdir(), 'mdgl-pack-'));
  const r = spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], { cwd: root, encoding: 'utf8', env: { ...process.env, npm_config_cache: cache } });
  assert.equal(r.status, 0, r.stderr);
  const files = JSON.parse(r.stdout)[0].files.map((f) => f.path);
  for (const f of ['bin/mdgl.js', 'bin/mdgl-adapter.js', 'dist/play.js', 'dist/play.d.ts', 'dist/index.d.ts', 'README.md', 'LICENSE-MIT', 'LICENSE-APACHE', 'UNICODE-LICENSE.txt']) assert.ok(files.includes(f), 'missing ' + f);
  assert.ok(!files.some((f) => f.startsWith('test/') || f.startsWith('src/') || f.startsWith('.examples/')));
  const pkg = require('../package.json');
  assert.equal(pkg.bin.mdgl, 'bin/mdgl.js');
});

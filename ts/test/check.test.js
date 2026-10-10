const test = require('node:test');
const assert = require('node:assert');
const { check, VERSION } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');

const BASE = 'scene width=8 height=1 fallback=end\n';
const pad = (total) => BASE + '\n'.repeat(total - BASE.length);
const line = (n) => BASE + '#' + 'x'.repeat(n - 1) + '\n';
const actors = (n) => BASE + Array.from({ length: n }, (_, i) => `actor a${i} = circle(1) at (0, 0)\n`).join('');
const actions = (n) => BASE + 'actor a = text("AB") at (0, 0)\n' +
  Array.from({ length: n }, (_, i) => `@${(i * 0.05).toFixed(2)}: a.move(to=(${i % 2}, 0), dur=0.01)\n`).join('');

const cases = [
  ['minimal', BASE, true],
  ['version', 'mdgl 0.1\n' + BASE, true],
  ['order', 'scene fallback=start height=60 width=200\n', true],
  ['comments', '# hi\n\n' + BASE, true],
  ['empty', '\n', false],
  ['no width', 'scene height=1 fallback=end\n', false],
  ['no height', 'scene width=8 fallback=end\n', false],
  ['no fallback', 'scene width=8 height=1 period=4\n', false],
  ['width 0', 'scene width=0 height=1 fallback=end\n', false],
  ['width 201', 'scene width=201 height=1 fallback=end\n', false],
  ['height 61', 'scene width=8 height=61 fallback=end\n', false],
  ['dup key', 'scene width=8 width=9 height=1 fallback=end\n', false],
  ['unknown key', 'scene width=8 height=1 fallback=end bogus=1\n', false],
  ['dup scene', BASE + BASE, false],
  ['actor first', 'actor a = circle(1) at (0, 0)\n' + BASE, false],
  ['actor after action', BASE + '@0: a.fade(in, dur=1)\nactor a = circle(1) at (0, 0)\n', false],
  ['unknown stmt', BASE + 'bogus\n', false],
  ['size 256KiB', pad(262144), true],
  ['size +1', pad(262145), false],
  ['line 16384', line(16384), true],
  ['line 16385', line(16385), false],
  ['64 actors', actors(64), true],
  ['65 actors', actors(65), false],
  ['1024 actions', actions(1024), true],
  ['1025 actions', actions(1025), false],
];

for (const [name, src, ok] of cases) {
  test(name, () => assert.equal(check(src).length === 0, ok, JSON.stringify(check(src))));
}
test('non-string throws', () => assert.throws(() => check(null), TypeError));
test('version matches package', () => {
  if (!process.env.MDGL_UNDER_TEST) assert.equal(VERSION, require('../package.json').version);
});

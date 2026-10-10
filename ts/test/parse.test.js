const test = require('node:test');
const assert = require('node:assert');
const { check, parseChecked } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');
const S = 'scene width=20 height=5 fallback=end\n';
const first = (src) => { const d = check(src); return d.length ? `${d[0].line}:${d[0].col}: ${d[0].message}` : ''; };
test('go-style escapes', () => assert.equal(first(S + 'actor a = text("a\\u00e9\\x41\\101\\"") at (0,0)\n'), ''));
test('bad escape col', () => assert.equal(first(S + 'actor a = text("\\q") at (0,0)\n'), '2:17: invalid escape in string'));
test('exponent rejected', () => assert.match(first(S + 'actor a = circle(1e1) at (0,0)\n'), /^2:/));
test('scene before actor', () => assert.equal(first('actor a = circle(1) at (0,0)\n' + S), '1:1: scene must precede actors'));
test('forward parent ok', () => assert.equal(first(S + 'actor a = circle(1) at (0,0) parent=b\nactor b = circle(1) at (0,0)\n'), ''));
test('unknown parent', () => assert.match(first(S + 'actor a = circle(1) at (0,0) parent=b\n'), /^2:1: unknown parent "b"/));
test('anchor axis', () => assert.match(first(S + 'actor a = circle(1) at (top, 0)\n'), /^2:1: anchor top/));
test('anchor offsets and percent', () => assert.equal(first(S + 'actor a = circle(1) at (right-3, 50%)\n'), ''));
test('duplicate arg', () => assert.equal(first(S + 'actor a = circle(1) at (0,0)\n@0: a.fade(in, dur=1, dur=2)\n'), '3:1: duplicate argument dur'));
test('rotate cube only', () => assert.match(first(S + 'actor a = circle(1) at (0,0)\n@0: a.rotate(x=1, dur=1)\n'), /cube/));
test('rotate rad ok', () => assert.equal(first(S + 'actor a = cube(size=3) at (0,0)\n@0: a.rotate(x=1.5rad, y=90deg, dur=1)\n'), ''));
test('type text only, grapheme duration overlaps', () => {
  assert.equal(first(S + 'actor a = text("ab") at (0,0)\n@0: a.type(per_char=1)\n@2: a.wipe(in, dur=1)\n'), '');
  assert.match(first(S + 'actor a = text("ab") at (0,0)\n@0: a.type(per_char=1)\n@1: a.type(per_char=1)\n'), /^4:1: overlapping reveal/);
});
test('fallback beyond duration', () => assert.match(first('scene width=8 height=1 fallback=@5\n'), /^1:1: fallback time/));
test('model', () => {
  const r = parseChecked(S + 'actor a = text("x") at (0,0)\n@0.5: a.fade(in, dur=1.5)\n');
  assert.ok(r.ok);
  assert.equal(r.doc.scene.duration, 2e9);
  assert.equal(r.doc.actions[0].endNs, 2e9);
});
test('byte columns (2- and 3-byte runes)', () => {
  assert.equal(first(S + 'actor a = text("é") $\n'), '2:22: unexpected character "$"');
  assert.equal(first(S + 'actor a = text("日本") $\n'), '2:26: unexpected character "$"');
});
test('text 1024/1025 grapheme clusters, combining and flags', () => {
  const t = (n, u) => first(S + `actor a = text("${u.repeat(n)}") at (0,0)\n`);
  assert.equal(t(1024, 'é'), '');
  assert.match(t(1025, 'é'), /^2:1: text exceeds 1024/);
  assert.equal(t(512, '🇺🇸'), '');
});
test('z is an unbounded integer; fractional rejected', () => {
  assert.equal(first(S + 'actor a = circle(1) at (0,0) z=100000\n'), '');
  assert.match(first(S + 'actor a = circle(1) at (0,0) z=1.5\n'), /^2:1: z must be an integer/);
});
test('circle radius bound is 100 (diameter <= 200)', () => {
  const c = (r) => first(S + `actor a = circle(${r}) at (0,0)\n`);
  assert.equal(c('100'), '');
  assert.equal(c('100.0'), '');
  assert.equal(c('0.5'), '');
  for (const r of ['100.0001', '150', '200', '0', '-1']) assert.equal(c(r), '2:1: circle radius must be positive and <=100', r);
  // rect and cube keep their own 0 < n <= 200 bound
  assert.equal(first(S + 'actor a = cube(size=200) at (0,0)\n'), '');
  assert.match(first(S + 'actor a = cube(size=201) at (0,0)\n'), /^2:1: cube size .* 200$/);
});

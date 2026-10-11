// Opacity over an already painted glyph: RGB source-over onto the cell's current foreground
// (all other adapters agree); over a blank cell the destination is the black background.
// Exact values come from the five adapters' agreed output, not from this implementation.
const test = require('node:test');
const assert = require('node:assert');
const { handleLine } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');
const S = 'scene width=20 height=5 fallback=end\n';
const cell = (src, ns, r = 0, c = 0, w = 20, h = 5) => JSON.parse(handleLine(JSON.stringify({ v: 1, id: 'x', op: 'frame', source: src, time_ns: ns, width: w, height: h }))).cells[r][c];
const fg = (src, ns, r, c) => cell(src, ns, r, c).fg;
const fade = (name, ease = 'linear') => `@0: ${name}.fade(in, dur=1, ease=${ease})\n`;
const TXT = (n, ch, x, col) => `actor ${n} = text("${ch}") at (${x}, 0)${col ? ' color=' + col : ''}\n`;

test('half fade over an opaque red glyph blends with red, not black', () => {
  assert.equal(fg(S + TXT('a', 'A', 0, 'red') + TXT('b', 'B', 0, 'green') + fade('b'), 5e8), '#808000');
});
test('quarter fade over an opaque normal (white) glyph', () => {
  assert.equal(fg(S + TXT('a', 'A', 0) + TXT('b', 'B', 0, 'blue') + fade('b'), 25e7), '#bfbfff');
});
test('two stacked half fades compose twice', () => {
  assert.equal(fg(S + TXT('a', 'A', 0, 'red') + TXT('b', 'B', 0, 'green') + fade('a') + fade('b'), 5e8), '#408000');
});
test('controls: blank cell blends with black; opaque top glyph keeps its named colour; alone equals alone', () => {
  assert.equal(fg(S + TXT('b', 'B', 0, 'green') + fade('b'), 5e8), '#008000');
  assert.equal(fg(S + TXT('a', 'A', 0, 'red') + TXT('b', 'B', 0, 'green') + fade('a'), 5e8), 'green');
  assert.equal(fg(S + TXT('t', 'N', 1, 'magenta') + fade('t', 'ease-out'), 33333333, 0, 1), '#0e000e');
});
test('rect title over its own faded border (the neon title case)', () => {
  const src = S + 'actor f = rect(10, 3, border=square, title="N") at (0, 0) color=magenta\n' + fade('f', 'ease-out');
  assert.deepEqual([cell(src, 33333333, 0, 1).r, cell(src, 33333333, 0, 1).fg], ['N', '#1b001b']); // title glyph: source-over onto its border dots
  assert.equal(fg(src, 33333333, 0, 5), '#0e000e'); // border cell without a title: single blend
  const lin = S + 'actor f = rect(10, 3, border=square, title="N") at (0, 0) color=magenta\n' + fade('f');
  assert.equal(fg(lin, 5e8, 0, 1), '#c000c0');
  assert.equal(fg(lin, 1e9, 0, 1), 'magenta'); // full opacity: named colour
});
test('exact neon-cube request: row 0 column 1 at 33333333 ns is N #1b001b', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const file = path.join(__dirname, '..', '..', 'examples', 'neon-cube.mdgl');
  if (!fs.existsSync(file)) return;
  const c = cell(fs.readFileSync(file, 'utf8'), 33333333, 0, 1, 90, 28);
  assert.deepEqual([c.r, c.fg, c.bg], ['N', '#1b001b', '']);
});

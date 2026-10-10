const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const U = require(process.env.MDGL_UNDER_TEST ? '../dist/unicode.js' : '../dist/unicode.js');

test('GraphemeBreakTest.txt 15.0.0 (all lines)', () => {
  let n = 0;
  const bad = [];
  for (const l of fs.readFileSync(path.join(__dirname, 'data', 'GraphemeBreakTest.txt'), 'utf8').split('\n')) {
    const body = l.replace(/#.*/, '').trim();
    if (!body) continue;
    const toks = body.split(/\s+/).filter((t) => t !== '÷' && t !== '×' ? true : true);
    let str = '', exp = [], pos = 0;
    for (const t of toks) {
      if (t === '÷') { exp.push(pos); continue; }
      if (t === '×') continue;
      const c = String.fromCodePoint(parseInt(t, 16)); str += c; pos += c.length;
    }
    const want = exp.filter((p) => p > 0 && p < str.length);
    const got = U.graphemeRanges(str).map((r) => r[0]).filter((p) => p > 0);
    n++;
    if (JSON.stringify(want) !== JSON.stringify(got)) bad.push(body.slice(0, 80));
  }
  assert.ok(n > 600, 'lines ' + n);
  assert.deepEqual(bad.slice(0, 5), []);
});
test('profile cases', () => {
  const cnt = U.graphemeCount;
  assert.equal(cnt('🇺🇸🇫🇷'), 2);            // flags
  assert.equal(cnt('🇺🇸🇫'), 2);              // odd regional indicator
  assert.equal(cnt('각'), 1); // jamo L V T
  assert.equal(cnt('क्ष'), 2);                // 15.0: no GB9c, virama+consonant splits
  assert.equal(cnt('بَ'), 1);       // Arabic fatha
  assert.equal(cnt('؀a'), 1);            // prepend
  assert.equal(cnt('🏴\u{e0067}\u{e0062}\u{e007f}'), 1); // tag sequence
  assert.equal(cnt('👨‍👩‍👧'), 1);               // ZWJ family
  assert.equal(cnt('é́'), 1);
  assert.equal(cnt('a'.repeat(1024)), 1024);
  assert.equal(cnt('a'.repeat(1025)), 1025);
});
test('cell rune', () => {
  assert.equal(U.cellRune('é'), 'e');
  assert.equal(U.cellRune('́e'), 'e');
  assert.equal(U.cellRune('日'), '�');
  assert.equal(U.cellRune('A'), 'A');
  assert.equal(U.cellRune('́'), ' ');   // all marks: width 0, blank cell
  assert.equal(U.clusterWidth('\u200b'), 0);
  assert.equal(U.clusterWidth('\u200d'), 0);
  assert.equal(U.clusterWidth('☺️'), 2);  // VS16 emoji presentation
  assert.equal(U.clusterWidth('☺'), 1);
  assert.equal(U.cellRune('☺️'), '�');
  assert.equal(U.clusterWidth('👍🏽'), 2);
  assert.equal(U.clusterWidth('ｱ'), 1);
  assert.equal(U.clusterWidth('Ａ'), 2);
  assert.equal(U.UNICODE_VERSION, '15.0.0');
  assert.equal(U.clusterWidth('🇺🇸'), 2);   // flag pair
  assert.equal(U.clusterWidth('🇺'), 2);     // single RI
  assert.equal(U.cellRune('🇺🇸'), '�');
  assert.equal(U.clusterWidth('1️⃣'), 2);  // keycap 1 FE0F 20E3
  assert.equal(U.clusterWidth('#️⃣'), 2);
  assert.equal(U.clusterWidth('1⃣'), 1);   // no VS16: not an emoji keycap
  assert.equal(U.cellRune('1️⃣'), '�');
});
test('marks table is the pinned Unicode 15.0.0 General_Category M* set', () => {
  // The pinned profile must not follow the runtime's ICU: Node 22.23 ships Unicode 17, which has
  // 93 more marks than 15.0 (e.g. U+0897, U+1ACF..). Pin the table itself ...
  const { MARK } = require('../dist/unicode-tables.js');
  const sha = require('node:crypto').createHash('sha256').update(MARK.join(',')).digest('hex');
  assert.equal(sha, 'e62f86b3491d1fc15c0733e6dc86efe05883dca06cf2235995b866e67a4cfa91');
  // ... and compare with the runtime exactly where the runtime Unicode version has the same marks
  // (15.0 and 15.1), otherwise require the pinned set to be a subset of the runtime's marks.
  const [maj, min] = process.versions.unicode.split('.').map(Number);
  const same = maj === 15 && min <= 1;
  let missing = 0, extra = 0;
  for (let c = 0; c < 0x30000; c++) {
    const rt = /\p{M}/u.test(String.fromCodePoint(c)), t = U.isMark(c);
    if (t && !rt) missing++;
    if (rt && !t) extra++;
  }
  assert.equal(missing, 0, 'pinned marks absent from runtime');
  if (same) assert.equal(extra, 0);
  else assert.ok(extra < 200, 'runtime-only marks: ' + extra);
});

test('one cluster = one cell: later cells never shift', () => {
  const cells = (str) => U.graphemes(str).map(U.cellRune);
  assert.deepEqual(cells('🇺🇸A'), ['�', 'A']);            // flag + ASCII
  assert.deepEqual(cells('\u0301A'), [' ', 'A']);         // leading mark + ASCII
  assert.deepEqual(cells('e\u0301A'), ['e', 'A']);
  assert.deepEqual(cells('\u200bA'), ['\u200b', 'A']);   // ZWSP is a non-mark rune: emitted, still one cell
  assert.deepEqual(cells('1️⃣A'), ['�', 'A']);        // keycap + ASCII
  assert.deepEqual(cells('☺️A'), ['�', 'A']);        // VS16 + ASCII
  assert.deepEqual(cells('日A'), ['�', 'A']);
});

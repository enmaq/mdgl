const test = require('node:test');
const assert = require('node:assert');
const { handleLine, mathInt } = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');
const S = 'scene width=8 height=1 fallback=end\\n';
const req = (o) => handleLine(JSON.stringify(o));
const code = (s) => JSON.parse(s).error && JSON.parse(s).error.code;
test('mathematical integers on the wire', () => {
  const f = (t) => handleLine(`{"v":1,"id":"x","op":"frame","source":"","time_ns":${t},"width":8,"height":1}`);
  for (const t of ['1.5', '9007199254740991.1', '9007199254740992', '-1', '1e-1', '0.5e0']) assert.equal(code(f(t)), 'bad_request', t);
  for (const t of ['-0', '-0.0', '1.0', '1e9']) assert.equal(code(f(t)), 'invalid_source', t); // accepted as numbers; source "" is invalid
  assert.equal(mathInt('9007199254740991.0'), 9007199254740991n);
});
test('versions and ids', () => {
  assert.equal(code(handleLine('{"v":2,"id":"a","op":"check","source":""}')), 'unsupported_version');
  assert.equal(code(handleLine('{"v":1.5,"id":"a","op":"check","source":""}')), 'bad_request');
  assert.equal(code(handleLine('')), 'bad_request');
  assert.equal(JSON.parse(handleLine('nope')).id, null);
});
test('done present on normal frames, omitted on fallback', () => {
  const src = 'scene width=8 height=1 fallback=end\nactor a = text("AB") at (0, 0)\n@0: a.move(to=(2, 0), dur=1)\n';
  const n = JSON.parse(req({ v: 1, id: 'n', op: 'frame', source: src, time_ns: 0, width: 8, height: 1 }));
  const fb = JSON.parse(req({ v: 1, id: 'f', op: 'frame', source: src, fallback: true, width: 8, height: 1 }));
  assert.equal(n.done, false);
  assert.ok(!('done' in fb));
  assert.equal(fb.cells[0].map((c) => c.r).join(''), '  AB    ');
});
test('lone surrogate escape is bad_request; viewport clamps to scene', () => {
  assert.equal(code(handleLine('{"v":1,"id":"a","op":"check","source":"\\ud800"}')), 'bad_request');
  const r = JSON.parse(req({ v: 1, id: 'c', op: 'frame', source: 'scene width=4 height=1 fallback=end\n', time_ns: 0, width: 200, height: 60 }));
  assert.equal(r.width, 4);
  assert.equal(r.height, 1);
});

// ---- strict UTF-8 transport (spawned adapter, raw bytes) ----
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const BIN = path.join(__dirname, '..', 'bin', 'mdgl-adapter.js');
const GOOD = Buffer.from('{"v":1,"id":"ok","op":"check","source":"scene width=8 height=1 fallback=end\\n"}\n');
const pre = Buffer.from('{"v":1,"id":"a","op":"check","source":"');
const post = Buffer.from('"}\n');
const run = (...bufs) => spawnSync(process.execPath, [BIN], { input: Buffer.concat(bufs) }).stdout.toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
test('malformed UTF-8 bytes are bad_request with null id, next good line recovers', () => {
  for (const bad of [[0xff], [0xc0, 0xaf], [0xe0, 0x80, 0xaf], [0xed, 0xa0, 0x80], [0xe3, 0x81], [0xf4, 0x90, 0x80, 0x80], [0x80]]) {
    const out = run(pre, Buffer.from(bad), post, GOOD);
    assert.equal(out.length, 2, JSON.stringify(bad));
    assert.equal(out[0].ok, false, JSON.stringify(bad));
    assert.equal(out[0].error.code, 'bad_request');
    assert.equal(out[0].id, null);
    assert.equal(out[1].id, 'ok');
    assert.equal(out[1].ok, true);
  }
});
test('valid U+FFFD and valid multibyte text are accepted; byte columns unchanged', () => {
  const out = run(pre, Buffer.from('é�日', 'utf8'), post);
  assert.equal(out.length, 1);
  assert.equal(out[0].ok, true);
  assert.match(out[0].diagnostics[0].message, /é/); // decoded text, not replaced
});
test('multibyte character split across stdin chunks', async () => {
  const { spawn } = require('node:child_process');
  const child = spawn(process.execPath, [BIN]);
  let out = '';
  child.stdout.on('data', (d) => { out += d; });
  const line = Buffer.concat([pre, Buffer.from('日', 'utf8'), post]);
  const cut = pre.length + 1; // inside the 3-byte rune
  child.stdin.write(line.subarray(0, cut));
  await new Promise((r) => setTimeout(r, 50));
  child.stdin.end(line.subarray(cut));
  await new Promise((r) => child.on('close', r));
  const j = JSON.parse(out.trim());
  assert.equal(j.ok, true);
  assert.equal(j.id, 'a');
});
test('final unterminated line: valid answered once, invalid is bad_request once', () => {
  const noNl = (b) => b.subarray(0, b.length - 1);
  const v = run(noNl(GOOD));
  assert.equal(v.length, 1);
  assert.equal(v[0].id, 'ok');
  const i = run(pre, Buffer.from([0xff]), noNl(post));
  assert.equal(i.length, 1);
  assert.equal(i[0].error.code, 'bad_request');
});
test('BOM is not stripped: leading BOM is bad_request, BOM inside a string is data', () => {
  const out = run(Buffer.from([0xef, 0xbb, 0xbf]), GOOD, GOOD);
  assert.equal(out[0].error.code, 'bad_request');
  assert.equal(out[1].id, 'ok');
  const inner = run(pre, Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('scene width=8 height=1 fallback=end\\n'), post);
  assert.equal(inner[0].ok, true);
  assert.equal(inner[0].diagnostics[0].col, 1); // the BOM rune is data in the source, reported at byte column 1
});
test('2 MiB byte cap: oversize line (with or without newline) is one bad_request, then recovery', () => {
  const big = Buffer.concat([pre, Buffer.alloc(2097152, 0x61), post]);
  const out = run(big, GOOD);
  assert.equal(out.length, 2);
  assert.equal(out[0].error.code, 'bad_request');
  assert.equal(out[0].id, null);
  assert.equal(out[1].id, 'ok');
  const out2 = run(Buffer.concat([pre, Buffer.alloc(2097152, 0x61)]));
  assert.equal(out2.length, 1);
  assert.equal(out2[0].error.code, 'bad_request');
});

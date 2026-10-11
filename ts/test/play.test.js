// Deterministic player tests: fake monotonic clock, recording writer, no real terminal.
const test = require('node:test');
const assert = require('node:assert');
const m = require(process.env.MDGL_UNDER_TEST || '../dist/index.js');

function fake() {
  const c = { t: 1000, timers: [], id: 0, writes: [], subs: { err: [], int: [] }, unsubs: 0 };
  c.now = () => c.t;
  c.setTimeout = (fn, ms) => { const h = ++c.id; c.timers.push({ h, at: c.t + ms, fn }); return h; };
  c.clearTimeout = (h) => { c.timers = c.timers.filter((x) => x.h !== h); };
  // run timers due up to now+ms, advancing the clock to each timer time
  c.run = (ms) => { const end = c.t + ms; for (;;) { c.timers.sort((a, b) => a.at - b.at); const n = c.timers[0]; if (!n || n.at > end) break; c.timers.shift(); c.t = n.at; n.fn(); } c.t = end; };
  c.deps = (over = {}) => ({
    write: (s) => { c.writes.push(s); },
    clock: c,
    onWriteError: (cb) => { c.subs.err.push(cb); return () => { c.unsubs++; }; },
    onInterrupt: (cb) => { c.subs.int.push(cb); return () => { c.unsubs++; }; },
    ...over,
  });
  return c;
}
const scene = (src) => { const r = m.compile(src); assert.ok(r.ok, JSON.stringify(r.diagnostics)); return r.scene; };
const MOVE = 'scene width=6 height=1 fps=10 fallback=end\nactor a = text("AB") at (0,0)\n@0: a.move(to=(4,0), dur=1)\n';
const strip = (s) => s.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '');

test('finite scene: hide cursor first, stops on done, restores cursor, no timers left', async () => {
  const c = fake();
  const h = m.play(scene(MOVE), c.deps());
  assert.ok(c.writes[0].startsWith(m.SYNC_BEGIN + m.HIDE_CURSOR));
  assert.ok(c.writes[0].endsWith(m.SYNC_END));
  c.run(5000);
  const r = await h.done;
  assert.deepEqual([r.code, r.reason], [0, 'done']);
  assert.equal(c.writes[c.writes.length - 1], m.RESET + m.SHOW_CURSOR);
  assert.equal(c.timers.length, 0);
  assert.equal(c.unsubs, 2); // both listeners removed
  const n = c.writes.length;
  c.run(5000);
  assert.equal(c.writes.length, n); // nothing after done
});
test('every frame update is one atomic synchronized-output chunk', async () => {
  const c = fake();
  const h = m.play(scene(MOVE), c.deps());
  c.run(5000);
  await h.done;
  for (const w of c.writes.slice(0, -1)) { assert.ok(w.startsWith(m.SYNC_BEGIN)); assert.ok(w.endsWith(m.SYNC_END)); }
});
test('frame time is absolute elapsed time, not accumulated ticks', async () => {
  const c = fake();
  m.play(scene(MOVE), c.deps());
  // stall: the clock jumps 0.6 s before the next timer fires; the frame must show t=0.6 (x=2.4 -> col 2)
  c.t += 600;
  c.timers.sort((a, b) => a.at - b.at);
  const t = c.timers.shift();
  t.fn();
  const last = c.writes[c.writes.length - 1];
  assert.equal(strip(last).replace('\r', ''), '  AB'); // A now at column 2 (x=2.4 rounds to 2); one 0.1 s tick would leave it at column 0
});
test('dirty cells only: an unchanged frame writes nothing, a change touches only its cells', async () => {
  const c = fake();
  m.play(scene('scene width=40 height=3 fps=10 period=2 repeat=infinite fallback=end\nactor a = text("X") at (0,0)\nactor b = text("Y") at (30,2)\n@0: a.move(to=(1,0), dur=1)\n'), c.deps());
  const first = c.writes.length;
  c.run(50); // 0.05 s: a stays in column 0 (round(0.05*... ) -> no change)
  assert.equal(c.writes.length, first, 'unchanged frame must not write');
  c.run(1000);
  const upd = c.writes.slice(first).join('');
  assert.ok(upd.length < 400, 'diff update is small: ' + upd.length);
  assert.ok(!strip(upd).includes('Y'), 'unchanged actor b is not redrawn');
});
test('colours: named fg, true-colour blend, bg codes', async () => {
  const c = fake();
  m.play(scene('scene width=4 height=1 fps=10 fallback=end\nactor a = text("A") at (0,0) color=red\nactor b = text("B") at (1,0)\n@0: b.fade(in, dur=2)\n'), c.deps());
  c.run(1000);
  const all = c.writes.join('');
  assert.match(all, /\x1b\[0;31;49m/); // red on default background
  assert.match(all, /38;2;12[0-9];12[0-9];12[0-9]/); // half-faded white as 24-bit
});
test('control characters in cells never reach the terminal as escapes', () => {
  assert.equal(m.sanitizeRune('\x1b'), ' ');
  assert.equal(m.sanitizeRune('\x07'), ' ');
  assert.equal(m.sanitizeRune('\x9b'), ' ');
  assert.equal(m.sanitizeRune('\x7f'), ' ');
  assert.equal(m.sanitizeRune('é'), 'é');
  assert.equal(m.sanitizeRune('日'), '日');
  assert.equal(strip(m.plainText([[{ r: '\x1b', fg: 'normal', bg: '' }, { r: 'A', fg: 'normal', bg: '' }]])), ' A\n');
});
test('infinite scene never finishes; interrupt stops it with code 130 and cleans up', async () => {
  const c = fake();
  const h = m.play(scene('scene width=6 height=1 fps=10 period=1 repeat=infinite fallback=end\nactor a = text("A") at (0,0)\n@0: a.move(to=(3,0), dur=1)\n'), c.deps());
  c.run(60000);
  assert.equal(c.timers.length, 1); // still ticking
  c.subs.int[0](130);
  const r = await h.done;
  assert.deepEqual([r.code, r.reason], [130, 'interrupt']);
  assert.equal(c.timers.length, 0);
  assert.equal(c.unsubs, 2);
  assert.equal(c.writes[c.writes.length - 1], m.RESET + m.SHOW_CURSOR);
  const n = c.writes.length;
  c.subs.int[0](130); // idempotent
  assert.equal(c.writes.length, n);
});
test('synchronous write error: stops, surfaces the error, still tries to restore the cursor', async () => {
  const c = fake();
  let calls = 0;
  const boom = new Error('EPIPE');
  const h = m.play(scene(MOVE), c.deps({ write: (s) => { calls++; c.writes.push(s); if (calls === 2) throw boom; } }));
  c.run(5000);
  const r = await h.done;
  assert.equal(r.code, 1);
  assert.equal(r.reason, 'write-error');
  assert.equal(r.error, boom);
  assert.equal(c.timers.length, 0);
  assert.equal(c.unsubs, 2);
  assert.equal(c.writes[c.writes.length - 1], m.RESET + m.SHOW_CURSOR);
});
test('asynchronous stream error stops playback', async () => {
  const c = fake();
  const h = m.play(scene(MOVE), c.deps());
  c.subs.err[0](new Error('EIO'));
  const r = await h.done;
  assert.deepEqual([r.code, r.reason], [1, 'write-error']);
  assert.equal(c.timers.length, 0);
});
test('fallback text is exactly the plain fallback frame, no escapes', () => {
  const s = scene('scene width=4 height=2 fallback=end\nactor a = text("AB") at (1,1)\n@0: a.move(to=(2,0), dur=1)\n');
  const t = m.plainFallback(s);
  assert.equal(t, '  AB\n    \n');
  assert.ok(!/\x1b/.test(t));
});
test('stop() ends playback once', async () => {
  const c = fake();
  const h = m.play(scene(MOVE), c.deps());
  h.stop(); h.stop();
  const r = await h.done;
  assert.equal(r.reason, 'stopped');
  assert.equal(c.writes.filter((w) => w === m.RESET + m.SHOW_CURSOR).length, 1);
});

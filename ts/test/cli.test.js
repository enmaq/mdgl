// Real-process proof for `mdgl`: a pseudo-terminal (python3 pty) for play, pipes for redirected output.
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const bin = path.join(__dirname, '..', 'bin', 'mdgl.js');
const py = spawnSync('python3', ['-c', 'import pty']);
const havePty = process.platform !== 'win32' && py.status === 0;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mdgl-cli-'));
const write = (n, s) => { const f = path.join(tmp, n); fs.writeFileSync(f, s); return f; };
const FINITE = write('finite.mdgl', 'scene width=8 height=2 fps=30 fallback=end\nactor a = text("AB") at (0,0)\n@0: a.move(to=(6,1), dur=1)\n');
const INFINITE = write('inf.mdgl', 'scene width=8 height=1 fps=30 period=1 repeat=infinite fallback=end\nactor a = text("AB") at (0,0)\n@0: a.move(to=(6,0), dur=1)\n');

// run `node bin/mdgl.js play FILE` in a pty; optionally send ^C after `intAfter` seconds
const PTYRUN = `
import os, pty, sys, time, json, select, signal
node, bin, file, env_json, int_after = sys.argv[1:6]
env = dict(os.environ); env.update(json.loads(env_json))
t0 = time.time()
pid, fd = pty.fork()
if pid == 0:
    os.execve(node, [node, bin, 'play', file], env)
out = b''; sent = False
while True:
    r, _, _ = select.select([fd], [], [], 0.05)
    if r:
        try: d = os.read(fd, 65536)
        except OSError: d = b''
        if not d: break
        out += d
    if int_after != '-' and not sent and time.time() - t0 > float(int_after):
        os.write(fd, b'\\x03'); sent = True
    if time.time() - t0 > 15: os.kill(pid, signal.SIGKILL); break
_, st = os.waitpid(pid, 0)
print(json.dumps({'code': os.waitstatus_to_exitcode(st), 'secs': time.time() - t0, 'out': out.decode('utf8', 'replace')}))
`;
const pty = (file, extra = {}, intAfter = '-') => JSON.parse(spawnSync('python3', ['-I', '-c', PTYRUN, process.execPath, bin, file, JSON.stringify({ NO_COLOR: '', MDGL_REDUCED_MOTION: '', ...extra }), intAfter], { encoding: 'utf8', timeout: 30000 }).stdout);
const run = (args, extra = {}) => spawnSync(process.execPath, [bin, ...args], { encoding: 'utf8', env: { ...process.env, NO_COLOR: '', MDGL_REDUCED_MOTION: '', ...extra } });

test('help, version, usage errors and unreadable files', () => {
  assert.equal(run(['--help']).status, 0);
  assert.match(run(['--help']).stdout, /mdgl play FILE|play FILE/);
  assert.equal(run(['--version']).stdout.trim(), require('../package.json').version);
  assert.equal(run([]).status, 2);
  assert.equal(run(['play']).status, 2);
  assert.equal(run(['bogus']).status, 2);
  assert.equal(run(['play', '--nope', FINITE]).status, 2);
  assert.equal(run(['play', path.join(tmp, 'missing.mdgl')]).status, 2);
});
test('invalid scene: diagnostic on stderr, exit 1, nothing on stdout', () => {
  const bad = write('bad.mdgl', 'scene width=8 height=1\n');
  const r = run(['play', bad]);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /bad\.mdgl:1:1: missing scene attribute fallback/);
  assert.equal(r.stdout, '');
  assert.equal(run(['check', bad]).status, 1);
  assert.equal(run(['check', FINITE]).stdout, 'ok\n');
});
test('redirected stdout: exactly the plain fallback frame once, no escapes, exit 0', () => {
  const r = run(['play', FINITE]);
  assert.equal(r.status, 0);
  assert.equal(r.stdout, '        \n      AB\n');
  assert.ok(!/\x1b/.test(r.stdout));
});
test('frames prints the conformance format', () => {
  assert.equal(run(['frames', FINITE, '--at', '0,1']).stdout, '@0\nAB\n\n@1\n\n      AB\n');
  assert.equal(run(['frames', FINITE]).status, 2);
  assert.equal(run(['frames', FINITE, '--at', 'x']).status, 2);
});
test('closed stdout pipe is surfaced, not swallowed', () => {
  // head -c1 closes the pipe after one byte; plain fallback write must not hang or crash silently
  const r = spawnSync('sh', ['-c', `"${process.execPath}" "${bin}" play "${FINITE}" | head -c1 >/dev/null; echo done`], { encoding: 'utf8' });
  assert.equal(r.stdout.trim(), 'done');
});
test('pty: finite scene animates with absolute time, sync output, hidden cursor, restored on exit 0', { skip: !havePty }, () => {
  const r = pty(FINITE);
  assert.equal(r.code, 0);
  assert.ok(r.out.includes('\x1b[?2026h') && r.out.includes('\x1b[?2026l'));
  assert.ok(r.out.indexOf('\x1b[?25l') >= 0 && r.out.lastIndexOf('\x1b[?25h') > r.out.lastIndexOf('\x1b[?25l'));
  assert.ok(r.out.trimEnd().endsWith('\x1b[?25h'), JSON.stringify(r.out.slice(-40)));
  assert.ok(r.secs >= 0.95 && r.secs < 3, 'duration ' + r.secs); // 1 s scene: stops on done, not early, not hung
});
test('pty: Ctrl+C stops an infinite scene with exit 130 and a restored cursor', { skip: !havePty }, () => {
  const r = pty(INFINITE, {}, '0.6');
  assert.equal(r.code, 130);
  assert.ok(r.out.trimEnd().endsWith('\x1b[?25h'), JSON.stringify(r.out.slice(-40)));
  assert.ok(r.secs < 5);
});
test('pty: reduced motion and NO_COLOR print only the plain fallback frame', { skip: !havePty }, () => {
  for (const env of [{ MDGL_REDUCED_MOTION: '1' }, { NO_COLOR: '1' }]) {
    const r = pty(FINITE, env);
    assert.equal(r.code, 0);
    assert.equal(r.out.replace(/\r\n/g, '\n'), '        \n      AB\n');
    assert.ok(r.secs < 2);
  }
});
test('pty: empty NO_COLOR does not disable animation', { skip: !havePty }, () => {
  const r = pty(FINITE, { NO_COLOR: '' });
  assert.ok(r.out.includes('\x1b[?25l'));
});

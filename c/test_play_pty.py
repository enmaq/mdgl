#!/usr/bin/env python3
"""Real pseudo-terminal tests for `mdgl play`: python3 test_play_pty.py PATH_TO_MDGL (POSIX, stdlib only)."""
import os, pty, select, signal, subprocess, sys, tempfile, time

BIN = os.path.abspath(sys.argv[1])
fails = 0
FIN = 'scene width=10 height=2 fps=20 fallback=end\nactor a = text("hi") at (0, 0)\n@0: a.move(to=(6, 1), dur=0.6)\n'
INF = 'scene width=10 height=2 fps=20 fallback=end period=1 repeat=infinite\nactor a = text("hi") at (0, 0)\n@0: a.move(to=(6, 1), dur=0.6)\n'
d = tempfile.mkdtemp()
def scene(name, text):
    p = os.path.join(d, name); open(p, "w").write(text); return p

def check(name, cond, info=""):
    global fails
    if not cond: fails += 1; print("FAIL", name, info)

def spawn_tty(args, env_extra=None, shell_prefix=""):
    env = dict(os.environ); env.pop("NO_COLOR", None); env.pop("MDGL_REDUCED_MOTION", None); env.update(env_extra or {})
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.clear(); os.environ.update(env)
        os.execv("/bin/sh", ["sh", "-c", shell_prefix + 'exec "$0" "$@"', BIN] + args)
    return pid, fd

def drain(fd, timeout=5.0, until_exit_pid=None):
    out = b""; end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try: chunk = os.read(fd, 65536)
            except OSError: break
            if not chunk: break
            out += chunk
        elif until_exit_pid:
            if os.waitpid(until_exit_pid, os.WNOHANG) != (0, 0): return out, True
    return out, False

def wait(pid, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        p, st = os.waitpid(pid, os.WNOHANG)
        if p: return st
        time.sleep(0.02)
    os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0); return None

def code(st): return None if st is None else (os.WEXITSTATUS(st) if os.WIFEXITED(st) else 128 + os.WTERMSIG(st))

# 1. finite scene on a tty: absolute time, sync output, cursor hidden then restored, exit 0
t0 = time.time(); pid, fd = spawn_tty(["play", scene("fin.mdgl", FIN)])
out, _ = drain(fd, 5, None); st = wait(pid); dt = time.time() - t0
check("finite exit", code(st) == 0, code(st))
check("finite starts hidden", out.startswith(b"\x1b[?25l"), out[:20])
check("finite restores", out.rstrip(b"\r").endswith(b"\x1b[?25h\n") or out.endswith(b"\x1b[?25h\r\n"), out[-30:])
check("finite no clear", b"\x1b[2J" not in out and b"\x1b[3J" not in out and b"\x1b[H\x1b[J" not in out, out[:40])
check("finite sync2026", b"\x1b[?2026h" in out and out.count(b"\x1b[?2026h") <= out.count(b"\x1b[?2026l"), "")
check("finite duration ~0.6s", 0.5 <= dt <= 2.0, dt)
check("finite draws end state", b"\x1b[2;7H" in out, "")

# 2. Ctrl+C on an infinite scene: exit 130, terminal restored
pid, fd = spawn_tty(["play", scene("inf.mdgl", INF)])
time.sleep(0.5); os.write(fd, b"")  # let it run
os.kill(pid, signal.SIGINT)
out, _ = drain(fd, 3, None); st = wait(pid)
check("sigint exit 130", code(st) == 130, code(st))
check("sigint restores cursor", b"\x1b[?25h" in out and out.rstrip().endswith(b"\x1b[?25h"), out[-40:])

# 3. redirected output: plain fallback frame once, no ANSI, no waiting
t0 = time.time()
r = subprocess.run([BIN, "play", scene("inf.mdgl", INF)], capture_output=True, timeout=10)
check("redirect exit", r.returncode == 0, r.returncode)
check("redirect plain", b"\x1b" not in r.stdout and r.stdout.decode().splitlines()[:2] == ["", "      hi"], r.stdout)
check("redirect fast", time.time() - t0 < 1.0, time.time() - t0)

# 4. reduced motion / NO_COLOR on a tty (non-empty only)
for var in ("NO_COLOR", "MDGL_REDUCED_MOTION"):
    pid, fd = spawn_tty(["play", scene("inf.mdgl", INF)], {var: "1"})
    out, _ = drain(fd, 3, pid); st = wait(pid, 3)
    check(var + " plain", code(st) == 0 and b"\x1b" not in out and b"hi" in out, (code(st), out[:40]))
    pid, fd = spawn_tty(["play", scene("fin.mdgl", FIN)], {var: ""})
    out, _ = drain(fd, 5, None); st = wait(pid)
    check(var + " empty still animates", code(st) == 0 and b"\x1b[?2026h" in out, (code(st), out[:30]))

# 5. write error: the terminal goes away mid-play (SIGHUP ignored so the write error is what stops it)
pid, fd = spawn_tty(["play", scene("inf.mdgl", INF)], shell_prefix='trap "" HUP; ')
time.sleep(0.4); os.close(fd); st = wait(pid, 5)
check("write error exit 2", code(st) == 2, code(st))

# 6. stdout write failure in plain mode
with open("/dev/full", "wb") as full:
    r = subprocess.run([BIN, "play", scene("fin.mdgl", FIN)], stdout=full, stderr=subprocess.PIPE, timeout=10)
check("plain write error exit 2", r.returncode == 2, r.returncode)

# 7. exit codes and CLI surface
bad = scene("bad.mdgl", "scene width=8 height=1\n")
r = subprocess.run([BIN, "play", bad], capture_output=True); check("invalid exit 1", r.returncode == 1 and b"1:1:" in r.stderr, (r.returncode, r.stderr))
r = subprocess.run([BIN, "play", os.path.join(d, "nope.mdgl")], capture_output=True); check("unreadable exit 2", r.returncode == 2, r.returncode)
r = subprocess.run([BIN, "play"], capture_output=True); check("usage exit 2", r.returncode == 2, r.returncode)
r = subprocess.run([BIN, "--help"], capture_output=True); check("help exit 0", r.returncode == 0 and b"play FILE" in r.stdout, r.returncode)
r = subprocess.run([BIN, "check", scene("fin.mdgl", FIN)], capture_output=True); check("check", r.returncode == 0 and r.stdout == b"OK MDGL 0.1\n", r.stdout)
r = subprocess.run([BIN, "frames", scene("fin.mdgl", FIN), "--at", "0,0.6"], capture_output=True)
check("frames", r.returncode == 0 and r.stdout.decode().startswith("@0\n") and "@0.6\n" in r.stdout.decode(), r.stdout)
r = subprocess.run([BIN, "frames", scene("fin.mdgl", FIN), "--at", "x"], capture_output=True); check("frames bad time", r.returncode == 2, r.returncode)
print("mdgl play pty tests:", "OK" if not fails else "%d FAILED" % fails)
sys.exit(1 if fails else 0)

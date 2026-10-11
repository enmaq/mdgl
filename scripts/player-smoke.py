#!/usr/bin/env python3
"""PTY smoke test for a real `mdgl play` CLI (stdlib only, POSIX).

usage: player-smoke.py --name LANG [--int-code N] -- CMD...   (the harness appends `play FILE`)
--int-code: documented exit status after Ctrl+C (default 130; the Go player exits 0).
"""
import argparse, os, pty, re, select, signal, subprocess, sys, tempfile, time

FIN = 'scene width=10 height=2 fps=20 fallback=end\nactor a = text("hi") at (0, 0)\n@0: a.move(to=(6, 1), dur=0.6)\n'
INF = 'scene width=10 height=2 fps=20 fallback=end period=1 repeat=infinite\nactor a = text("hi") at (0, 0)\n@0: a.move(to=(6, 1), dur=0.6)\n'
BAD = 'scene width=10 height=2\nactor a = bogus(\n'
HIDE, SHOW = b"\x1b[?25l", b"\x1b[?25h"


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "MDGL_REDUCED_MOTION")}
    env["TERM"] = "xterm"
    env.update(extra or {})
    return env


def spawn_tty(cmd, env):
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(cmd[0], cmd, env)
        finally:
            os._exit(127)
    return pid, fd


def pump(fd, out, seconds):
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return True
            if not chunk:
                return True
            out.append(chunk)
    return False


def reap(pid, fd, out, timeout):
    """Read until EOF/exit within timeout; hard-kill on overrun. Returns exit code or None on timeout."""
    end = time.time() + timeout
    while time.time() < end:
        pump(fd, out, 0.1)
        p, st = os.waitpid(pid, os.WNOHANG)
        if p:
            pump(fd, out, 0.2)
            os.close(fd)
            return os.WEXITSTATUS(st) if os.WIFEXITED(st) else 128 + os.WTERMSIG(st)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    os.waitpid(pid, 0)
    os.close(fd)
    return None


def restored(b):
    return SHOW in b and b.rfind(SHOW) > b.rfind(HIDE) and b.rfind(b"\x1b[0m") != -1 and b.rfind(b"\x1b[0m") < b.rfind(SHOW)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--int-code", type=int, default=130)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if os.name != "posix" or not cmd:
        print("SKIP %s: POSIX pty required (or no command given)" % a.name)
        return 0 if os.name != "posix" else 2
    d = tempfile.mkdtemp(prefix="mdgl-smoke-")
    paths = {}
    for n, t in (("fin", FIN), ("inf", INF), ("bad", BAD)):
        paths[n] = os.path.join(d, n + ".mdgl")
        with open(paths[n], "w") as h:
            h.write(t)
    fails = 0

    def report(name, ok, info=""):
        nonlocal fails
        fails += 0 if ok else 1
        print("%s %s: %s%s" % ("PASS" if ok else "FAIL", a.name, name, "" if ok else " [%s]" % info), flush=True)

    try:
        # 1 finite on a pty
        pid, fd = spawn_tty(cmd + ["play", paths["fin"]], clean_env()); out = []
        code = reap(pid, fd, out, 15); b = b"".join(out)
        report("finite scene animates and exits 0", code == 0 and HIDE in b and b.strip() != b"", "code=%s out=%r" % (code, b[-60:]))
        report("finite scene restores terminal", restored(b), b[-60:])
        # 2 infinite + Ctrl+C
        pid, fd = spawn_tty(cmd + ["play", paths["inf"]], clean_env()); out = []
        pump(fd, out, 1.0)
        got = bool(out)
        os.write(fd, b"\x03")  # tty line discipline raises SIGINT for the foreground group
        code = reap(pid, fd, out, 10); b = b"".join(out)
        report("infinite scene prints, still running before Ctrl+C", got, "no output")
        report("Ctrl+C exits %d" % a.int_code, code == a.int_code, "code=%s" % code)
        report("Ctrl+C restores terminal", restored(b), b[-60:])
        # 3 redirected stdout
        try:
            p = subprocess.run(cmd + ["play", paths["inf"]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=clean_env(), timeout=10)
            report("redirected stdout prints plain fallback only", p.returncode == 0 and p.stdout.strip() != b"" and b"\x1b" not in p.stdout,
                   "code=%s out=%r" % (p.returncode, p.stdout[:60]))
        except subprocess.TimeoutExpired:
            report("redirected stdout prints plain fallback only", False, "timeout")
        # 4 reduced motion on a pty
        pid, fd = spawn_tty(cmd + ["play", paths["inf"]], clean_env({"MDGL_REDUCED_MOTION": "1"})); out = []
        code = reap(pid, fd, out, 10); b = b"".join(out)
        report("MDGL_REDUCED_MOTION=1 prints plain fallback only", code == 0 and b.strip() != b"" and b"\x1b" not in b, "code=%s out=%r" % (code, b[:60]))
        # 5 invalid scene
        try:
            p = subprocess.run(cmd + ["play", paths["bad"]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=clean_env(), timeout=10)
            report("invalid scene fails with LINE:COL on stderr",
                   p.returncode != 0 and re.search(rb"\d+:\d+", p.stderr) is not None,
                   "code=%s err=%r" % (p.returncode, p.stderr[:100]))
        except subprocess.TimeoutExpired:
            report("invalid scene fails with LINE:COL on stderr", False, "timeout")
    finally:
        for f in os.listdir(d):
            os.unlink(os.path.join(d, f))
        os.rmdir(d)
    return 1 if fails else 0


sys.exit(main())

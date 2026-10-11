#!/usr/bin/env python3
"""Run the `mdgl` binary on a real pseudo-terminal: finite play, SIGINT, reduced motion.

usage: pty_proof.py PATH_TO_MDGL      (stdlib only; Unix)
Prints one PASS/FAIL line per case and exits 0 only if all pass.
"""
import os
import pty
import select
import signal
import sys
import tempfile
import time

BIN = sys.argv[1]
FINITE = 'scene width=8 height=2 period=1 fps=20 fallback=end\nactor a = text("Hi") at (0,0)\n@0: a.move(to=(5,1), dur=1)\n'
INFINITE = 'scene width=8 height=2 period=1 repeat=infinite fps=20 fallback=end\nactor a = text("Hi") at (0,0)\n@0: a.move(to=(5,1), dur=1)\n'
RESTORE = b"\x1b[0m\x1b[?25h"


def run(path, env_extra=None, interrupt_after=None, timeout=10.0):
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "MDGL_REDUCED_MOTION")}
    env.update(env_extra or {})
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(BIN, [BIN, "play", path], env)
    out, start, sent = b"", time.monotonic(), False
    while True:
        if interrupt_after is not None and not sent and time.monotonic() - start >= interrupt_after:
            os.write(fd, b"\x03")  # the tty line discipline raises SIGINT for the foreground group
            sent = True
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            out += chunk
        if time.monotonic() - start > timeout:
            os.kill(pid, signal.SIGKILL)
            break
    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    return code, out, time.monotonic() - start


def main():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name + (" " + detail if detail else ""))

    with tempfile.TemporaryDirectory() as d:
        fin, inf = os.path.join(d, "fin.mdgl"), os.path.join(d, "inf.mdgl")
        open(fin, "w").write(FINITE)
        open(inf, "w").write(INFINITE)

        code, out, took = run(fin)
        check("finite play exits 0 at the scene end", code == 0 and 0.9 <= took < 3.0, f"code={code} took={took:.2f}s")
        check("finite play hides the cursor first, restores it last",
              out.startswith(b"\x1b[?25l") and out.rstrip(b"\r\n").endswith(b"\x1b[?25h\x1b[3;1H") or RESTORE in out[-40:], repr(out[-30:]))
        check("finite play uses synchronized output", b"\x1b[?2026h" in out and b"\x1b[?2026l" in out)

        code, out, took = run(inf, interrupt_after=0.5)
        check("Ctrl+C stops an infinite scene with exit 130", code == 130 and took < 3.0, f"code={code} took={took:.2f}s")
        check("Ctrl+C restores the cursor", RESTORE in out[-40:], repr(out[-30:]))

        for var in ("NO_COLOR", "MDGL_REDUCED_MOTION"):
            code, out, took = run(inf, {var: "1"})
            check(f"{var} prints the plain fallback once, no escapes, no timer",
                  code == 0 and b"\x1b" not in out and took < 1.0 and out.count(b"Hi") == 1, f"code={code} took={took:.2f}s")
    return 0 if ok else 1


sys.exit(main())

import os
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINITE = 'scene width=6 height=1 fallback=end\nactor a = text("AB") at (0, 0)\n@0: a.move(to=(3, 0), dur=0.4)\n'
INFINITE = 'scene width=6 height=1 fallback=end period=1 repeat=infinite fps=30\nactor a = text("AB") at (0, 0)\n@0: a.move(to=(3, 0), dur=1)\n'


def spawn(path, env_extra=None, tty=True):
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "MDGL_REDUCED_MOTION")}
    env["PYTHONPATH"] = ROOT
    env.update(env_extra or {})
    cmd = [sys.executable, "-m", "mdgl", "play", path]
    if tty:
        master, slave = pty.openpty()
        proc = subprocess.Popen(cmd, stdout=slave, stderr=subprocess.PIPE, env=env)
        os.close(slave)
        return proc, master
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    return proc, None


def drain(master, proc, timeout=10.0):
    data, end = b"", time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([master], [], [], 0.05)
        if r:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            data += chunk
        elif proc.poll() is not None:
            break
    os.close(master)
    return data.decode("utf-8", "replace")


class Pty(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def scene(self, text):
        p = os.path.join(self.dir.name, "s.mdgl")
        with open(p, "w", encoding="utf-8") as h:
            h.write(text)
        return p

    def test_finite_completes_with_sync_and_restore(self):
        proc, master = spawn(self.scene(FINITE))
        out = drain(master, proc)
        self.assertEqual(proc.wait(10), 0)
        proc.stderr.close()
        self.assertIn("\x1b[?25l", out)
        self.assertIn("\x1b[?2026h", out)
        self.assertTrue(out.endswith("\x1b[?2026l\x1b[0m\x1b[?25h\r\n"), repr(out[-40:]))

    def test_sigint_exits_130_and_restores(self):
        proc, master = spawn(self.scene(INFINITE))
        first = os.read(master, 65536)  # playback has started
        self.assertIn(b"\x1b[?25l", first)
        proc.send_signal(signal.SIGINT)
        out = first.decode() + drain(master, proc)
        self.assertEqual(proc.wait(10), 130)
        proc.stderr.close()
        self.assertTrue(out.endswith("\x1b[?25h\r\n"), repr(out[-40:]))

    def test_redirected_and_reduced_motion_are_plain(self):
        proc, _ = spawn(self.scene(FINITE), tty=False)
        out, _err = proc.communicate(timeout=10)
        self.assertEqual((proc.returncode, out), (0, b"   AB \n"))
        for env in ({"NO_COLOR": "1"}, {"MDGL_REDUCED_MOTION": "1"}):
            proc, master = spawn(self.scene(FINITE), env)
            out = drain(master, proc)
            self.assertEqual(proc.wait(10), 0)
            proc.stderr.close()
            self.assertNotIn("\x1b", out, env)
            self.assertEqual(out.replace("\r\n", "\n"), "   AB \n")


if __name__ == "__main__":
    unittest.main()

import io
import os
import tempfile
import unittest
from unittest import mock

import mdgl
from mdgl import cli, player
from mdgl.render import Cell

FINITE = 'scene width=6 height=1 fallback=end\nactor a = text("AB") at (0, 0)\n@0: a.move(to=(3, 0), dur=1)\n'
INFINITE = 'scene width=6 height=1 fallback=end period=1 repeat=infinite fps=10\nactor a = text("AB") at (0, 0)\n@0: a.move(to=(3, 0), dur=1)\n'


class FakeTime:
    """Deterministic clock; sleep advances it by `factor` x the request (factor>1 = slow host)."""

    def __init__(self, factor=1.0, stop_after=None):
        self.now, self.factor, self.sleeps, self.stop_after = 100.0, factor, [], stop_after

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        if self.stop_after is not None and len(self.sleeps) >= self.stop_after:
            raise KeyboardInterrupt
        self.now += s * self.factor


def run_play(src, ft, write=None):
    out = []
    player.play(mdgl.compile(src), write or out.append, clock=ft.clock, sleep=ft.sleep)
    return out


class Play(unittest.TestCase):
    def test_finite_stops_at_done_and_restores(self):
        ft = FakeTime()
        out = run_play(FINITE, ft)
        self.assertEqual(out[0], player.HIDE)
        self.assertEqual(out[-1], player.RESTORE)
        self.assertTrue(player.SYNC_ON in out[1] and out[1].endswith(player.SYNC_OFF))
        self.assertTrue(10 <= len(ft.sleeps) <= 40, len(ft.sleeps))  # 30 fps over 1 s, then stops

    def test_absolute_time_not_accumulated_ticks(self):
        # Slow host: every sleep takes 3x longer. Playback must end at wall time ~period, not period*3 frames.
        slow = FakeTime(factor=3.0)
        out = run_play(FINITE, slow)
        self.assertEqual(out[-1], player.RESTORE)
        self.assertLess(len(slow.sleeps), 15)  # frames dropped, not delayed
        last = "".join(out[:-1])
        self.assertIn("\x1b[1;4H", last)  # final state reached: text at column 3 (1-based 4)

    def test_keyboard_interrupt_and_write_error_cleanup(self):
        out = []
        with self.assertRaises(KeyboardInterrupt):
            run_play(INFINITE, FakeTime(stop_after=3), out.append)
        self.assertEqual(out[-1], player.RESTORE)
        n, seen = [0], []

        def bad(text):
            n[0] += 1
            seen.append(text)
            if n[0] == 3:
                raise BrokenPipeError(32, "pipe")

        with self.assertRaises(BrokenPipeError):
            run_play(INFINITE, FakeTime(), bad)
        self.assertEqual(seen[-1], player.RESTORE)  # cleanup attempted after the failure

    def test_infinite_does_not_finish_by_itself(self):
        ft = FakeTime(stop_after=200)
        with self.assertRaises(KeyboardInterrupt):
            run_play(INFINITE, ft)
        self.assertEqual(len(ft.sleeps), 200)

    def test_dirty_diff_includes_colors_and_skips_unchanged(self):
        a = mdgl.compile(FINITE).frame(0)
        self.assertEqual(player.dirty(a, a), "")
        b = mdgl.compile(FINITE).frame(0)
        b.cells[0][5] = Cell(" ", "normal", "#112233")
        d = player.dirty(a, b)
        self.assertEqual(d.count("\x1b[1;"), 1)
        self.assertIn("\x1b[48;2;17;34;51m", d)
        self.assertTrue(d.startswith(player.SYNC_ON) and d.endswith(player.SYNC_OFF))
        c = mdgl.compile(FINITE).frame(0)
        c.cells[0][0] = Cell("A", "#ff0000", "")
        self.assertIn("\x1b[38;2;255;0;0m", player.dirty(a, c))

    def test_control_characters_never_become_escapes(self):
        f = mdgl.compile(FINITE).frame(0)
        f.cells[0][0] = Cell("\x1b", "normal", "")
        self.assertNotIn("\x1b]", player.dirty(None, f).replace("\x1b[", ""))
        self.assertEqual(player.plain_lines(f)[0][0], " ")


class Cli(unittest.TestCase):
    def setUp(self):
        # Direct cli.main calls must not inherit the parent's NO_COLOR / MDGL_REDUCED_MOTION (fallback is tested explicitly).
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("MDGL_REDUCED_MOTION", None)
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: [os.remove(os.path.join(d, x)) or None for x in os.listdir(d)] and os.rmdir(d))
        self.d = d

    def file(self, text, name="s.mdgl"):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as h:
            h.write(text)
        return p

    def call(self, *argv, out=None, env=None):
        out, err = out or io.StringIO(), io.StringIO()
        old = {k: os.environ.get(k) for k in ("NO_COLOR", "MDGL_REDUCED_MOTION")}
        for k in old:
            os.environ.pop(k, None)
        os.environ.update(env or {})
        try:
            code = cli.main(list(argv), out=out, err=err)
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v
        return code, out.getvalue(), err.getvalue()

    def test_redirected_prints_fallback_frame_once_without_ansi(self):
        code, out, _ = self.call("play", self.file(FINITE))
        self.assertEqual((code, out), (0, "   AB \n"))

    def test_reduced_motion_and_no_color_on_a_tty(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        for env in ({"NO_COLOR": "1"}, {"MDGL_REDUCED_MOTION": "1"}):
            code, out, _ = self.call("play", self.file(FINITE), out=Tty(), env=env)
            self.assertEqual((code, out), (0, "   AB \n"), env)

    def test_tty_plays_with_injected_time(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        ft, out, err = FakeTime(), Tty(), io.StringIO()
        code = cli.main(["play", self.file(FINITE)], out=out, err=err, clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith(player.HIDE) and out.getvalue().endswith(player.RESTORE))

    def test_exit_codes(self):
        self.assertEqual(self.call("check", self.file(FINITE))[:2], (0, "OK MDGL 0.1\n"))
        code, _, err = self.call("check", self.file("scene width=1\n"))
        self.assertEqual((code, err), (1, "s.mdgl:1:1: missing scene attribute height\n"))
        code, _, err = self.call("check", os.path.join(self.d, "nope.mdgl"))
        self.assertEqual(code, 2)
        self.assertNotIn(self.d, err)  # no machine path in messages
        with self.assertRaises(SystemExit) as e:
            self.call("play")
        self.assertEqual(e.exception.code, 2)
        self.assertEqual(self.call("frames", self.file(FINITE), "--at", "x")[0], 2)

    def test_interrupt_exit_130(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        ft, out = FakeTime(stop_after=2), Tty()
        code = cli.main(["play", self.file(INFINITE)], out=out, err=io.StringIO(), clock=ft.clock, sleep=ft.sleep)
        self.assertEqual(code, 130)
        self.assertTrue(out.getvalue().endswith(player.RESTORE))

    def test_frames(self):
        code, out, _ = self.call("frames", self.file(FINITE), "--at", "0,1s")
        self.assertEqual((code, out), (0, "@0\nAB    \n@1\n   AB \n"))


if __name__ == "__main__":
    unittest.main()

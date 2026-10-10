import glob
import os
import re
import unittest

import mdgl

CONF = os.path.join(os.path.dirname(__file__), "..", "..", "conformance")
S = 'scene width=8 height=1 fallback=end\nactor a = text("AB") at (0, 0)\n'


def row(frame, i=0):
    return "".join(c.rune for c in frame.cells[i])


class Legacy(unittest.TestCase):
    def test_expect_fixtures(self):
        n = 0
        for f in sorted(glob.glob(os.path.join(CONF, "*.expect"))):
            if os.path.exists(f[:-7] + ".err"):
                continue
            with open(f[:-7] + ".mdgl", encoding="utf-8") as h:
                a = mdgl.compile(h.read())
            with open(f, encoding="utf-8") as h:
                lines = h.read().split("\n")
            for i, ln in enumerate(lines):
                m = re.match(r"@(\S+)", ln)
                if m:
                    want = [r.ljust(a.width) for r in lines[i + 1:i + 1 + a.height]]
                    self.assertEqual(a.frame(float(m.group(1))).lines(), want, (f, ln))
                    n += 1
        self.assertGreater(n, 50)


class Observables(unittest.TestCase):
    def test_static_color_background_done(self):
        a = mdgl.compile(S.replace("(0, 0)", "(0, 0) color=red"))
        f = a.frame(0)
        self.assertEqual([(c.rune, c.color, c.background) for c in f.cells[0][:3]],
                         [("A", "red", ""), ("B", "red", ""), (" ", "normal", "")])
        self.assertTrue(f.done)

    def test_fade_blend_and_done_boundary(self):
        a = mdgl.compile(S + "@0: a.fade(in, dur=2)\n")
        mid = a.frame(1.0)
        self.assertEqual((mid.cells[0][0].color, mid.done), ("#808080", False))
        end = a.frame(2.0)
        self.assertEqual((end.cells[0][0].color, end.done), ("normal", True))
        self.assertEqual(a.frame(0).lines(), ["        "])

    def test_color_switch_half(self):
        a = mdgl.compile(S + "@0: a.color(to=red, dur=2)\n")
        self.assertEqual(a.frame(0.99).cells[0][0].color, "normal")
        self.assertEqual(a.frame(1.0).cells[0][0].color, "red")

    def test_fallback_and_seeking_pure(self):
        a = mdgl.compile(S + "@0: a.move(to=(2, 0), dur=1)\n")
        self.assertEqual(row(a.fallback_frame()), "  AB    ")
        self.assertEqual(row(a.frame(0.5)), " AB     ")
        self.assertEqual(a.frame(0.5).lines(), a.frame(0.5).lines())
        self.assertEqual(row(a.frame_ns(500_000_000)), " AB     ")

    def test_repeat_boundaries(self):
        a = mdgl.compile("scene width=8 height=1 fallback=start period=2 repeat=2\n"
                         'actor a = text("AB") at (0, 0)\n@0: a.move(to=(2, 0), dur=1)\n')
        self.assertEqual((row(a.frame(2.0)), a.frame(2.0).done), ("AB      ", False))
        self.assertEqual((row(a.frame(3.5)), a.frame(3.5).done), ("  AB    ", False))
        self.assertEqual((row(a.frame(4.0)), a.frame(4.0).done), ("  AB    ", True))
        inf = mdgl.compile("scene width=8 height=1 fallback=end period=1 repeat=infinite\n" + S.split("\n", 1)[1])
        self.assertFalse(inf.frame(1e5).done)

    def test_static_scene_done_and_type_wipe_blink(self):
        self.assertTrue(mdgl.compile(S).frame(0).done)
        t = mdgl.compile(S + "@0: a.type(per_char=1)\n")
        self.assertEqual([row(t.frame(x)) for x in (0.9, 1, 2)], ["        ", "A       ", "AB      "])
        b = mdgl.compile(S + "@0: a.blink(times=1, dur=2)\n")
        self.assertEqual([row(b.frame(x)) for x in (0.5, 1.5, 2)], ["AB      ", "        ", "AB      "])

    def test_cube_dots_wrong_rotation_changes_output(self):
        base = "scene width=12 height=6 fallback=end\nactor c = cube(size=6) at (0, 0)\n"
        r0 = mdgl.compile(base).frame(0).lines()
        r1 = mdgl.compile(base + "@0: c.rotate(y=45, dur=1)\n").frame(1).lines()
        self.assertNotEqual(r0, r1)
        self.assertTrue(any(ord(ch) >= 0x2800 for ln in r0 for ch in ln))

    def test_parent_z_and_wide_glyph(self):
        a = mdgl.compile('scene width=4 height=1 fallback=end\nactor a = text("x") at (0, 0) z=1\n'
                         'actor b = text("y") at (0, 0)\n')
        self.assertEqual(row(a.frame(0)), "x   ")
        w = mdgl.compile('scene width=4 height=1 fallback=end\nactor a = text("\U0001F1FA\U0001F1F8é") at (0, 0)\n')
        self.assertEqual(row(w.frame(0)), "�e  ")


if __name__ == "__main__":
    unittest.main()

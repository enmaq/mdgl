import json
import unittest

import mdgl
from mdgl import adapter

S = "scene width=4 height=1 fallback=end\n"
FADE = S + 'actor a = text("A") at (0,0) color=green\n@2.4: a.fade(in, dur=0.8)\n'
COLOR = S + 'actor a = text("A") at (0,0)\n@8: a.color(to=red, dur=0.4)\n'


def fg(src, ns):
    return mdgl.compile(src).frame_ns(ns).cells[0][0].color


def via_adapter(src, ns):
    line = json.dumps({"v": 1, "id": "x", "op": "frame", "source": src, "time_ns": ns, "width": 4, "height": 1})
    return adapter.handle(line.encode())["cells"][0][0]["fg"]


class IntegerNsProgress(unittest.TestCase):
    def test_fade_exact_midpoint(self):
        # progress is exactly 0.5 at 2.8 s: 127.5 rounds half away from zero to 128 = 0x80
        self.assertEqual(fg(FADE, 2_800_000_000), "#008000")
        self.assertEqual(via_adapter(FADE, 2_800_000_000), "#008000")

    def test_fade_shifted_control_and_neighbours(self):
        ctl = S + 'actor a = text("A") at (0,0) color=green\n@4: a.fade(in, dur=0.4)\n'
        self.assertEqual(fg(ctl, 4_200_000_000), "#008000")
        self.assertEqual(fg(FADE, 2_799_999_999), "#007f00")  # one ns before the midpoint
        self.assertEqual(fg(FADE, 2_800_000_001), "#008000")

    def test_color_switches_exactly_at_half(self):
        self.assertEqual(fg(COLOR, 8_199_999_999), "normal")
        self.assertEqual(fg(COLOR, 8_200_000_000), "red")
        self.assertEqual(via_adapter(COLOR, 8_200_000_000), "red")
        self.assertEqual(fg(COLOR.replace("@8", "@4"), 4_200_000_000), "red")  # shifted control

    def test_interval_end_clamp_and_freeze_unchanged(self):
        self.assertEqual(fg(FADE, 3_200_000_000), "green")  # end: full opacity keeps the named colour
        self.assertEqual(fg(FADE, 60_000_000_000), "green")  # frozen afterwards
        self.assertEqual(mdgl.compile(FADE).frame_ns(2_399_999_999).lines(), ["    "])  # before begin: unrevealed

    def test_type_floor_still_exact(self):
        t = S + 'actor a = text("AB") at (0,0)\n@0: a.type(per_char=1)\n'
        a = mdgl.compile(t)
        self.assertEqual([a.frame_ns(n).lines()[0] for n in (999_999_999, 1_000_000_000, 2_000_000_000)],
                         ["    ", "A   ", "AB  "])


if __name__ == "__main__":
    unittest.main()

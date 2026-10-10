import glob
import os
import unittest

import mdgl
from mdgl import MdglError, load, parse

BASE = "scene width=8 height=2 fallback=end\n"
CONF = os.path.join(os.path.dirname(__file__), "..", "..", "conformance")


def first(src):
    r = mdgl.check(src)
    return "%d:%d: %s" % (r[0]["line"], r[0]["col"], r[0]["message"]) if r else ""


class ErrCorpus(unittest.TestCase):
    def test_err_fixtures(self):
        files = sorted(glob.glob(os.path.join(CONF, "*.err")))
        self.assertTrue(files)
        for f in files:
            with open(f[:-4] + ".mdgl", encoding="utf-8") as s, open(f, encoding="utf-8") as e:
                self.assertEqual(first(s.read()), e.read().strip(), f)

    def test_valid_fixtures(self):
        for f in sorted(glob.glob(os.path.join(CONF, "*.mdgl"))):
            if os.path.exists(f[:-5] + ".err") or os.path.basename(f).startswith("obs_diag"):
                continue
            with open(f, encoding="utf-8") as s:
                self.assertEqual(mdgl.check(s.read()), [], f)


class ObsDiagnostics(unittest.TestCase):
    def test_obs_diag_fixtures(self):
        import json
        files = sorted(glob.glob(os.path.join(CONF, "observable", "obs_diag*.obs.json")))
        self.assertEqual([os.path.basename(f) for f in files],
                         ["obs_diag_multibyte_2.obs.json", "obs_diag_multibyte_3.obs.json"])
        for f in files:
            with open(f, encoding="utf-8") as h:
                obs = json.load(h)
            with open(os.path.join(os.path.dirname(f), obs["source_file"]), encoding="utf-8") as h:
                self.assertEqual(mdgl.check(h.read()), [obs["diagnostic"]], f)


class Model(unittest.TestCase):
    def test_source_located_model(self):
        sc = load(BASE + 'actor a = text("héé") at (center, 0)\n@0.5s: a.fade(in, dur=1)\n')
        self.assertEqual((sc.width, sc.height, sc.period), (8, 2, 1.5))
        a = sc.actors[0]
        self.assertEqual((a.pos.line, a.width, a.x.text), (2, 3.0, "center"))
        act = sc.actions[0]
        self.assertEqual((act.begin, act.duration, act.property, act.ease), (0.5, 1.0, "opacity", "linear"))

    def test_parse_is_unchecked(self):
        self.assertFalse(parse(BASE).checked)
        self.assertTrue(load(BASE).checked)


class Diagnostics(unittest.TestCase):
    def test_byte_columns(self):
        # é is two bytes: the '$' after it is at byte column 19
        self.assertEqual(first(BASE + 'actor a = text("é")$ at (0,0)\n'), '2:21: unexpected character "$"')

    def test_escapes(self):
        ok = BASE + 'actor a = text("a\\x41\\u00e9\\n") at (0,0)\n'
        self.assertEqual(first(ok), "2:1: text contains a control character")
        self.assertEqual(first(BASE + 'actor a = text("\\q") at (0,0)\n'), "2:16: invalid string escape")
        self.assertEqual(first(BASE + 'actor a = text("x) at (0,0)\n'), "2:16: unterminated string")

    def test_numbers_finite_decimal(self):
        for bad in ("1e5", "inf", "nan"):
            self.assertNotEqual(first(BASE + 'actor a = circle(%s) at (0,0)\n' % bad), "")
        self.assertEqual(first(BASE + "actor a = circle(1.) at (0,0)\n"), "")
        self.assertEqual(first(BASE + "actor a = circle(.5) at (-1,+2)\n"), "")

    def test_order_and_refs(self):
        self.assertEqual(first("actor a = circle(1) at (0,0)\n" + BASE), "1:1: scene must precede actors")
        self.assertEqual(first(BASE + "@0: a.fade(in,dur=1)\nactor a = circle(1) at (0,0)\n"), "3:1: actors must precede actions")
        fwd = BASE + "actor a = circle(1) at (0,0) parent=b\nactor b = circle(1) at (0,0)\n"
        self.assertEqual(first(fwd), "")
        cyc = fwd.replace("actor b = circle(1) at (0,0)", "actor b = circle(1) at (0,0) parent=a")
        self.assertEqual(first(cyc), "2:1: parent cycle involving a")
        self.assertEqual(first(BASE + "actor a = circle(1) at (0,0) parent=q\n"), '2:1: unknown parent "q"; did you mean "a"?')

    def test_actions(self):
        a = BASE + 'actor t = text("ab") at (0,0)\nactor c = cube(size=4) at (0,0)\n'
        cases = [
            ("@0: t.rotate(x=1,dur=1)", "4:1: rotate requires a cube actor"),
            ("@0: c.type(per_char=1)", "4:1: type requires a text actor"),
            ("@0: t.fade(in)", "4:1: dur must be positive"),
            ("@0: t.fade(dur=1)", "4:1: fade requires in or out"),
            ("@0: t.fade(in,dur=1,dur=2)", "4:1: duplicate argument dur"),
            ("@0: t.blink(times=0,dur=1)", "4:1: times must be an integer in 1..1000"),
            ("@0: t.scale(to=17,dur=1)", "4:1: scale to must be positive and <=16"),
            ("@0: c.rotate(x=90deg,y=1.5rad,dur=1)", ""),
            ("@0: c.rotate(x=20000,dur=1)", "4:1: rotation must be within -10000..10000"),
            ("@0: t.move(to=(top,0),dur=1)", "4:1: invalid coordinate \"top\""),
            ("@0: t.move(to=(1,1),dur=1)\n@0.5: t.move(to=(2,1),dur=1)", "5:1: overlapping position actions on t"),
            ("@0: t.move(to=(1,1),dur=1)\n@1: t.move(to=(2,1),dur=1)", ""),
            ("@0: t.fade(in,dur=1)\n@0: t.move(to=(2,1),dur=1)", ""),
            ("@0: t.fdae(in,dur=1)", '4:1: unknown action "fdae"; did you mean "fade"?'),
            ("@0: t.fade(in,dur=1,ease=bonce)", '4:1: unknown easing "bonce"; did you mean "bounce"?'),
            ("@0: t.fade(in,dur=0.0000000001)", "4:1: dur rounds to zero at nanosecond precision"),
            ("@61: t.fade(in,dur=1)", "4:1: action end must be <=60"),
            ("@0: t.fade(in,dur=1", '4:1: expected ","'),
            ("@0: t.fade(in,dur=1,)", "4:21: trailing comma"),
        ]
        for tail, want in cases:
            self.assertEqual(first(a + tail + "\n"), want, tail)

    def test_scene_rules(self):
        self.assertEqual(first("scene width=8 height=2 fallback=@3 period=2\n"), "1:1: fallback time must be within period")
        self.assertEqual(first("scene width=8 height=2 fallback=end repeat=2\n"), "1:1: repeat requires explicit period")
        self.assertEqual(first("scene width=8 height=2 fallback=end repeat=infinite period=1\n"), "")
        self.assertEqual(first("scene width=8 height=2 fallback=end fps=31\n"), "1:1: fps must be an integer in 1..30")
        self.assertEqual(first("camera x\n"), "1:1: camera is reserved; not yet supported in 0.1")
        self.assertEqual(first("text(\"a\")\n" + BASE)[:30], '1:1: unknown statement "text";')

    def test_limits(self):
        many = BASE + "".join("actor a%d = circle(1) at (0,0)\n" % i for i in range(65))
        self.assertEqual(first(many), "66:1: actor limit 64 exceeded")
        self.assertEqual(first("scene width=8 height=2 fallback=end\n" + "#" * 17000), "2:1: line exceeds 16 KiB")
        self.assertEqual(first(BASE + 'actor a = text("' + "x" * 1025 + '") at (0,0)\n'), "2:1: text exceeds 1024 graphemes")


if __name__ == "__main__":
    unittest.main()

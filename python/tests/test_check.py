import unittest

from mdgl import __version__, check

BASE = "scene width=8 height=1 fallback=end\n"


def pad(total):
    return BASE + "\n" * (total - len(BASE))


def line(n):
    return BASE + "#" + "x" * (n - 1) + "\n"


def actors(n):
    return BASE + "".join("actor a%d = circle(1) at (0, 0)\n" % i for i in range(n))


def actions(n):
    return BASE + 'actor a = text("AB") at (0, 0)\n' + "".join(
        "@%.2f: a.move(to=(%d, 0), dur=0.01)\n" % (i * 0.05, i % 2) for i in range(n))


CASES = [
    ("minimal", BASE, True),
    ("version", "mdgl 0.1\n" + BASE, True),
    ("order", "scene fallback=start height=60 width=200\n", True),
    ("comments", "# hi\n\n" + BASE, True),
    ("empty", "\n", False),
    ("no width", "scene height=1 fallback=end\n", False),
    ("no height", "scene width=8 fallback=end\n", False),
    ("no fallback", "scene width=8 height=1 period=4\n", False),
    ("width 0", "scene width=0 height=1 fallback=end\n", False),
    ("width 201", "scene width=201 height=1 fallback=end\n", False),
    ("height 61", "scene width=8 height=61 fallback=end\n", False),
    ("dup key", "scene width=8 width=9 height=1 fallback=end\n", False),
    ("unknown key", "scene width=8 height=1 fallback=end bogus=1\n", False),
    ("dup scene", BASE + BASE, False),
    ("actor first", "actor a = circle(1) at (0, 0)\n" + BASE, False),
    ("actor after action", BASE + "@0: a.fade(in, dur=1)\nactor a = circle(1) at (0, 0)\n", False),
    ("unknown stmt", BASE + "bogus\n", False),
    ("size 256KiB", pad(262144), True),
    ("size +1", pad(262145), False),
    ("line 16384", line(16384), True),
    ("line 16385", line(16385), False),
    ("64 actors", actors(64), True),
    ("65 actors", actors(65), False),
    ("1024 actions", actions(1024), True),
    ("1025 actions", actions(1025), False),
]


class TestCheck(unittest.TestCase):
    def test_case_table(self):
        for name, src, ok in CASES:
            with self.subTest(name):
                self.assertEqual(check(src) == [], ok, check(src))

    def test_non_str(self):
        with self.assertRaises(TypeError):
            check(None)

    def test_version(self):
        self.assertEqual(__version__, "0.2.0")


if __name__ == "__main__":
    unittest.main()

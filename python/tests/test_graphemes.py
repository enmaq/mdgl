import unittest

import mdgl
from mdgl.graphemes import UNICODE_VERSION, clusters
from mdgl.model import glyphs

BASE = "scene width=8 height=2 fallback=end\n"
FLAG = "\U0001F1FA\U0001F1F8"
HANGUL = "한"  # decomposed L V T
DEVA = "का"  # KA + spacing mark AA
ARABIC = "بَ"  # BEH + FATHA
ENGLAND = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
ECUTE = "é"


def n(text):
    return len(list(clusters(text)))


def type_scene(text, per_char):
    return BASE + 'actor t = text("%s") at (0,0)\n@0: t.type(per_char=%s)\n' % (text, per_char)


class Clusters(unittest.TestCase):
    def test_version(self):
        self.assertEqual(UNICODE_VERSION, "15.0.0")

    def test_scalars_vs_clusters(self):
        for text, scalars, count in [(FLAG, 2, 1), (FLAG * 2, 4, 2), (HANGUL, 3, 1), (DEVA, 2, 1),
                                     (ARABIC, 2, 1), (ENGLAND, 7, 1), (ECUTE, 2, 1), ("\U0001F1FA", 1, 1),
                                     ("\U0001F1FA\U0001F1F8\U0001F1E9", 3, 2), ("؀a", 2, 1),
                                     ("\U0001F468‍\U0001F469", 3, 1), ("a\r\nb", 4, 3)]:
            self.assertEqual((len(text), n(text)), (scalars, count), ascii(text))

    def test_widths_and_glyphs(self):
        self.assertEqual([w for _, w in clusters(FLAG + "a" + "中" + ECUTE)], [2, 1, 2, 1])
        self.assertEqual(glyphs(FLAG + "a" + ECUTE + DEVA), ["\ufffd", "a", "e", "\ufffd"])  # Devanagari KA+AA: cell width 2 in uniseg v0.4.7 (reference parity)


class Limits(unittest.TestCase):
    def test_flag_clusters_count_not_scalars(self):
        self.assertEqual(mdgl.check(type_scene(FLAG * 600, "0.1")), [])
        sc = mdgl.load(type_scene(FLAG * 600, "0.1"))
        self.assertEqual((sc.actors[0].width, sc.actions[0].duration), (600.0, 60.0))
        self.assertEqual(mdgl.check(type_scene(FLAG * 601, "0.1"))[0]["message"], "action end must be <=60")
        self.assertEqual(mdgl.check(BASE + 'actor t = text("%s") at (0,0)\n' % (FLAG * 1024)), [])
        self.assertEqual(mdgl.check(BASE + 'actor t = text("%s") at (0,0)\n' % (FLAG * 1025))[0]["message"],
                         "text exceeds 1024 graphemes")

    def test_hangul_clusters(self):
        sc = mdgl.load(type_scene(HANGUL * 700, "0.05"))
        self.assertEqual((sc.actors[0].width, sc.actions[0].duration), (700.0, 35.0))
        self.assertEqual(mdgl.check(BASE + 'actor t = text("%s") at (0,0)\n' % (HANGUL * 1024)), [])
        self.assertEqual(mdgl.check(BASE + 'actor t = text("%s") at (0,0)\n' % (HANGUL * 1025))[0]["message"],
                         "text exceeds 1024 graphemes")

    def test_marks_do_not_add_width(self):
        for t in (DEVA, ARABIC, ENGLAND, ECUTE):
            self.assertEqual(mdgl.load(BASE + 'actor t = text("%s") at (0,0)\n' % t).actors[0].width, 1.0 if t != ENGLAND else 1.0)


if __name__ == "__main__":
    unittest.main()

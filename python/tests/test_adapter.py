import io
import json
import unittest

from mdgl import adapter

SRC = 'scene width=8 height=1 fallback=end\nactor a = text("AB") at (0, 0)\n@0: a.fade(in, dur=2)\n'


def req(**kw):
    base = {"v": 1, "id": "r", "op": "frame", "source": SRC, "time_ns": 1000000000, "width": 8, "height": 1}
    base.update(kw)
    return json.dumps(base)


def run(*lines, eof_newline=True):
    data = "\n".join(lines) + ("\n" if eof_newline else "")
    out = io.BytesIO()
    adapter.main(io.BytesIO(data.encode("utf-8", "surrogatepass")), out)
    return [json.loads(x) for x in out.getvalue().decode().splitlines()]


def one(line):
    return run(line)[0]


class Transport(unittest.TestCase):
    def test_frame_normal_has_done_fallback_omits(self):
        r = one(req())
        self.assertEqual((r["ok"], r["done"], r["cells"][0][0]), (True, False, {"r": "A", "fg": "#808080", "bg": ""}))
        f = one(req(fallback=True, time_ns="ignored"))
        self.assertTrue(f["ok"])
        self.assertNotIn("done", f)

    def test_check_byte_columns(self):
        r = one(json.dumps({"v": 1, "id": "c", "op": "check",
                            "source": 'scene width=8 height=1 fallback=end\nactor a = text("é") $\n'}))
        self.assertEqual(r["diagnostics"], [{"line": 2, "col": 22, "message": 'unexpected character "$"'}])
        self.assertEqual(one(json.dumps({"v": 1, "id": "c", "op": "check", "source": SRC}))["diagnostics"], [])

    def test_mathematical_integers(self):
        for ok in ("1000000000", "1.0", "1e9", "9007199254740991"):
            self.assertTrue(one(req().replace("1000000000", ok))["ok"], ok)
        for bad in ("9007199254740991.1", "9007199254740992", "1.5", "-1", '"1"', "true", "null", "1e999999999999"):
            r = one(req().replace("1000000000", bad))
            self.assertEqual((r["ok"], r["error"]["code"]), (False, "bad_request"), bad)
            self.assertEqual(r["id"], "r")

    def test_strict_json(self):
        for bad in ('{"v":1,"id":"x","op":"check","source":NaN}', '{"v":Infinity,"id":"x"}', "[]", "{", "",
                    '{"v":1,"id":"x","op":"check","source":"\\ud800"}'):
            r = one(bad)
            self.assertEqual((r["ok"], r["error"]["code"]), (False, "bad_request"), bad)

    def test_version_and_ops(self):
        r = one(json.dumps({"v": 2, "id": "e8", "op": "check", "source": ""}))
        self.assertEqual((r["id"], r["error"]["code"]), ("e8", "unsupported_version"))
        self.assertEqual(one(json.dumps({"id": "x", "op": "check", "source": ""}))["error"]["code"], "bad_request")
        self.assertEqual(one(req(op="play"))["error"]["code"], "bad_request")
        self.assertEqual(one(req(width=201))["error"]["code"], "bad_request")

    def test_invalid_source_frame(self):
        r = one(req(source=""))
        self.assertEqual((r["error"]["code"], r["error"]["diagnostics"]),
                         ("invalid_source", [{"line": 1, "col": 1, "message": "missing scene"}]))

    def test_line_bound_blank_and_eof(self):
        big = '{"v":1,"id":"x","op":"check","source":"%s"}' % ("a" * adapter.MAX_LINE)
        rs = run(big, "", req(id="after"))
        self.assertEqual([r["error"]["code"] for r in rs[:2]], ["bad_request", "bad_request"])
        self.assertIsNone(rs[0]["id"])
        self.assertEqual((rs[2]["id"], rs[2]["ok"]), ("after", True))
        last = run(req(id="eof"), eof_newline=False)
        self.assertEqual((len(last), last[0]["id"]), (1, "eof"))

    def test_clamp_and_purity(self):
        a, b = one(req(width=200, height=60)), one(req(width=200, height=60))
        self.assertEqual((a["width"], a["height"]), (8, 1))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()

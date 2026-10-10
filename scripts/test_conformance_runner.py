"""Self-tests for conformance-runner.py using scripts/mock_adapter.py (a test double, not an MDGL implementation).

  cd v/mdgl && python3 -I -m unittest scripts/test_conformance_runner.py -v
"""
import decimal, fractions, importlib.util, json, random, shlex, subprocess, sys, tempfile, time, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER, MOCK, CONF = HERE / "conformance-runner.py", HERE / "mock_adapter.py", HERE.parent / "conformance"
OBS = CONF / "observable"
spec = importlib.util.spec_from_file_location("runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

SRC = 'scene width=4 height=1 fallback=end\nactor a = text("AB") at (0, 0) color=red\n@0: a.fade(in, dur=2)\n'


def cell(r=" ", fg="normal", bg=""):
    return {"r": r, "fg": fg, "bg": bg}


def row(s, fg="normal"):
    return [cell(c, fg if c != " " else "normal") for c in s]


def frame(s, fg="normal", done=True, **kw):
    r = {"ok": True, "width": len(s), "height": 1, "cells": [row(s, fg)]}
    if done is not None:
        r["done"] = done
    r.update(kw)
    return r


def obs(frames, cls="timed", **kw):
    return json.dumps({"source_file": "x.mdgl", "cols": 4, "rows": 1, "class": cls, "derivation": "SPEC test", "frames": frames, **kw})


def ofr(t, s, fg="normal", done=False):
    return {"time": t, "cells": [row(s, fg)], "done": done}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.suite = self.tmp / "suite"
        self.suite.mkdir()

    def run_runner(self, files, script, *extra, timeout=30):
        for n, c in files.items():
            (self.suite / n).write_text(c, encoding="utf-8", newline="")
        (self.tmp / "script.json").write_text(json.dumps({"log": str(self.tmp / "log.jsonl"), **script}), encoding="utf-8")
        cmd = [sys.executable, "-I", str(RUNNER), "--adapter", f"{sys.executable} -I {shlex.quote(str(MOCK))} {self.tmp / 'script.json'}",
               "--suite", str(self.suite), *extra]
        t0 = time.monotonic()
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        self.elapsed = time.monotonic() - t0
        return p

    def requests(self):
        return [json.loads(l) for l in (self.tmp / "log.jsonl").read_text(encoding="utf-8").splitlines()]


GOOD = {"x.mdgl": SRC, "x.obs.json": obs([ofr("0", "    ", done=False), ofr("2", "AB  ", "red", True)])}
GOOD_KEYS = {"by_key": {"frame:0": frame("    ", done=False), "frame:2000000000": frame("AB  ", "red", True)}}


class Pass(Base):
    def test_all_pass_mixed_formats(self):
        files = dict(GOOD)
        files.update({"leg.mdgl": SRC, "leg.expect": "@2\nAB\n", "d.mdgl": 'scene width=1 height=1\n', "d.err": "1:1: missing scene attribute fallback\n"})
        keys = dict(GOOD_KEYS["by_key"])
        keys["frame:2000000000"] = frame("AB  ", "red", True)
        keys["check:scene width=1 height=1\n"] = {"ok": True, "diagnostics": [{"line": 1, "col": 1, "message": "missing scene attribute fallback"}]}
        p = self.run_runner(files, {"by_key": keys})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("summary: 3 passed, 0 failed", p.stdout)
        self.assertIn("PASS timed x", p.stdout)

    def test_json_report(self):
        p = self.run_runner(GOOD, GOOD_KEYS, "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)
        self.assertEqual((r["protocol"], r["total"], r["passed"], r["failed"]), (1, 1, 1, 0))
        self.assertEqual(r["results"][0]["status"], "pass")


class Failures(Base):
    def fails(self, files, keys, needle):
        p = self.run_runner(files, {"by_key": keys})
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("FAIL", p.stdout)
        self.assertIn(needle, p.stdout)

    def test_wrong_fg(self):
        self.fails(GOOD, {**GOOD_KEYS["by_key"], "frame:2000000000": frame("AB  ", "blue", True)}, ".fg: expected 'red' got 'blue'")

    def test_wrong_bg(self):
        bad = frame("AB  ", "red", True)
        bad["cells"][0][3]["bg"] = "#000001"
        self.fails(GOOD, {**GOOD_KEYS["by_key"], "frame:2000000000": bad}, "cell[0][3].bg")

    def test_wrong_done(self):
        self.fails(GOOD, {**GOOD_KEYS["by_key"], "frame:2000000000": frame("AB  ", "red", False)}, "done: expected True got False")

    def test_wrong_glyph_in_expect(self):
        files = {"leg.mdgl": SRC, "leg.expect": "@2\nAB\n"}
        self.fails(files, {"frame:2000000000": frame("AC  ", "red", True)}, "expected 'AB  ' got 'AC  '")

    def test_diag_rune_count_instead_of_bytes(self):
        src = 'scene width=8 height=1 fallback=end\nactor a = text("é") $\n'
        d = {"line": 2, "col": 22, "message": 'unexpected character "$"'}
        files = {"m.mdgl": src, "m.obs.json": json.dumps({"source_file": "m.mdgl", "cols": 8, "rows": 1, "class": "diagnostic", "derivation": "bytes", "diagnostic": d})}
        self.fails(files, {"check:" + src: {"ok": True, "diagnostics": [{**d, "col": 21}]}}, "first diagnostic col: expected 22 got 21")
        p = self.run_runner(files, {"by_key": {"check:" + src: {"ok": True, "diagnostics": [d, {"line": 9, "col": 9, "message": "extra"}]}}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)  # only the FIRST diagnostic is compared

    def test_diag_expected_but_none(self):
        files = {"d.mdgl": "x\n", "d.err": "1:1: boom\n"}
        self.fails(files, {"check:x\n": {"ok": True, "diagnostics": []}}, "got none")

    def test_unexpected_invalid_source_is_fixture_failure(self):
        inv = {"ok": False, "error": {"code": "invalid_source", "message": "m", "diagnostics": [{"line": 1, "col": 1, "message": "nope"}]}}
        self.fails(GOOD, {"frame:0": inv}, "unexpected invalid_source")


class Seeking(Base):
    FILES = {"x.mdgl": SRC, "x.obs.json": obs([ofr("2", "AB  ", "red", True), ofr("0", "    "), ofr("2", "AB  ", "red", True), ofr("0", "    ")])}

    def test_consistent(self):
        p = self.run_runner(self.FILES, GOOD_KEYS)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([r["time_ns"] for r in self.requests()], [2000000000, 0, 2000000000, 0])

    def test_inconsistent_repeat_detected(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([ofr("2", "AB  ", "red", True), ofr("2", "AB  ", "red", True)])}
        p = self.run_runner(files, {"by_key": {"frame:2000000000": [frame("AB  ", "red", True), frame("AB  ", "red", False)]}})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("seek impurity", p.stdout)


class Wire(Base):
    def test_fallback_request_and_response_without_done(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([{"fallback": True, "cells": [row("  AB")]}])}
        p = self.run_runner(files, {"by_key": {"frame:fallback": frame("  AB", done=None)}})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        req = self.requests()[0]
        self.assertIs(req["fallback"], True)
        self.assertNotIn("time_ns", req)
        self.assertEqual((req["width"], req["height"]), (4, 1))

    def test_fallback_response_with_done_is_transport_failure(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([{"fallback": True, "cells": [row("  AB")]}])}
        p = self.run_runner(files, {"by_key": {"frame:fallback": frame("  AB", done=True)}})
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_missing_done_on_normal_frame_is_transport_failure(self):
        p = self.run_runner(GOOD, {"by_key": {"frame:0": frame("    ", done=None)}})
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_nanosecond_exact_times_sent(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([ofr("0.999999999", "AB  ", "red"), ofr("1", "AB  ", "red"), ofr("1.000000001", "AB  ", "red")], "repeat")}
        p = self.run_runner(files, {"default": frame("AB  ", "red", False)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        times = [r["time_ns"] for r in self.requests()]
        self.assertEqual(times, [999999999, 1000000000, 1000000001])
        self.assertTrue(all(type(t) is int for t in times))

    def test_legacy_request_size_is_200x60(self):
        self.run_runner({"l.mdgl": SRC, "l.expect": "@0.5\n\n"}, {"default": frame("    ", done=False)})
        r = self.requests()[0]
        self.assertEqual((r["width"], r["height"], r["time_ns"]), (200, 60, 500000000))

    def test_clamp_response_smaller_than_request(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([ofr("0", "AB  ", "red", True)], "static").replace('"cols": 4', '"cols": 20')}
        p = self.run_runner(files, {"default": frame("AB  ", "red", True)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.requests()[0]["width"], 20)

    def test_response_larger_than_request_is_transport_failure(self):
        p = self.run_runner(GOOD, {"default": frame("AB    ", "red", True)})
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


class Transport(Base):
    def exit2(self, script, *extra, files=GOOD):
        p = self.run_runner(files, script, *extra)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("transport failure", p.stderr)
        return p

    def test_malformed_json_line(self):
        self.exit2({"default": {"_raw": "{not json"}})

    def test_id_mismatch(self):
        self.exit2({"default": {**frame("    ", done=False), "_id": "zzz"}})

    def test_hang_times_out_within_bound(self):
        self.exit2({"default": {"_hang": True}}, "--timeout", "1")
        self.assertLess(self.elapsed, 20)

    def test_bad_request_on_valid_request(self):
        p = self.exit2({"default": {"ok": False, "error": {"code": "bad_request", "message": "nope"}}})
        self.assertIn("bad_request", p.stderr)

    def test_unsupported_version_and_internal(self):
        for code in ("unsupported_version", "internal"):
            self.exit2({"default": {"ok": False, "error": {"code": code, "message": "x"}}})

    def test_adapter_exits_early(self):
        self.exit2({"default": {"_exit": True}})

    def test_adapter_exit_after_first(self):
        self.exit2({"by_key": GOOD_KEYS["by_key"], "exit_after": 1})

    def test_adapter_cannot_start(self):
        for n, c in GOOD.items():
            (self.suite / n).write_text(c, encoding="utf-8")
        p = subprocess.run([sys.executable, "-I", str(RUNNER), "--adapter", "/nonexistent/adapter-xyz", "--suite", str(self.suite)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 2)

    def test_unterminated_final_response(self):
        p = self.exit2({"by_key": GOOD_KEYS["by_key"], "unterminated_at": 2})
        self.assertIn("LF-terminated", p.stderr)
        self.assertLess(self.elapsed, 20)

    def test_unterminated_first_response(self):
        self.exit2({"by_key": GOOD_KEYS["by_key"], "unterminated_at": 1})

    def test_nonzero_exit_after_eof(self):
        p = self.exit2({"by_key": GOOD_KEYS["by_key"], "exit_code_at_eof": 4})
        self.assertIn("status 4", p.stderr)

    def test_adapter_ignores_eof(self):
        p = self.exit2({"by_key": GOOD_KEYS["by_key"], "hang_at_eof": True}, "--shutdown-timeout", "1")
        self.assertIn("did not exit", p.stderr)
        self.assertLess(self.elapsed, 20)

    def test_extra_response_line_mid_run(self):
        self.exit2({"by_key": GOOD_KEYS["by_key"], "extra_after": 1})

    def test_extra_line_after_last_response(self):
        self.exit2({"by_key": GOOD_KEYS["by_key"], "extra_after": 2})
        p = self.exit2({"by_key": GOOD_KEYS["by_key"], "extra_at_eof": True})
        self.assertIn("unsolicited", p.stderr)

    def test_clean_shutdown_passes(self):
        p = self.run_runner(GOOD, {**GOOD_KEYS, "exit_code_at_eof": 0})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_schema_violations(self):
        bad_cell = frame("    ", done=False)
        bad_cell["cells"][0][0]["r"] = "ab"
        self.exit2({"default": bad_cell})
        extra = frame("    ", done=False, bogus=1)
        self.exit2({"default": extra})
        self.exit2({"default": {**frame("    ", done=False), "v": 2}})


class Malformed(Base):
    def exit2(self, files):
        p = self.run_runner(files, {"default": frame("    ", done=False)})
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("malformed fixture", p.stderr)

    def test_invalid_json(self):
        self.exit2({"x.mdgl": SRC, "x.obs.json": "{oops"})

    def test_missing_or_empty_derivation(self):
        o = json.loads(obs([ofr("0", "    ")]))
        del o["derivation"]
        self.exit2({"x.mdgl": SRC, "x.obs.json": json.dumps(o)})
        o["derivation"] = "  "
        self.exit2({"x.mdgl": SRC, "x.obs.json": json.dumps(o)})

    def test_unknown_class(self):
        self.exit2({"x.mdgl": SRC, "x.obs.json": obs([ofr("0", "    ")], "bogus")})

    def test_bad_time_string(self):
        for t in ("1e9", "-1", "-0", "2s", "inf", "abc", ""):
            self.exit2({"x.mdgl": SRC, "x.obs.json": obs([ofr(t, "    ")])})

    def test_missing_source_and_bare_mdgl(self):
        self.exit2({"x.obs.json": obs([ofr("0", "    ")])})
        self.exit2({"bare.mdgl": SRC})

    def test_cells_missing_fg_in_non_cube(self):
        self.exit2({"x.mdgl": SRC, "x.obs.json": obs([{"time": "0", "cells": [[{"r": "A"}]], "done": False}])})

    def test_fallback_frame_with_done(self):
        self.exit2({"x.mdgl": SRC, "x.obs.json": obs([{"fallback": True, "cells": [row("    ")], "done": True}])})

    def test_normal_frame_without_done_is_malformed_even_for_cube(self):
        for cls in ("cube", "timed", "static"):
            p = self.run_runner({"x.mdgl": SRC, "x.obs.json": obs([{"time": "0", "cells": [[{"r": "A"}]] if cls == "cube" else [row("    ")]}], cls)}, {"default": frame("    ", done=False)})
            self.assertEqual(p.returncode, 2, (cls, p.stdout + p.stderr))
            self.assertIn("malformed fixture", p.stderr)
            self.assertIn("x.obs.json", p.stderr)
            self.assertIn("frame 0", p.stderr)

    def test_cube_fallback_with_done_and_done_not_bool(self):
        self.exit2({"x.mdgl": SRC, "x.obs.json": obs([{"fallback": True, "cells": [[{"r": "A"}]], "done": False}], "cube")})
        self.exit2({"x.mdgl": SRC, "x.obs.json": obs([{"time": "0", "cells": [[{"r": "A"}]], "done": "yes"}], "cube")})

    def test_bad_err_file(self):
        self.exit2({"e.mdgl": SRC, "e.err": "garbage"})

    def test_bad_expect_marker_and_missing_rows(self):
        self.exit2({"e.mdgl": SRC, "e.expect": "oops\n"})
        self.exit2({"e.mdgl": SRC, "e.expect": "@1\n"})  # height 1, row missing


class Layout(Base):
    def test_observable_subdir_and_root_both_load(self):
        o = obs([ofr("0", "    ", done=False)], "static")
        files = {"observable/x.mdgl": SRC, "observable/x.obs.json": o, "y.mdgl": SRC, "y.obs.json": o.replace("x.mdgl", "y.mdgl")}
        (self.suite / "observable").mkdir()
        p = self.run_runner(files, {"default": frame("    ", done=False)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(len(self.requests()), 2)

    def test_observable_mdgl_is_not_legacy_but_root_bare_is_malformed(self):
        (self.suite / "observable").mkdir()
        p = self.run_runner({"observable/z.mdgl": SRC}, {})
        self.assertEqual(p.returncode, 2)  # no obs.json and no zero-fixture pass
        p = self.run_runner({"bare.mdgl": SRC}, {})
        self.assertEqual(p.returncode, 2)


class Selection(Base):
    FILES = {"x.mdgl": SRC, "x.obs.json": obs([ofr("0", "    ")], "static"), "t.mdgl": SRC, "t.obs.json": obs([ofr("0", "    ")], "timed").replace("x.mdgl", "t.mdgl")}

    def test_class_filter(self):
        p = self.run_runner(self.FILES, {"default": frame("    ", done=False)}, "--class", "static")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(len(self.requests()), 1)
        self.assertIn("PASS static x", p.stdout)
        self.assertNotIn("PASS timed", p.stdout)
        self.assertNotIn("class timed: no fixtures", p.stdout)

    def test_zero_fixture_classes_reported(self):
        p = self.run_runner(self.FILES, {"default": frame("    ", done=False)})
        for c in ("diagnostic", "repeat", "cube"):
            self.assertIn(f"class {c}: no fixtures", p.stdout)
        self.assertNotIn("class static: no fixtures", p.stdout)
        r = json.loads(self.run_runner({}, {"default": frame("    ", done=False)}, "--json").stdout)
        self.assertEqual(sorted(r["no_fixtures"]), ["cube", "diagnostic", "repeat"])

    def test_selecting_nothing_is_exit_2(self):
        p = self.run_runner(self.FILES, {}, "--class", "cube")
        self.assertEqual(p.returncode, 2)

    def test_unknown_class_option(self):
        p = self.run_runner(self.FILES, {}, "--class", "nope")
        self.assertEqual(p.returncode, 2)

    def test_legacy_class_derivation(self):
        d = runner.derive_class
        self.assertEqual(d("scene width=1 height=1 fallback=end\n", True), "diagnostic")
        self.assertEqual(d('scene w\nactor c = cube(size=3) at (0,0)\n@0: c.rotate(x=1)\n', False), "cube")
        self.assertEqual(d("scene period=1 repeat=2\n@0: a.fade(in, dur=1)\n", False), "repeat")
        self.assertEqual(d("scene w\nactor a = text(\"A\") at (0,0)\n", False), "static")
        self.assertEqual(d("scene w\n@0.5: a.fade(in, dur=1)\n", False), "timed")


class Converter(unittest.TestCase):
    def test_accepts(self):
        for s, ns in [("0", 0), ("1", 10**9), ("1.0", 10**9), ("0.50", 500000000), ("1.", 10**9), (".5", 500000000), ("+2", 2 * 10**9),
                      ("1e-3", 10**6), ("1e0", 10**9), ("1E0", 10**9), ("0.999999999", 999999999), ("1.000000001", 1000000001), ("007", 7 * 10**9),
                      ("0.0000000015", 2), ("0.0000000014", 1), ("1.2345678904", 1234567890), ("1.2345678905", 1234567891),
                      ("0.1234567891", 123456789), ("0.0000000001", 0), ("9007199.254740991", 9007199254740991), ("9.007199254740991e6", 9007199254740991)]:
            self.assertEqual(runner.seconds_to_ns(s), ns, s)

    def test_rejects(self):
        for s in ("-0", "-0.0", "-0.0000000001", "-1", "-1e0", "2s", "0.5s", "inf", "Infinity", "nan", "--1", "+-1", "", ".", "s", "e3", "1e", "1 ", " 1",
                  "1_0", "0x10", "1.2.3", "٣", "9007199.254740992", "1e7", "1e999999999", "1ss"):
            with self.assertRaises(ValueError, msg=s):
                runner.seconds_to_ns(s)
        with self.assertRaises(ValueError):
            runner.seconds_to_ns(5)

    def test_long_decimal_half_nanosecond_neighbors(self):
        """Exact conversion independent of the default 28-digit context (review blocker 1)."""
        nines, zeros = "9" * 60, "0" * 60
        cases = [("0.0000000015", 2), ("0." + "0" * 8 + "1" + "4" + nines, 1), ("0.00000000149999999999999999999999999999999999999999", 1),
                 ("0.00000000150000000000000000000000000000000000000001", 2), ("0.000000001" + "5" + zeros, 2),
                 ("1.5e-9", 2), ("1e-9", 1), ("0.4999999995", 500000000), ("0.4999999994" + nines, 499999999),
                 ("9007199254.740991", None), ("9007199.254740991", 9007199254740991),
                 ("0.0000000014" + "9" * 3000, 1), ("0.0000000015" + "0" * 3000 + "1", 2), ("0.0000000015" + "0" * 3000, 2),
                 ("0.0000000004" + "9" * 3000, 0), ("0.0000000005" + "0" * 3000 + "1", 1)]
        for s, ns in cases:
            if ns is None:
                with self.assertRaises(ValueError, msg=s):
                    runner.seconds_to_ns(s)
            else:
                self.assertEqual(runner.seconds_to_ns(s), ns, s[:60])

    def test_cap_boundary(self):
        self.assertEqual(runner.seconds_to_ns("9007199.254740991"), 2**53 - 1)
        self.assertEqual(runner.seconds_to_ns("9007199.2547409905"), 2**53 - 1)  # tie rounds up to the cap, allowed
        for s in ("9007199.2547409915", "9007199.254740992", "9007199.254740991500" + "0" * 50 + "1"):
            with self.assertRaises(ValueError, msg=s):
                runner.seconds_to_ns(s)

    def test_negatives_rejected_before_rounding(self):
        for s in ("-0", "-1e-30", "-0.0000000004", "-0." + "0" * 40 + "1", "-0e0"):
            with self.assertRaises(ValueError, msg=s):
                runner.seconds_to_ns(s)

    def test_default_context_is_irrelevant(self):
        old = decimal.getcontext().prec
        try:
            for prec in (1, 5, 28):
                decimal.getcontext().prec = prec
                self.assertEqual(runner.seconds_to_ns("0.00000000149999999999999999999999999999999999999999"), 1)
                self.assertEqual(runner.seconds_to_ns("0.00000000150000000000000000000000000000000000000001"), 2)
        finally:
            decimal.getcontext().prec = old

    def test_randomized_against_fraction(self):
        rnd = random.Random(20261010)
        for _ in range(4000):
            ip = rnd.choice(["0", "0", str(rnd.randrange(0, 10**7)), ""])
            fl = rnd.choice([0, 3, 9, 10, 11, 30, 80])
            fd = "".join(rnd.choice("0123456789") for _ in range(fl))
            if rnd.random() < 0.5 and fl >= 10:  # force a half-ns neighbourhood
                fd = fd[:9] + rnd.choice(["4" + "9" * (fl - 10), "5" + "0" * (fl - 10), "5" + "0" * (fl - 11) + "1", "4" + "9" * (fl - 11) + "8"][: 4]) if fl >= 11 else fd
            if not ip and not fd:
                continue
            txt = ip + ("." + fd if fd or rnd.random() < 0.3 else "")
            if rnd.random() < 0.2:
                txt += "e" + str(rnd.randrange(-12, 3))
            if not runner.TIME_RE.fullmatch(txt):
                continue
            exact = fractions.Fraction(decimal.Decimal(txt)) * 10**9
            want = int(exact + fractions.Fraction(1, 2))  # floor(x + 1/2) == half away from zero for x >= 0
            if want > runner.MAX_NS:
                with self.assertRaises(ValueError, msg=txt):
                    runner.seconds_to_ns(txt)
            else:
                self.assertEqual(runner.seconds_to_ns(txt), want, txt)

    def test_canonical_short_form_output(self):
        for ns, s in [(0, "0"), (10**9, "1"), (500000000, "0.5"), (999999999, "0.999999999"), (1000000001, "1.000000001")]:
            self.assertEqual(runner.ns_to_seconds(ns), s)

    def test_legacy_headers_with_trailing_zeros_load(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.mdgl").write_text(SRC)
            (Path(d) / "a.expect").write_text("@1.0\nAB\n@0.50\n\n")
            f = runner.load_fixtures(d)[0]
            self.assertEqual([ns for ns, _ in f["frames"]], [10**9, 500000000])

    def test_forms_in_expect_and_obs_load_and_negative_is_fixture_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.mdgl").write_text(SRC)
            (Path(d) / "a.expect").write_text("@+2\nAB\n@1e-3\n\n@.5\n\n")
            self.assertEqual([ns for ns, _ in runner.load_fixtures(d)[0]["frames"]], [2 * 10**9, 10**6, 500000000])
        for h in ("-0", "-0.0000000001", "2s", "nan"):
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "a.mdgl").write_text(SRC)
                (Path(d) / "a.expect").write_text(f"@{h}\n\n")
                with self.assertRaises(runner.Malformed):
                    runner.load_fixtures(d)


class Verdict(Base):
    """Normative vs non-normative reporting and exit codes."""
    def two(self, normative_a, normative_b):
        a = json.loads(obs([ofr("0", "    ", done=False)], "static"))
        b = json.loads(obs([ofr("0", "    ", done=False)], "timed"))
        a["normative"], b["normative"] = normative_a, normative_b
        return {"a.mdgl": SRC, "a.obs.json": json.dumps(a), "b.mdgl": SRC, "b.obs.json": json.dumps(b).replace("x.mdgl", "b.mdgl")}

    def files(self, normative):
        f = self.two(True, normative)
        return {k: v.replace("x.mdgl", "a.mdgl") if k.startswith("a.") else v.replace("x.mdgl", "b.mdgl") for k, v in f.items()}

    def test_all_pass_verdict_and_counts(self):
        p = self.run_runner(self.files(False), {"default": frame("    ", done=False)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("ALL NORMATIVE FIXTURES PASSED", p.stdout)
        self.assertIn("normative: 1 passed, 0 failed", p.stdout)
        self.assertIn("non-normative: 1 assumption-based pass (not certification), 0 failed", p.stdout)
        r = json.loads(self.run_runner(self.files(False), {"default": frame("    ", done=False)}, "--json").stdout)
        self.assertEqual(r["counts"], {"normative": {"passed": 1, "failed": 0}, "nonnormative": {"passed": 1, "failed": 0}})
        self.assertEqual([x["normative"] for x in r["results"]], [True, False])

    def test_no_nonnormative_fixtures(self):
        p = self.run_runner(GOOD, GOOD_KEYS)
        self.assertIn("non-normative: no fixtures", p.stdout)
        self.assertIn("ALL NORMATIVE FIXTURES PASSED", p.stdout)

    def wrong(self, which):
        """Break b (timed) via fg/bg/done; a (static) always right. Returns (normative_b -> process)."""
        out = {}
        for norm in (True, False):
            bad = frame("    ", done=(which == "done"))
            if which == "fg":
                bad["cells"][0][0]["fg"] = "red"
            if which == "bg":
                bad["cells"][0][0]["bg"] = "blue"
            good = frame("    ", done=False)
            out[norm] = self.run_runner(self.files(norm), {"by_key": {"frame:0": [good, bad]}}, "--json")
        return out

    def test_wrong_fg_bg_done_normative_vs_not(self):
        for which in ("fg", "bg", "done"):
            for norm, p in self.wrong(which).items():
                self.assertEqual(p.returncode, 1, (which, norm, p.stdout, p.stderr))
                r = json.loads(p.stdout)
                self.assertEqual(r["counts"]["normative" if norm else "nonnormative"]["failed"], 1)
                self.assertEqual(r["counts"]["nonnormative" if norm else "normative"]["failed"], 0)
                self.assertEqual(r["verdict"] == "NORMATIVE FIXTURES FAILED", norm, r["verdict"])

    def test_text_verdict_lines(self):
        for norm in (True, False):
            bad = frame("    ", done=False)
            bad["cells"][0][0]["fg"] = "red"
            p = self.run_runner(self.files(norm), {"by_key": {"frame:0": [frame("    ", done=False), bad]}})
            self.assertEqual(p.returncode, 1)
            self.assertIn("FAIL timed b", p.stdout)
            self.assertIn("NORMATIVE FIXTURES FAILED" if norm else "non-normative: 0 assumption-based pass (not certification), 1 failed", p.stdout)
            self.assertEqual("ALL NORMATIVE FIXTURES PASSED" in p.stdout, not norm)

    def test_class_filter_hides_unrun_normative_class(self):
        p = self.run_runner(self.files(False), {"default": frame("    ", done=False)}, "--class", "static")
        self.assertEqual(p.returncode, 0, p.stdout)
        p = self.run_runner(self.files(True), {"default": frame("    ", done=False)}, "--class", "static")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("NOT CERTIFIED: normative classes not run: timed", p.stdout)
        self.assertNotIn("ALL NORMATIVE FIXTURES PASSED", p.stdout)

    def test_no_normative_fixtures_never_certifies(self):
        nn = {k: v for k, v in self.two(False, False).items()}
        nn = {k: v.replace("x.mdgl", k.split(".")[0] + ".mdgl") for k, v in nn.items()}
        for extra in ((), ("--class", "static")):
            p = self.run_runner(nn, {"default": frame("    ", done=False)}, "--json", *extra)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            r = json.loads(p.stdout)
            self.assertEqual(r["verdict"], "NOT CERTIFIED: no normative fixtures ran")
            self.assertEqual(r["counts"]["normative"], {"passed": 0, "failed": 0})
            t = self.run_runner(nn, {"default": frame("    ", done=False)}, *extra)
            self.assertIn("NOT CERTIFIED: no normative fixtures ran", t.stdout)
            self.assertNotIn("ALL NORMATIVE FIXTURES PASSED", t.stdout)
            self.assertIn("assumption-based pass (not certification)", t.stdout)

    def test_class_selecting_only_nonnormative_fixtures(self):
        p = self.run_runner(self.files(False), {"default": frame("    ", done=False)}, "--class", "timed")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("NOT CERTIFIED: no normative fixtures ran", p.stdout)
        self.assertNotIn("ALL NORMATIVE FIXTURES PASSED", p.stdout)

    def test_legacy_reported_glyph_only(self):
        p = self.run_runner({"leg.mdgl": SRC, "leg.expect": "@2\nAB\n"}, {"default": frame("AB  ", "red", True)}, "--json")
        r = json.loads(p.stdout)
        self.assertEqual(r["results"][0]["basis"], "glyph-only")
        self.assertEqual(r["verdict"], "ALL NORMATIVE FIXTURES PASSED")

    def test_legacy_is_normative_and_byte_column_mismatch_fails(self):
        src = 'scene width=8 height=1 fallback=end\nactor a = text("é") $\n'
        files = {"m.mdgl": src, "m.err": '2:22: unexpected character "$"\n'}
        p = self.run_runner(files, {"by_key": {"check:" + src: {"ok": True, "diagnostics": [{"line": 2, "col": 21, "message": 'unexpected character "$"'}]}}}, "--json")
        self.assertEqual(p.returncode, 1, p.stdout)
        r = json.loads(p.stdout)
        self.assertEqual(r["counts"]["normative"], {"passed": 0, "failed": 1})
        self.assertIn("col", r["results"][0]["detail"])


class Requests(Base):
    def test_time_ns_plain_integers_in_request_text(self):
        files = {"x.mdgl": SRC, "x.obs.json": obs([ofr("0.999999999", "AB  ", "red"), ofr("1", "AB  ", "red"), ofr("1e-3", "AB  ", "red"), ofr("+2.50", "AB  ", "red")], "repeat")}
        p = self.run_runner(files, {"default": frame("AB  ", "red", False)})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        lines = (self.tmp / "log.jsonl").read_text(encoding="utf-8").splitlines()
        want = [999999999, 1000000000, 1000000, 2500000000]
        self.assertEqual([json.loads(l)["time_ns"] for l in lines], want)
        self.assertTrue(all(type(json.loads(l)["time_ns"]) is int for l in lines))

    def test_fallback_branch_bound_to_request(self):
        fb = {"x.mdgl": SRC, "x.obs.json": obs([{"fallback": True, "cells": [row("  AB")]}])}
        self.assertEqual(self.run_runner(fb, {"default": frame("  AB", done=False)}).returncode, 2)
        self.assertEqual(self.run_runner(GOOD, {"default": frame("    ", done=None)}).returncode, 2)

    def test_hang_and_id_mismatch_exit_2(self):
        self.assertEqual(self.run_runner(GOOD, {"default": {"_hang": True}}, "--timeout", "1").returncode, 2)
        self.assertEqual(self.run_runner(GOOD, {"default": {**frame("    ", done=False), "_id": "q"}}).returncode, 2)

    def test_zero_fixtures_selected_exit_2(self):
        self.assertEqual(self.run_runner(GOOD, {}, "--class", "cube").returncode, 2)
        self.assertEqual(self.run_runner({}, {}).returncode, 2)


class MockStdin(unittest.TestCase):
    """The mock must read stdin as a conforming adapter does (PROTOCOL section 1)."""
    def talk(self, data):
        with tempfile.TemporaryDirectory() as d:
            sc = Path(d) / "s.json"
            sc.write_text(json.dumps({"default": frame("AB", done=True)}))
            p = subprocess.run([sys.executable, "-I", str(MOCK), str(sc)], input=data, capture_output=True, timeout=30)
        return p.returncode, [json.loads(l) for l in p.stdout.decode().split("\n") if l]

    def test_final_line_without_newline_is_answered_and_exit_0(self):
        req = json.dumps({"v": 1, "id": "a", "op": "frame", "source": "", "time_ns": 0, "width": 2, "height": 1})
        rc, out = self.talk((req + "\n" + req.replace('"a"', '"b"')).encode())
        self.assertEqual(rc, 0)
        self.assertEqual([o["id"] for o in out], ["a", "b"])
        self.assertTrue(all(o["ok"] and o["done"] is True for o in out))

    def test_blank_lines_are_bad_request_id_null_and_trailing_segment_silent(self):
        req = json.dumps({"v": 1, "id": "a", "op": "frame", "source": "", "time_ns": 0, "width": 2, "height": 1})
        rc, out = self.talk(("\n   \n" + req + "\n").encode())
        self.assertEqual(rc, 0)
        self.assertEqual([(o["id"], o["ok"]) for o in out], [(None, False), (None, False), ("a", True)])
        self.assertEqual(out[0]["error"]["code"], "bad_request")
        self.assertEqual(self.talk(b"")[1], [])


class Corpus(unittest.TestCase):
    """Self-check of the shipped conformance/ directory (no adapter involved)."""

    def test_loads_and_obs_files_are_sound(self):
        fixtures = runner.load_fixtures(CONF)  # raises Malformed on any problem
        obs_files = sorted(OBS.glob("*.obs.json"))
        self.assertGreaterEqual(len(obs_files), 12)
        for p in obs_files:  # every non-fallback frame of every observable fixture carries an explicit boolean done
            for i, fr in enumerate(json.loads(p.read_text(encoding="utf-8")).get("frames", [])):
                self.assertEqual("done" in fr, fr.get("fallback") is not True, (p.name, i))
        for p in obs_files:
            o = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(o["derivation"].strip(), p.name)
            self.assertTrue((OBS / o["source_file"]).is_file(), p.name)
            self.assertIn(o["class"], runner.CLASSES, p.name)
            src = (OBS / o["source_file"]).read_text(encoding="utf-8")
            self.assertLessEqual(max(len(l) for l in src.splitlines()) if o["class"] != "diagnostic" else 0, 80)
            m = [int(x) for x in __import__("re").search(r"width=(\d+) height=(\d+)", src).groups()]
            self.assertTrue(m[0] <= 200 and m[1] <= 60, p.name)  # SPEC stage limit; cube fixtures are 14x10
        names = {f["name"] for f in fixtures}
        self.assertTrue({"fade", "cube_x_30", "stage_limit", "obs_blink"} <= names)
        by = {f["name"]: f["class"] for f in fixtures}
        self.assertEqual((by["fade"], by["cube_x_30"], by["stage_limit"], by["repeat"], by["static"]), ("timed", "cube", "diagnostic", "repeat", "static"))

    def test_real_corpus_counts(self):
        fixtures = runner.load_fixtures(CONF)
        legacy = [f for f in fixtures if f["legacy"]]
        self.assertEqual((len(legacy), len(fixtures) - len(legacy), len(fixtures)), (46, 40, 86), "legacy/observable/total counted")
        norm = [f for f in fixtures if f["normative"]]
        self.assertEqual((len(norm), len(fixtures) - len(norm)), (64, 22), "normative/non-normative counted")
        circ = [f for f in fixtures if f["name"].startswith("obs_circle_")]
        self.assertEqual(sorted((f["name"], f["normative"]) for f in circ), [("obs_circle_r0_reject", False), ("obs_circle_r100_accept", True), ("obs_circle_r101_reject", False)], "matched %d circle fixtures" % len(circ))
        self.assertEqual(len([f for f in fixtures if f["class"] == "cube" and not f["legacy"] and f["normative"]]), 3)
        self.assertEqual(len([f for f in fixtures if f["class"] == "cube" and not f["legacy"] and not f["normative"]]), 3)
        self.assertEqual(len([f for f in fixtures if f["name"].startswith("obs_ref_") and not f["normative"]]), 3)
        self.assertEqual(len(list(CONF.glob("obs_*"))), 0)
        for m in CONF.glob("*.mdgl"):
            self.assertTrue(m.with_suffix(".err").exists() or m.with_suffix(".expect").exists(), m.name)

    def test_schema_validation_if_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not importable")
        schema = json.loads((CONF / "protocol.schema.json").read_text(encoding="utf-8"))
        for p in sorted(OBS.glob("*.obs.json")):
            o = json.loads(p.read_text(encoding="utf-8"))
            for fr in o.get("frames", []):
                if o["class"] == "cube":
                    continue
                for r in fr["cells"]:
                    for c in r:
                        jsonschema.validate(c, {"$defs": schema["$defs"], "$ref": "#/$defs/cell"})
            if "diagnostic" in o:
                jsonschema.validate(o["diagnostic"], {"$defs": schema["$defs"], "$ref": "#/$defs/diagnostic"})


if __name__ == "__main__":
    unittest.main()

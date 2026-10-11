"""Tests for example-media.py (stdlib unittest, fast). Run: python3 -m unittest scripts/test_example_media.py -v"""
import importlib.util, io, os, shlex, shutil, sys, tempfile, time, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = HERE / "example-media.py"
spec = importlib.util.spec_from_file_location("example_media", SCRIPT)
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

TINY = 'scene width=12 height=2 period=1s repeat=1 fallback=end\nactor a = text("hello ⠀⣿") at (0, 0) color=red\n'
INF = 'scene width=12 height=2 period=1s repeat=infinite fallback=end\nactor a = text("loop") at (0, 0) color=cyan\n'


class Sampling(unittest.TestCase):
    def test_times(self):
        for fps in (30, 24, 60):
            ts = [em.frame_time_ns(k, fps) for k in range(fps * 3 + 1)]
            self.assertEqual(ts[0], 0)
            self.assertTrue(all(type(t) is int for t in ts))
            self.assertTrue(all(b > a for a, b in zip(ts, ts[1:])))
            self.assertEqual(ts[fps], 10**9)
        self.assertEqual(em.frame_time_ns(1, 30), 33333333)
        self.assertEqual(em.frame_time_ns(2, 30), 66666667)


class Colour(unittest.TestCase):
    def test_sgr(self):
        self.assertEqual(em.sgr("red", ""), "\x1b[38;2;255;85;85m\x1b[49m")
        self.assertEqual(em.sgr("normal", ""), "\x1b[38;2;229;229;229m\x1b[49m")
        self.assertEqual(em.sgr("accent", ""), em.sgr("cyan", ""))
        self.assertEqual(em.sgr("#0a1B2c", "blue"), "\x1b[38;2;10;27;44m\x1b[48;2;98;114;255m")
        for n in ("normal black red green yellow blue magenta cyan white accent".split()):
            self.assertIn(n, em.PALETTE)

    def test_row(self):
        cells = [{"r": "a", "fg": "red", "bg": ""}, {"r": "b", "fg": "red", "bg": ""}, {"r": "⣿", "fg": "#112233", "bg": ""}]
        self.assertEqual(em.row_ansi(cells), "\x1b[38;2;255;85;85m\x1b[49mab\x1b[38;2;17;34;51m\x1b[49m⣿\x1b[0m")
        self.assertEqual(em.row_plain(cells), "ab⣿")


class Header(unittest.TestCase):
    def test_real_scenes(self):
        want = {"neon-cube": (90, 28, 12, "infinite"),
                "kubernetes": (96, 34, 18, None), "llm": (96, 30, 43, "infinite")}
        for name, (w, h, p, r) in want.items():
            hd = em.parse_header((REPO / "examples" / f"{name}.mdgl").read_text(encoding="utf-8"))
            self.assertEqual((hd["width"], hd["height"], hd["period_ns"], hd["repeat"]), (w, h, p * 10**9, r), name)
            self.assertGreaterEqual(hd["fps"], 1)
            self.assertEqual(em.limit_ns(hd), p * 10**9)
        self.assertEqual(em.parse_header("scene width=3 height=1\n")["fps"], 30)


class FakeAdapter:
    def __init__(self):
        self.reqs = []
    def call(self, op, source, **kw):
        self.reqs.append((op, kw))
        return {}, {"ok": True, "width": 2, "height": 2, "cells": [[{"r": "x", "fg": "red", "bg": ""}, {"r": "⠀", "fg": "normal", "bg": ""}]] * 2}
    def close(self): pass
    def kill(self): pass


class Plain(unittest.TestCase):
    def test_plain_fallback(self):
        d = tempfile.mkdtemp()
        try:
            p = Path(d) / "t.mdgl"
            p.write_text(TINY, encoding="utf-8")
            ad = FakeAdapter()
            buf = io.StringIO()
            args = em.build_parser().parse_args(["play", str(p)])
            rc = em.cmd_play(args, ad_factory=lambda: ad, stdout=buf, is_tty=False)
            self.assertEqual(rc, 0)
            self.assertNotIn("\x1b", buf.getvalue())
            self.assertIn("x⠀", buf.getvalue())
            self.assertTrue(ad.reqs and all(kw.get("fallback") is True for _, kw in ad.reqs))
        finally:
            shutil.rmtree(d)

    def test_missing_scene_exit(self):
        args = em.build_parser().parse_args(["play", "/nonexistent/x.mdgl"])
        self.assertEqual(em.cmd_play(args, ad_factory=FakeAdapter, stdout=io.StringIO(), is_tty=False), 1)


class FiniteFake:
    """Fake adapter: records frame requests into a shared event list; done once time_ns >= end_ns."""
    def __init__(self, events, end_ns):
        self.events, self.end_ns = events, end_ns
    def call(self, op, source, **kw):
        self.events.append(("req", kw["time_ns"]))
        row = [{"r": "x", "fg": "red", "bg": ""}]
        return {}, {"ok": True, "width": 1, "height": 1, "cells": [row], "done": kw["time_ns"] >= self.end_ns}
    def close(self): pass
    def kill(self): pass


class Finite(unittest.TestCase):
    def play(self, header, end_ns):
        events, now = [], [0.0]
        def sleep(s):
            if s >= em.HOLD_S:
                events.append(("hold",))
            now[0] += s
        src = header + 'actor a = text("x") at (0, 0) color=red\n'
        em.play_scene(FiniteFake(events, end_ns), src, em.Out(io.StringIO()), "t", 1, False, None, clock=lambda: now[0], sleep=sleep)
        reqs = [e[1] for e in events if e[0] == "req"]
        return events, reqs

    def check_end(self, events, reqs, end):
        self.assertEqual(reqs.count(end), 1, reqs)
        self.assertEqual(reqs[-1], end)
        self.assertTrue(all(type(t) is int for t in reqs))
        self.assertEqual(events[-1], ("hold",))
        self.assertEqual(events.index(("req", end)), len(events) - 2)  # last request immediately precedes the hold

    def test_finite_extra_frame_exact_end_once_before_hold(self):
        events, reqs = self.play("scene width=4 height=1 fps=10 period=2s\n", 2 * 10**9)
        self.check_end(events, reqs, 2_000_000_000)
        self.assertEqual(reqs[:3], [0, 100_000_000, 200_000_000])
        self.assertEqual(reqs[-2], 1_900_000_000)

    def test_finite_repeat2_extra_frame_at_period_times_repeat(self):
        events, reqs = self.play("scene width=4 height=1 fps=10 period=2s repeat=2\n", 4 * 10**9)
        self.check_end(events, reqs, 4_000_000_000)

    def test_infinite_never_requests_wrapped_end(self):
        events, reqs = self.play("scene width=4 height=1 fps=10 period=2s repeat=infinite\n", 10**18)
        self.assertLess(max(reqs), 2 * 10**9)
        self.assertEqual(reqs[-1], 1_900_000_000)
        self.assertEqual(events[-1], ("hold",))


class InterruptStream(io.StringIO):
    """Raises KeyboardInterrupt right after a frame's sync-begin has been written."""
    def write(self, s):
        if em.SYNC_ON in s:  # interrupted mid-frame: sync-begin landed, its sync-end did not
            super().write(s.replace(em.SYNC_OFF, ""))
            raise KeyboardInterrupt
        return super().write(s)


class Cleanup(unittest.TestCase):
    def test_interrupt_mid_frame_emits_sync_off_before_reset_and_show(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = Path(d) / "t.mdgl"
        p.write_text(INF, encoding="utf-8")
        events, buf = [], InterruptStream()
        args = em.build_parser().parse_args(["play", str(p)])
        saved = {k: os.environ.pop(k, None) for k in ("NO_COLOR", "MDGL_REDUCED_MOTION")}
        try:
            with self.assertRaises(KeyboardInterrupt):
                em.cmd_play(args, ad_factory=lambda: FiniteFake(events, 10**18), stdout=buf, is_tty=True)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        out = buf.getvalue()
        self.assertEqual(out.count(em.SYNC_ON), 1)
        tail = out[out.rfind(em.SYNC_ON):]
        a = tail.find(em.SYNC_OFF)
        b, c = tail.find(em.RESET, a + 1), tail.find(em.SHOW, a + 1)
        self.assertTrue(0 <= a < b < c, (a, b, c))


@unittest.skipIf(sys.platform == "win32", "PTY tests need POSIX")
@unittest.skipUnless(shutil.which("go"), "go not available: PTY tests need the Go adapter")
class Pty(unittest.TestCase):
    def run_pty(self, scene, extra, sigint_after=None, timeout=60):
        import pty, select, signal
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = Path(d) / "s.mdgl"
        p.write_text(scene, encoding="utf-8")
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.pop("NO_COLOR", None); os.environ.pop("MDGL_REDUCED_MOTION", None)
            os.environ["LC_ALL"] = "C.UTF-8"
            os.execv(sys.executable, [sys.executable, str(SCRIPT), "play", str(p)] + extra)
        data, t0, sent, status = b"", time.monotonic(), False, None
        while time.monotonic() - t0 < timeout:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                try:
                    c = os.read(fd, 65536)
                except OSError:
                    c = b""
                if not c:
                    break
                data += c
            if sigint_after is not None and not sent and b"loop" in data and time.monotonic() - t0 > sigint_after:
                os.write(fd, b"\x03"); sent = True
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("timeout")
        _, st = os.waitpid(pid, 0)
        os.close(fd)
        return data.decode("utf-8", "replace"), os.waitstatus_to_exitcode(st)

    def check_restored(self, out):
        self.assertIn("\x1b[?25l", out)
        self.assertGreater(out.rfind("\x1b[?25h"), out.rfind("\x1b[?25l"))

    def test_finite(self):
        out, rc = self.run_pty(TINY, ["--loops", "1"])
        self.assertEqual(rc, 0, out[-300:])
        self.assertTrue("hello" in out or "⣿" in out)
        self.check_restored(out)

    def test_ctrl_c(self):
        out, rc = self.run_pty(INF, ["--forever"], sigint_after=0.5)
        self.assertEqual(rc, 130, out[-300:])
        self.check_restored(out)



# ---- verify / export engine (example_media_export.py), fake adapters only: no tools needed ----
_spec = importlib.util.spec_from_file_location("ex_t", HERE / "example_media_export.py")
ex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ex)

FIN = "scene width=3 height=2 fps=10 period=2s repeat=1 fallback=end\nactor a = text(\"x\") at (0, 0)\n"
INFS = "scene width=3 height=2 fps=10 period=2s repeat=infinite fallback=end\nactor a = text(\"x\") at (0, 0)\n"
CELL = {"r": "x", "fg": "red", "bg": ""}
BLANK = {"r": " ", "fg": "normal", "bg": ""}


class Fake:
    """check -> ok; frame -> fixed 3x2 grid. mutate(t, fallback, cells, done) -> (cells, done) injects a difference."""
    def __init__(self, log, end_ns=None, mutate=None):
        self.log, self.end_ns, self.mutate = log, end_ns, mutate
    def call(self, op, source, **kw):
        if op == "check":
            return {}, {"ok": True, "diagnostics": []}
        fb = kw.get("fallback") is True
        t = kw.get("time_ns")
        self.log.append(("fb",) if fb else ("t", t))
        cells, done = [[dict(CELL), dict(BLANK), dict(BLANK)] for _ in range(2)], (t is not None and self.end_ns is not None and t >= self.end_ns)
        if self.mutate:
            cells, done = self.mutate(t, fb, cells, done)
        r = {"ok": True, "width": 3, "height": 2, "cells": cells}
        if not fb:
            r["done"] = done
        return dict(kw, op=op), r
    def close(self): pass
    def kill(self): pass


def five(mutate_for=None, mutate=None, end_ns=None):
    log = []
    ads = {n: Fake(log, end_ns, mutate if n == mutate_for else None) for n in ex.ADAPTERS}
    return ads, log


class Compare(unittest.TestCase):
    def mismatch(self, mutate, scene=INFS):
        ads, _ = five("c", mutate)
        with self.assertRaises(ex.Mismatch) as cm:
            ex.compare_scene("demo", scene, ads)
        return cm.exception.report

    def test_colour_only_mismatch_reports_exact_cell(self):
        def mut(t, fb, cells, done):
            if t == 300_000_000:
                cells[1][2] = dict(BLANK, fg="cyan")
            return cells, done
        r = self.mismatch(mut)
        self.assertEqual((r["scene"], r["time_ns"], r["frame_index"], r["row"], r["col"], r["field"], r["adapters"], r["fallback"]),
                         ("demo", 300_000_000, 3, 1, 2, "fg", ["go", "c"], False))
        self.assertEqual(r["detail"], {"go": {"r": " ", "fg": "normal", "bg": ""}, "c": {"r": " ", "fg": "cyan", "bg": ""}})
        self.assertEqual(r["full"]["c"]["done"], False)

    def test_done_only_mismatch(self):
        def mut(t, fb, cells, done):
            return cells, (not done) if t == 100_000_000 else done
        r = self.mismatch(mut)
        self.assertEqual((r["field"], r["time_ns"], r["frame_index"], r["row"], r["col"], r["adapters"]), ("done", 100_000_000, 1, None, None, ["go", "c"]))
        self.assertEqual(r["detail"], {"go": False, "c": True})

    def test_glyph_mismatch(self):
        def mut(t, fb, cells, done):
            if t == 0:
                cells[0][1] = dict(BLANK, r="⣿")
            return cells, done
        r = self.mismatch(mut)
        self.assertEqual((r["field"], r["time_ns"], r["row"], r["col"], r["adapters"]), ("r", 0, 0, 1, ["go", "c"]))
        self.assertEqual(r["detail"]["c"]["r"], "⣿")
        self.assertIn("scene=demo", str(ex.Mismatch(r)))

    def test_background_and_size_are_compared(self):
        def bg(t, fb, cells, done):
            cells[0][0] = dict(CELL, bg="blue") if t == 0 else cells[0][0]
            return cells, done
        self.assertEqual(self.mismatch(bg)["field"], "bg")

    def test_fallback_compared_separately(self):
        def mut(t, fb, cells, done):
            if fb:
                cells[0][0] = dict(CELL, r="y")
            return cells, done
        r = self.mismatch(mut)
        self.assertTrue(r["fallback"])
        self.assertIsNone(r["time_ns"])
        self.assertEqual((r["row"], r["col"], r["field"]), (0, 0, "r"))
        self.assertTrue(r["request"].get("fallback"))

    def test_fallback_requested_once_per_adapter_and_has_no_done(self):
        ads, log = five()
        s = ex.compare_scene("demo", FIN, ads, None)
        self.assertEqual(log.count(("fb",)), 5)
        self.assertEqual(len(s["fallback_sha256"]), 64)

    def test_finite_end_frame_requested_once(self):
        ads, log = five(end_ns=2 * 10**9)
        s = ex.compare_scene("demo", FIN, ads)
        ts = [e[1] for e in log if e[0] == "t"]
        self.assertEqual(ts.count(2_000_000_000), 5)  # once per adapter
        self.assertEqual(max(ts), 2_000_000_000)
        self.assertEqual(s["frames"], 21)  # k=0..19 plus the exact end frame
        self.assertTrue(s["end_frame"])
        self.assertEqual(s["end_time_ns"], 2_000_000_000)

    def test_infinite_never_wraps(self):
        ads, log = five()
        s = ex.compare_scene("demo", INFS, ads)
        ts = [e[1] for e in log if e[0] == "t"]
        self.assertEqual(max(ts), 1_900_000_000)
        self.assertEqual((s["frames"], s["end_frame"]), (20, False))

    def test_streams_frame_by_frame_across_adapters(self):
        ads, log = five()
        seen = []
        ex.compare_scene("demo", INFS, ads, sink=lambda i, t, r, e: seen.append((i, t, len(log))))
        self.assertEqual([x[0] for x in seen], list(range(20)))
        self.assertEqual([x[2] for x in seen][:3], [5, 10, 15])  # five requests per frame, compared before the next frame

    def test_done_presence_and_value_change_the_frame_hash(self):
        base = {"ok": True, "width": 1, "height": 1, "cells": [[dict(CELL)]]}
        h = lambda **kw: __import__("hashlib").sha256(ex.canon(dict(base, **kw))).hexdigest()
        self.assertEqual(len({h(), h(done=True), h(done=False)}), 3)  # absent / true / false are three different observables
        self.assertEqual(h(done=True), h(done=True))

    def test_non_ok_reference_response_is_a_structured_mismatch(self):
        class Refuse(Fake):
            def call(self, op, source, **kw):
                if op == "check":
                    return {}, {"ok": True, "diagnostics": []}
                return {"time_ns": kw.get("time_ns")}, {"ok": False, "error": {"code": "invalid_source", "message": "no", "diagnostics": [{"line": 1, "col": 1, "message": "no"}]}}
        ads, _ = five()
        ads["go"] = Refuse([])  # reference refuses, the others answer
        with self.assertRaises(ex.Mismatch) as cm:
            ex.compare_scene("demo", INFS, ads)
        r = cm.exception.report
        self.assertEqual((r["scene"], r["time_ns"], r["frame_index"], r["field"], r["adapters"], r["row"]), ("demo", 0, 0, "ok", ["go", "rust"], None))
        self.assertEqual(r["detail"]["go"], {"code": "invalid_source", "message": "no"})
        self.assertEqual(r["detail"]["rust"], "ok")
        self.assertIn("field=ok", str(cm.exception))

    def test_non_ok_non_reference_response_is_a_structured_mismatch(self):
        class Refuse(Fake):
            def call(self, op, source, **kw):
                if op == "check":
                    return {}, {"ok": True, "diagnostics": []}
                return {}, {"ok": False, "error": {"code": "invalid_source", "message": "late", "diagnostics": [{"line": 1, "col": 1, "message": "late"}]}}
        ads, _ = five()
        ads["python"] = Refuse([])
        with self.assertRaises(ex.Mismatch) as cm:
            ex.compare_scene("demo", INFS, ads)
        self.assertEqual((cm.exception.report["adapters"], cm.exception.report["detail"]["python"]["message"]), (["go", "python"], "late"))

    def test_sequence_hash_is_deterministic(self):
        a = ex.compare_scene("demo", INFS, five()[0])
        b = ex.compare_scene("demo", INFS, five()[0])
        self.assertEqual(a["sequence_sha256"], b["sequence_sha256"])
        self.assertEqual(len(a["frame_sha256"]), 20)


def args_for(*argv):
    return em.build_parser().parse_args(list(argv))


class Run(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.scene = Path(self.d) / "t.mdgl"
        self.scene.write_text(FIN, encoding="utf-8")
        self.old = (ex.need_tools, ex.tool_versions)
        ex.need_tools, ex.tool_versions = (lambda *a, **k: None), (lambda *a, **k: {"go": "go-test"})
        self.addCleanup(lambda: setattr(ex, "need_tools", self.old[0]) or setattr(ex, "tool_versions", self.old[1]))

    def go(self, factory, *extra):
        out, err = io.StringIO(), io.StringIO()
        a = args_for("verify", str(self.scene), "--out", str(Path(self.d) / "out"), "--failure-report", str(Path(self.d) / "fail-{scene}.json"), *extra)
        return ex.run(a, False, factory=factory, stdout=out, stderr=err), out.getvalue(), err.getvalue()

    def test_verify_ok_writes_manifest_without_private_paths(self):
        rc, out, _ = self.go(lambda root, env, tm: five(end_ns=2 * 10**9)[0])
        self.assertEqual(rc, 0, out)
        txt = (Path(self.d) / "out" / ex.MANIFEST).read_text(encoding="utf-8")
        self.assertNotIn(self.d, txt)
        self.assertNotIn("/home/", txt)
        import json
        m = json.loads(txt)
        sc = m["scenes"][0]
        self.assertEqual(sc["scene"], "t.mdgl")
        self.assertEqual(sc["frames"], len(sc["frame_sha256"]))
        self.assertEqual(len(sc["scene_sha256"]), 64)
        self.assertIn("no cross-encoder byte identity", m["note"])
        self.assertEqual(sorted(p.name for p in (Path(self.d) / "out").iterdir()), [ex.MANIFEST])  # verify: no media

    def test_mismatch_exit_1_report_and_no_publication(self):
        def mut(t, fb, cells, done):
            cells[0][0] = dict(CELL, fg="blue") if t == 200_000_000 else cells[0][0]
            return cells, done
        rc, out, err = self.go(lambda root, env, tm: five("ts", mut, 2 * 10**9)[0])
        self.assertEqual(rc, ex.EXIT_MISMATCH)
        self.assertIn("MISMATCH scene=t frame 2 time_ns=200000000 row=0 col=0 field=fg go vs ts", err)
        import json
        rep = json.loads((Path(self.d) / "fail-t.json").read_text(encoding="utf-8"))
        self.assertEqual((rep["scene"], rep["time_ns"], rep["row"], rep["col"], rep["adapters"]), ("t", 200_000_000, 0, 0, ["go", "ts"]))
        self.assertEqual(len(rep["scene_sha256"]), 64)
        self.assertFalse((Path(self.d) / "out").exists())

    def test_malformed_protocol_response_exit_5(self):
        bad = f"{shlex.quote(sys.executable)} -c \"import sys; sys.stdin.readline(); print('not json')\""
        rc, _, err = self.go(lambda root, env, tm: {n: (bad, "x") for n in ex.ADAPTERS})
        self.assertEqual(rc, ex.EXIT_PROTOCOL)
        self.assertIn("protocol/transport failure", err)
        self.assertIn("non-JSON", err)
        self.assertFalse((Path(self.d) / "out").exists())

    def test_wrong_branch_response_is_protocol_failure(self):
        # a frame answer with `done` for a fallback request violates the response branch bound to the request
        script = ("import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({'v':1,'id':r['id'],'ok':True,"
                  "'diagnostics':[]} if r['op']=='check' else {'v':1,'id':r['id'],'ok':True,'width':1,'height':1,"
                  "'cells':[[{'r':'x','fg':'red','bg':''}]],'done':True}),flush=True)\n")
        p = Path(self.d) / "bad.py"
        p.write_text(script)
        cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(p))}"
        rc, _, err = self.go(lambda root, env, tm: {n: (cmd, "x") for n in ex.ADAPTERS})
        self.assertEqual(rc, ex.EXIT_PROTOCOL, err)

    def test_missing_tool_exit_3(self):
        ex.need_tools, ex.tool_versions = self.old
        saved = ex.base_env
        ex.base_env = lambda: {"PATH": "/nonexistent-dir"}
        self.addCleanup(lambda: setattr(ex, "base_env", saved))
        rc, _, err = self.go(lambda *a: self.fail("must not build"))
        self.assertEqual(rc, ex.EXIT_TOOL)
        self.assertIn("required tool(s) unavailable", err)
        self.assertIn("go", err)

    def test_need_tools_names_missing(self):
        with self.assertRaises(ex.Fail) as cm:
            self.old[0]({"PATH": "x"}, False, which=lambda n, path=None: None if n == "cmake" else "/bin/" + n)
        self.assertEqual((cm.exception.code, cm.exception.msg), (3, "required tool(s) unavailable: cmake"))

    def test_invalid_scene_exit_6(self):
        class Bad(Fake):
            def call(self, op, source, **kw):
                return {}, {"ok": True, "diagnostics": [{"line": 1, "col": 2, "message": "boom"}]}
        rc, _, err = self.go(lambda root, env, tm: {n: Bad([]) for n in ex.ADAPTERS})
        self.assertEqual(rc, ex.EXIT_SCENE)
        self.assertIn("boom", err)

    def test_missing_scene_exit_6(self):
        a = args_for("verify", "/nonexistent/s.mdgl", "--out", str(Path(self.d) / "o"))
        err = io.StringIO()
        self.assertEqual(ex.run(a, False, factory=lambda *x: self.fail("no build"), stdout=io.StringIO(), stderr=err), ex.EXIT_SCENE)


class Raster(unittest.TestCase):
    @unittest.skipUnless(ex.FONT.is_file() and importlib.util.find_spec("PIL"), "tool availability: Pillow or DejaVuSansMono.ttf missing")
    def test_raster_geometry_and_colours(self):
        r = ex.Rasteriser()
        cells = [[{"r": "⣿", "fg": "red", "bg": "blue"}, {"r": " ", "fg": "normal", "bg": ""}, {"r": "A", "fg": "#112233", "bg": ""}]]
        im = r.frame(cells)
        self.assertEqual(im.size, (3 * ex.CELL_W, ex.CELL_H))
        self.assertEqual(im.getpixel((ex.CELL_W + 1, 1)), (0, 0, 0))  # empty bg = black
        self.assertEqual(im.getpixel((0, 0)), em.PALETTE["blue"])  # named bg exactly as play's PALETTE
        cols = {p for _, p in im.crop((0, 0, ex.CELL_W, ex.CELL_H)).getcolors()}
        self.assertIn(em.PALETTE["red"], cols)  # braille drawn as a glyph in the fg colour
        self.assertEqual(r.frame(cells).tobytes(), im.tobytes())

    def _dots(self, tile):
        """set of (col,row) dots whose 2x2 block is fully fg; asserts every pixel is fg or bg."""
        fg, bg, out = em.PALETTE["red"], em.PALETTE["blue"], set()
        for c, x in enumerate(ex.BRAILLE_X):
            for r, y in enumerate(ex.BRAILLE_Y):
                px = {tile.getpixel((x + i, y + j)) for i in range(2) for j in range(2)}
                self.assertEqual(len(px), 1)
                if px == {fg}:
                    out.add((c, r))
        self.assertEqual(sum(p == fg for p in tile.getdata()), 4 * len(out))
        return out

    @unittest.skipUnless(ex.FONT.is_file() and importlib.util.find_spec("PIL"), "tool availability: Pillow or font missing")
    def test_braille_dot_masks(self):
        r = ex.Rasteriser()
        t = lambda m: r.tile(chr(0x2800 + m), "red", "blue")
        self.assertEqual(self._dots(t(0xFF)), {(c, y) for c in (0, 1) for y in range(4)})
        self.assertEqual({p for p in t(0).getdata()}, {em.PALETTE["blue"]})
        self.assertEqual(self._dots(r.tile("\u2801", "red", "blue")), {(0, 0)})
        want = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]
        for bit, pos in enumerate(want):
            self.assertEqual(self._dots(t(1 << bit)), {pos}, bit)

    @unittest.skipUnless(ex.FONT.is_file() and importlib.util.find_spec("PIL"), "tool availability: Pillow or font missing")
    def test_braille_all_256_masks(self):
        r = ex.Rasteriser()
        want = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]  # Unicode dot1..dot8 as (col,row)
        self.assertEqual((ex.CELL_W, ex.CELL_H), (8, 16))
        for m in range(256):
            tile = r.tile(chr(0x2800 + m), "red", "blue")
            self.assertEqual(tile.size, (8, 16))
            self.assertEqual(self._dots(tile), {want[b] for b in range(8) if m >> b & 1}, hex(m))
        self.assertEqual(self._dots(r.tile("\u28ff", "red", "blue")), set(want))
        self.assertEqual(set(r.tile("\u2800", "red", "blue").getdata()), {em.PALETTE["blue"]})
        for ch, pos in (("\u2801", (0, 0)), ("\u2808", (1, 0)), ("\u2840", (0, 3)), ("\u2880", (1, 3))):  # dot1/4/7/8 corners
            self.assertEqual(self._dots(r.tile(ch, "red", "blue")), {pos}, ch)

    @unittest.skipUnless(ex.FONT.is_file() and importlib.util.find_spec("PIL"), "tool availability: Pillow or font missing")
    def test_tile_cache_and_font_path(self):
        r = ex.Rasteriser()
        a = r.tile("\u2801", "red", "blue")
        self.assertIs(r.tile("\u2801", "red", "blue"), a)
        for k in (("\u2802", "red", "blue"), ("\u2801", "green", "blue"), ("\u2801", "red", "")):
            self.assertIsNot(r.tile(*k), a)
        self.assertEqual(set(r.tiles), {("\u2801", "red", "blue"), ("\u2802", "red", "blue"), ("\u2801", "green", "blue"), ("\u2801", "red", "")})
        calls = []
        orig = r.font
        class Spy:
            def __getattr__(s, n): return getattr(orig, n)
        import PIL.ImageDraw as D
        old = D.ImageDraw.text
        D.ImageDraw.text = lambda self, xy, text, *a, **k: (calls.append(text), old(self, xy, text, *a, **k))[1]
        try:
            r.tile("A", "red", "blue")
            r.tile("\u2803", "red", "blue")
        finally:
            D.ImageDraw.text = old
        self.assertEqual(calls, ["A"])  # font path for non-braille only

    def test_manifest_states_braille_method(self):
        src = Path(ex.__file__).read_text()
        self.assertIn("drawn procedurally from U+2800 dot masks (2x4 dots per 8x16 cell); the pinned font is used for all other glyphs and labels", src)
        self.assertNotIn("real font glyphs", src)

    @unittest.skipUnless(shutil.which("ffmpeg") and ex.FONT.is_file() and importlib.util.find_spec("PIL"), "tool availability: ffmpeg, Pillow or font missing")
    def test_encode_gif_has_no_private_paths_and_is_repeatable(self):
        from fractions import Fraction
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        r = ex.Rasteriser()
        for i in range(3):
            r.frame([[{"r": "ab⣿"[i], "fg": "green", "bg": ""}] * 4] * 2).save(Path(d) / f"{i:05d}.png")
        outs = []
        for n in ("a", "b"):
            flags = ex.encode(d, 3, Fraction(10, 1), True, "gif", Path(d) / f"{n}.gif", dict(os.environ))
            outs.append((Path(d) / f"{n}.gif").read_bytes())
        self.assertEqual(outs[0], outs[1])  # same machine, same ffmpeg: byte-identical (no cross-version claim)
        self.assertTrue(outs[0].startswith(b"GIF8"))
        self.assertNotIn(d, " ".join(flags))
        self.assertIn("<frames>/%05d.png", flags)
        self.assertIn("-map_metadata", flags)



class EncodedFrames(unittest.TestCase):
    def test_encoded_frame_count_includes_end_hold(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("eme", str(Path(__file__).resolve().parent / "example_media_export.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from fractions import Fraction
        self.assertEqual(mod.encoded_frames(181, Fraction(10, 1), True), 191)   # kubernetes: finite end hold of 1 s at 10 fps
        self.assertEqual(mod.encoded_frames(120, Fraction(10, 1), False), 120)  # infinite scene: no hold

if __name__ == "__main__":
    unittest.main()

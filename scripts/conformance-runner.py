#!/usr/bin/env python3
"""MDGL observable conformance runner (protocol v1, conformance/PROTOCOL.md section 5).

  conformance-runner.py --adapter 'CMD ARGS' [--suite DIR] [--class a,b] [--json] [--timeout S] [--shutdown-timeout S]

Exit 0 all selected fixtures pass, 1 some fixture failed, 2 usage error / transport failure / malformed fixture
/ zero fixtures selected. Python stdlib only.
"""
import argparse, decimal, json, os, queue, re, shlex, subprocess, sys, threading
from pathlib import Path

CLASSES = ("diagnostic", "static", "timed", "repeat", "cube")
MAX_NS = 2**53 - 1
COLOR_RE = re.compile(r"(normal|black|red|green|yellow|blue|magenta|cyan|white|accent|#[0-9a-f]{6})")
TIME_RE = re.compile(r"\+?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)


class Transport(Exception):
    """Adapter/transport failure: whole run exits 2."""


class Malformed(Exception):
    """Malformed fixture: whole run exits 2."""


def seconds_to_ns(text):
    """PROTOCOL 2.1 fixture-time rule: finite non-negative decimal/exponent seconds (optional +, no s suffix, no
    negatives incl. -0) -> integer ns, exact decimal arithmetic, nearest, ties away from zero, cap 2^53-1."""
    if not isinstance(text, str) or not TIME_RE.fullmatch(text):
        raise ValueError(f"invalid seconds {text!r}")
    d = decimal.Decimal(text)  # exact; the regex above already rejected any sign, so negatives never reach rounding
    if d > 10**7:
        raise ValueError(f"seconds {text!r} exceed 2^53-1 ns")
    # local context, independent of the process default: precision above the digit count makes scaleb exact, and
    # the exponent range admits any accepted text; ROUND_HALF_UP on a non-negative value is ties-away-from-zero
    ctx = decimal.Context(prec=len(text) + 50, rounding=decimal.ROUND_HALF_UP, Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN, traps=[decimal.InvalidOperation])
    scaled = d.scaleb(9, context=ctx)
    ns = int(scaled.quantize(decimal.Decimal(1), context=ctx))
    if ns > MAX_NS:
        raise ValueError(f"seconds {text!r} exceed 2^53-1 ns")
    return ns


def ns_to_seconds(ns):
    """Canonical short form used in reports only."""
    whole, frac = divmod(ns, 10**9)
    return str(whole) + (("." + f"{frac:09d}".rstrip("0")) if frac else "")


def derive_class(source, has_err):
    """PROTOCOL 5.1 legacy class derivation, first match wins."""
    if has_err:
        return "diagnostic"
    if "cube(" in source:
        return "cube"
    lines = source.splitlines()
    if any(l.startswith("scene") and re.search(r"\brepeat=", l) for l in lines):
        return "repeat"
    if not any(re.match(r"\s*@[0-9.+\-]+s?\s*:", l) for l in lines):
        return "static"
    return "timed"


def read_text(path):
    return Path(path).read_bytes().decode("utf-8")  # strict, newlines preserved


def load_fixtures(suite):
    """Return fixtures sorted by name; raise Malformed. fixture = dict(name, class, kind, source, ...)."""
    suite = Path(suite)
    if not suite.is_dir():
        raise Malformed(f"suite {suite} is not a directory")
    fixtures, claimed = [], set()
    obs_files = sorted(suite.glob("*.obs.json")) + sorted((suite / "observable").glob("*.obs.json"))
    for p in obs_files:
        name = p.name[: -len(".obs.json")]
        try:
            o = json.loads(read_text(p), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        except (ValueError, UnicodeDecodeError) as e:
            raise Malformed(f"{p.name}: invalid JSON: {e}")
        fixtures.append(load_obs(p.parent, name, o))
        if p.parent == suite:
            claimed.add(fixtures[-1]["source_file"])
    for p in sorted(suite.glob("*.mdgl")):
        if p.name in claimed:
            continue
        base = p.with_suffix("")
        err, exp = base.with_suffix(".err"), base.with_suffix(".expect")
        if not err.exists() and not exp.exists():
            raise Malformed(f"{p.name}: no .err, .expect or .obs.json companion")
        if err.exists() and exp.exists():
            raise Malformed(f"{p.name}: both .err and .expect")
        try:
            src = read_text(p)
            f = {"name": base.name, "source": src, "normative": True, "legacy": True, "class": derive_class(src, err.exists())}
            if err.exists():
                m = re.fullmatch(r"(\d+):(\d+): (.*)", read_text(err).strip(), re.S)
                if not m:
                    raise Malformed(f"{err.name}: not 'line:col: message'")
                f.update(kind="diag", diag=(int(m[1]), int(m[2]), m[3]))
            else:
                f.update(kind="expect", frames=parse_expect(read_text(exp), src, exp.name))
        except UnicodeDecodeError as e:
            raise Malformed(f"{base.name}: not UTF-8: {e}")
        fixtures.append(f)
    if len({f["name"] for f in fixtures}) != len(fixtures):
        raise Malformed("duplicate fixture names")
    return sorted(fixtures, key=lambda f: f["name"])


def parse_expect(text, source, fname):
    m = re.search(r"^scene\b.*?\bheight=(\d+)", source, re.M)
    if not m:
        raise Malformed(f"{fname}: cannot find scene height in source")
    height, lines, cur, frames = int(m[1]), text[:-1].split("\n") if text.endswith("\n") else text.split("\n"), 0, []
    while cur < len(lines):
        mk = lines[cur]
        cur += 1
        if not mk.startswith("@"):
            raise Malformed(f"{fname}: expected time marker, got {mk!r}")
        try:
            ns = seconds_to_ns(mk[1:])
        except ValueError as e:
            raise Malformed(f"{fname}: {e}")
        if cur + height > len(lines):
            raise Malformed(f"{fname}: missing expected row")
        frames.append((ns, lines[cur:cur + height]))
        cur += height
    return frames


def load_obs(suite, name, o):
    def bad(msg):
        raise Malformed(f"{name}.obs.json: {msg}")
    if not isinstance(o, dict):
        bad("top level must be an object")
    der = o.get("derivation")
    if not isinstance(der, str) or not der.strip():
        bad("missing or empty derivation")
    if o.get("class") not in CLASSES:
        bad(f"unknown class {o.get('class')!r}")
    sf = o.get("source_file")
    if not isinstance(sf, str) or "/" in sf or "\\" in sf or not (suite / sf).is_file():
        bad(f"source_file {sf!r} missing")
    for k in ("cols", "rows"):
        if type(o.get(k)) is not int or o[k] < 1:
            bad(f"{k} must be a positive integer")
    if not (o["cols"] <= 200 and o["rows"] <= 60):
        bad("cols/rows exceed stage limit")
    f = {"name": name, "class": o["class"], "source_file": sf, "source": read_text(suite / sf), "cols": o["cols"],
         "rows": o["rows"], "legacy": False, "normative": o.get("normative", True) is not False, "derivation": der}
    if "diagnostic" in o:
        d = o["diagnostic"]
        if o["class"] != "diagnostic" or "frames" in o or not isinstance(d, dict) or set(d) != {"line", "col", "message"} \
                or type(d["line"]) is not int or type(d["col"]) is not int or not isinstance(d["message"], str):
            bad("bad diagnostic fixture")
        f.update(kind="diag", diag=(d["line"], d["col"], d["message"]))
        return f
    if o["class"] == "diagnostic":
        bad("diagnostic class needs a diagnostic object")
    frames = o.get("frames")
    if not isinstance(frames, list) or not frames:
        bad("frames must be a non-empty list")
    out = []
    for i, fr in enumerate(frames):
        if not isinstance(fr, dict):
            bad(f"frame {i} not an object")
        fb = fr.get("fallback") is True
        if ("fallback" in fr and not fb) or (fb and "time" in fr) or (not fb and "time" not in fr):
            bad(f"frame {i}: needs exactly one of time / fallback:true")
        if fb and "done" in fr:
            bad(f"frame {i}: fallback frames have no done")
        if not fb and "done" not in fr:
            bad(f"frame {i}: done required on every non-fallback frame (including cube)")
        if "done" in fr and type(fr["done"]) is not bool:
            bad(f"frame {i}: done must be boolean")
        ns = None
        if not fb:
            try:
                ns = seconds_to_ns(fr["time"])
            except ValueError as e:
                bad(f"frame {i}: {e}")
        cells = fr.get("cells")
        if not isinstance(cells, list) or not cells or not all(isinstance(r, list) and len(r) == len(cells[0]) and r for r in cells):
            bad(f"frame {i}: cells must be a rectangular non-empty grid")
        for r in cells:
            for c in r:
                need = {"r"} if o["class"] == "cube" else {"r", "fg", "bg"}
                if not isinstance(c, dict) or not need <= set(c) or not set(c) <= {"r", "fg", "bg"}:
                    bad(f"frame {i}: cell keys must include {sorted(need)}")
                if not isinstance(c["r"], str) or len(c["r"]) != 1:
                    bad(f"frame {i}: r must be one scalar")
                if "fg" in c and not (isinstance(c["fg"], str) and COLOR_RE.fullmatch(c["fg"])):
                    bad(f"frame {i}: bad fg {c['fg']!r}")
                if "bg" in c and not (isinstance(c["bg"], str) and (c["bg"] == "" or COLOR_RE.fullmatch(c["bg"]))):
                    bad(f"frame {i}: bad bg {c['bg']!r}")
        out.append({"ns": ns, "fallback": fb, "cells": cells, "done": fr.get("done")})
    f.update(kind="obs", frames=out)
    return f


class Adapter:
    def __init__(self, cmd, cwd, timeout, shutdown_timeout=5.0):
        self.timeout, self.shutdown_timeout, self.n, self.q = timeout, shutdown_timeout, 0, queue.Queue()
        try:
            self.p = subprocess.Popen(shlex.split(cmd), cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        except (OSError, ValueError) as e:
            raise Transport(f"cannot start adapter: {e}")
        self.pump = threading.Thread(target=self._pump, daemon=True)
        self.pump.start()

    def _pump(self):
        for line in iter(self.p.stdout.readline, b""):
            self.q.put(line)
        self.q.put(None)

    def close(self):
        """End of run: close stdin, require exit 0 within the shutdown timeout and no output beyond the responses.
        Raises Transport (the caller kills the process)."""
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=self.shutdown_timeout)
        except subprocess.TimeoutExpired:
            raise Transport(f"adapter did not exit within {self.shutdown_timeout}s after stdin EOF")
        self.pump.join(timeout=2)
        extra = []
        while True:
            try:
                line = self.q.get_nowait()
            except queue.Empty:
                break
            if line is not None:
                extra.append(line)
        if extra:
            raise Transport(f"unsolicited extra output after the last response: {extra[0][:120]!r}")
        if self.p.returncode != 0:
            raise Transport(f"adapter exited with status {self.p.returncode} after stdin EOF (must be 0)")

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()

    def call(self, op, source, **kw):
        """Send one request, return (request, validated response). Raises Transport."""
        self.n += 1
        req = {"v": 1, "id": f"r{self.n}", "op": op, "source": source, **kw}
        try:
            self.p.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            self.p.stdin.flush()
        except OSError as e:
            raise Transport(f"adapter closed stdin ({e}) at request {req['id']}")
        try:
            line = self.q.get(timeout=self.timeout)
        except queue.Empty:
            raise Transport(f"timeout after {self.timeout}s waiting for response to {req['id']} ({op})")
        if line is None:
            raise Transport(f"adapter exited (status {self.p.poll()}) before answering {req['id']}")
        if not line.endswith(b"\n"):
            raise Transport(f"response to {req['id']} is not LF-terminated (EOF mid-line): {line[:120]!r}")
        try:
            resp = json.loads(line.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        except (ValueError, UnicodeDecodeError) as e:
            raise Transport(f"non-JSON response line to {req['id']}: {e}: {line[:120]!r}")
        return req, validate(req, resp)


def validate(req, resp):
    def bad(msg):
        raise Transport(f"protocol violation for {req['id']}: {msg}")
    if not isinstance(resp, dict):
        bad("response is not an object")
    if type(resp.get("v")) is not int or resp["v"] != 1:
        bad(f"v must be 1, got {resp.get('v')!r}")
    if resp.get("id") != req["id"]:
        bad(f"id mismatch: sent {req['id']!r}, got {resp.get('id')!r}")
    if type(resp.get("ok")) is not bool:
        bad("ok must be boolean")
    if not resp["ok"]:
        e = resp.get("error")
        if set(resp) != {"v", "id", "ok", "error"} or not isinstance(e, dict) or not isinstance(e.get("message"), str):
            bad("malformed error response")
        code = e.get("code")
        if code != "invalid_source":
            raise Transport(f"adapter error {code!r} on valid request {req['id']}: {e.get('message')}")
        if req["op"] != "frame" or set(e) != {"code", "message", "diagnostics"}:
            bad("invalid_source only valid for frame, with diagnostics")
        check_diags(e["diagnostics"], bad, nonempty=True)
        return resp
    if req["op"] == "check":
        if set(resp) != {"v", "id", "ok", "diagnostics"}:
            bad(f"check response keys {sorted(resp)}")
        check_diags(resp["diagnostics"], bad)
        return resp
    fb = req.get("fallback") is True
    if set(resp) != {"v", "id", "ok", "width", "height", "cells"} | (set() if fb else {"done"}):
        bad(f"frame response keys {sorted(resp)} (fallback={fb}; done must be {'omitted' if fb else 'present'})")
    w, h, cells = resp["width"], resp["height"], resp["cells"]
    if type(w) is not int or type(h) is not int or not (1 <= w <= min(200, req["width"])) or not (1 <= h <= min(60, req["height"])):
        bad(f"width/height {w!r}x{h!r} outside 1..request size")
    if not isinstance(cells, list) or len(cells) != h or any(not isinstance(r, list) or len(r) != w for r in cells):
        bad(f"cells is not {h} rows of {w} cells")
    for y, r in enumerate(cells):
        for x, c in enumerate(r):
            if not isinstance(c, dict) or set(c) != {"r", "fg", "bg"} or not all(isinstance(c[k], str) for k in c):
                bad(f"cell[{y}][{x}] is not {{r,fg,bg}} strings")
            if len(c["r"]) != 1 or not COLOR_RE.fullmatch(c["fg"]) or not (c["bg"] == "" or COLOR_RE.fullmatch(c["bg"])):
                bad(f"cell[{y}][{x}] invalid value {c!r}")
    if not fb and type(resp["done"]) is not bool:
        bad("done must be boolean")
    return resp


def check_diags(ds, bad, nonempty=False):
    if not isinstance(ds, list) or (nonempty and not ds):
        bad("diagnostics must be an array" + (" (non-empty)" if nonempty else ""))
    for d in ds:
        if not isinstance(d, dict) or set(d) != {"line", "col", "message"} or type(d["line"]) is not int \
                or type(d["col"]) is not int or d["line"] < 1 or d["col"] < 1 or not isinstance(d["message"], str):
            bad(f"bad diagnostic {d!r}")


def clip(s, n=120):
    s = repr(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def run_fixture(ad, f):
    """Return None on pass else a first-difference string. Raises Transport."""
    if f["kind"] == "diag":
        _, r = ad.call("check", f["source"])
        want = f["diag"]
        if not r["diagnostics"]:
            return f"expected diagnostic {want[0]}:{want[1]}: {clip(want[2])}, got none"
        d = r["diagnostics"][0]
        got = (d["line"], d["col"], d["message"])
        for label, i in (("line", 0), ("col", 1), ("message", 2)):
            if got[i] != want[i]:
                return f"first diagnostic {label}: expected {clip(want[i])} got {clip(got[i])}"
        return None
    seen = {}
    if f["kind"] == "expect":
        for ns, rows in f["frames"]:
            _, r = ad.call("frame", f["source"], time_ns=ns, width=200, height=60)
            if r["ok"] is False:
                return f"@{ns_to_seconds(ns)}: unexpected invalid_source: {clip(r['error']['diagnostics'][0]['message'])}"
            w = r["width"]
            if len(r["cells"]) != len(rows):
                return f"@{ns_to_seconds(ns)}: expected {len(rows)} rows, got {len(r['cells'])}"
            for y, (want, cr) in enumerate(zip(rows, r["cells"])):
                got = "".join(c["r"] for c in cr)
                want = want + " " * (w - len(want))
                if got != want:
                    return f"@{ns_to_seconds(ns)} row {y}: expected {clip(want)} got {clip(got)}"
        return None
    for i, fr in enumerate(f["frames"]):
        label = "fallback" if fr["fallback"] else f"t={ns_to_seconds(fr['ns'])}"
        kw = {"fallback": True} if fr["fallback"] else {"time_ns": fr["ns"]}
        _, r = ad.call("frame", f["source"], width=f["cols"], height=f["rows"], **kw)
        if r["ok"] is False:
            return f"{label}: unexpected invalid_source: {clip(r['error']['diagnostics'][0]['message'])}"
        sig = json.dumps([r["cells"], r.get("done")], sort_keys=True)
        key = "fallback" if fr["fallback"] else fr["ns"]
        if key in seen and seen[key] != sig:
            return f"{label}: seek impurity, repeated request gave a different response than frame {i} earlier"
        seen[key] = sig
        want = fr["cells"]
        if len(r["cells"]) != len(want) or len(r["cells"][0]) != len(want[0]):
            return f"{label}: expected size {len(want[0])}x{len(want)} got {r['width']}x{r['height']}"
        for y, (wr, gr) in enumerate(zip(want, r["cells"])):
            for x, (wc, gc) in enumerate(zip(wr, gr)):
                for k in ("r", "fg", "bg"):
                    if k in wc and wc[k] != gc[k]:
                        return f"{label} cell[{y}][{x}].{k}: expected {clip(wc[k])} got {clip(gc[k])}"
        if not fr["fallback"] and r["done"] != fr["done"]:
            return f"{label} done: expected {fr['done']} got {r['done']}"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="MDGL observable conformance runner (protocol v1)")
    ap.add_argument("--adapter", required=True, help="adapter command line (shlex-split, no shell)")
    ap.add_argument("--suite", default=str(Path(__file__).resolve().parent.parent / "conformance"))
    ap.add_argument("--class", dest="classes", default=",".join(CLASSES), help="comma list of: " + ",".join(CLASSES))
    ap.add_argument("--json", action="store_true", help="print a single JSON report on stdout")
    ap.add_argument("--timeout", type=float, default=10.0, help="per-request timeout seconds (default 10)")
    ap.add_argument("--shutdown-timeout", type=float, default=5.0, help="seconds the adapter may take to exit after stdin EOF (default 5)")
    args = ap.parse_args(argv)
    sel = [c for c in args.classes.split(",") if c]
    if not sel or any(c not in CLASSES for c in sel) or args.timeout <= 0 or args.shutdown_timeout <= 0:
        print(f"usage error: bad --class/--timeout (classes: {','.join(CLASSES)})", file=sys.stderr)
        return 2
    try:
        fixtures = load_fixtures(args.suite)
    except Malformed as e:
        print(f"malformed fixture: {e}", file=sys.stderr)
        return 2
    chosen = [f for f in fixtures if f["class"] in sel]
    if not chosen:
        print("no fixtures selected", file=sys.stderr)
        return 2
    results, ad = [], None
    try:
        ad = Adapter(args.adapter, args.suite, args.timeout, args.shutdown_timeout)
        for f in chosen:
            why = run_fixture(ad, f)
            results.append({"name": f["name"], "class": f["class"], "normative": f["normative"],
                            "status": "fail" if why else "pass", "detail": why or "",
                            "basis": "glyph-only" if f["legacy"] else "observable"})
            if not args.json:
                print(f"{'FAIL' if why else 'PASS'} {f['class']} {f['name']}" + (f": {why}" if why else ""), flush=True)
        ad.close()
    except Transport as e:
        if ad:
            ad.kill()
        print(f"transport failure: {e}", file=sys.stderr)
        return 2
    passed = sum(r["status"] == "pass" for r in results)
    per = {c: sum(r["class"] == c for r in results) for c in sel}
    none = [c for c in sel if per[c] == 0]
    cnt = {k: {"passed": 0, "failed": 0} for k in ("normative", "nonnormative")}
    for r in results:
        cnt["normative" if r["normative"] else "nonnormative"]["passed" if r["status"] == "pass" else "failed"] += 1
    need = {f["class"] for f in fixtures if f["normative"]}
    ran = {r["class"] for r in results if r["normative"]}
    missing = sorted(need - ran)
    if cnt["normative"]["failed"]:
        verdict = "NORMATIVE FIXTURES FAILED"
    elif cnt["normative"]["passed"] == 0:
        verdict = "NOT CERTIFIED: no normative fixtures ran"
    elif missing:
        verdict = "NOT CERTIFIED: normative classes not run: " + ",".join(missing)
    else:
        verdict = "ALL NORMATIVE FIXTURES PASSED"
    if args.json:
        print(json.dumps({"protocol": 1, "adapter": args.adapter, "total": len(results), "passed": passed,
                          "failed": len(results) - passed, "counts": cnt, "verdict": verdict, "results": results,
                          "classes": per, "no_fixtures": none}))
    else:
        print(f"summary: {passed} passed, {len(results) - passed} failed")
        print("fixtures per class: " + " ".join(f"{c}={per[c]}" for c in sel if per[c]))
        for c in none:
            print(f"class {c}: no fixtures")
        n, m = cnt["normative"], cnt["nonnormative"]
        glyph = sum(r["basis"] == "glyph-only" for r in results)
        if glyph:
            print(f"glyph-only legacy fixtures: {glyph} (no fg/bg/done claim)")
        print(f"normative: {n['passed']} passed, {n['failed']} failed")
        if m["passed"] or m["failed"]:
            print(f"non-normative: {m['passed']} assumption-based pass (not certification), {m['failed']} failed")
        else:
            print("non-normative: no fixtures")
        print(verdict)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

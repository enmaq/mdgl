#!/usr/bin/env python3
"""Play, verify and export the MDGL showcase demos.

  example-media.py [play] [SCENE.mdgl ...] [--loops N] [--forever] [--trace FILE]
  example-media.py verify [SCENE.mdgl ...] [--out DIR]   build all five adapters, compare every frame exactly, write the manifest
  example-media.py export [SCENE.mdgl ...] [--out DIR]   verify, then GIF/MP4 + manifest only if all five agree

`play` takes frames from the Go conformance adapter (protocol v1, op "frame"), built into a temp dir; `verify`/`export` live in
example_media_export.py (see `verify -h`). Exit codes of play: 0 ok, 1 adapter/scene error, 2 usage/missing tool, 130 interrupted.
play is stdlib only; export additionally needs Pillow and ffmpeg.
"""
import argparse, atexit, importlib.util, locale, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SCENES = ["examples/neon-cube.mdgl", "examples/kubernetes.mdgl", "examples/llm.mdgl"]
PALETTE = {  # fixed display colours; normal = white, accent = cyan
    "normal": (229, 229, 229), "black": (40, 40, 40), "red": (255, 85, 85), "green": (80, 250, 123),
    "yellow": (241, 250, 140), "blue": (98, 114, 255), "magenta": (255, 121, 198), "cyan": (139, 233, 253),
    "white": (229, 229, 229), "accent": (139, 233, 253),
}
HOLD_S = 1.0
CAP_S = 120.0  # safety bound for a scene with neither period nor finite done
ESC = "\x1b"
RESET = ESC + "[0m"
HIDE, SHOW = ESC + "[?25l", ESC + "[?25h"
SYNC_ON, SYNC_OFF = ESC + "[?2026h", ESC + "[?2026l"
HEADER_RE = re.compile(r"^scene\b(.*)$", re.M)


class Interrupted(BaseException):
    pass


class SceneError(Exception):
    pass


def parse_header(source):
    """-> dict(width, height, fps, period_ns|None, repeat: 'infinite'|int|None). Missing width/height -> None."""
    m = HEADER_RE.search(source)
    if not m:
        raise SceneError("no scene header line")
    h = m.group(1)
    def num(key, cast=int):
        k = re.search(r"\b" + key + r"=([0-9.]+)", h)
        return cast(k.group(1)) if k else None
    p = re.search(r"\bperiod=([0-9.]+)(ms|s)?\b", h)
    period = None
    if p:
        period = round(float(p.group(1)) * (1e6 if p.group(2) == "ms" else 1e9))
    r = re.search(r"\brepeat=(infinite|[0-9]+)", h)
    repeat = None if not r else ("infinite" if r.group(1) == "infinite" else int(r.group(1)))
    return {"width": num("width"), "height": num("height"), "fps": num("fps") or 30, "period_ns": period, "repeat": repeat}


def frame_time_ns(k, fps):
    return round(k * 1e9 / fps)


def limit_ns(hdr, forever=False):
    """Playback bound in ns, or None = until done (capped by CAP_S)."""
    if forever:
        return None
    p, r = hdr["period_ns"], hdr["repeat"]
    if p is None:
        return None
    return p * r if isinstance(r, int) else p


def sgr(fg, bg):
    r, g, b = color_rgb(fg)
    s = f"{ESC}[38;2;{r};{g};{b}m"
    if bg:
        r, g, b = color_rgb(bg)
        return s + f"{ESC}[48;2;{r};{g};{b}m"
    return s + ESC + "[49m"


def color_rgb(c):
    if c in PALETTE:
        return PALETTE[c]
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    raise SceneError(f"unknown colour {c!r}")


def row_ansi(cells):
    out, cur = [], None
    for c in cells:
        key = (c["fg"], c["bg"])
        if key != cur:
            out.append(sgr(*key))
            cur = key
        out.append(c["r"])
    out.append(RESET)
    return "".join(out)


def row_plain(cells):
    return "".join(c["r"] for c in cells).rstrip()


class Out:
    def __init__(self, stream):
        self.stream = stream
        self.bytes = 0

    def write(self, s):
        if hasattr(self.stream, "buffer"):
            b = s.encode("utf-8")
            self.stream.buffer.write(b)
            self.bytes += len(b)
        else:
            self.stream.write(s)
            self.bytes += len(s)

    def flush(self):
        try:
            self.stream.flush()
        except (OSError, ValueError):
            pass


class Renderer:
    def __init__(self, out, top=2):
        self.out, self.top, self.prev = out, top, []

    def begin(self, title, h):
        self.prev = []
        self.out.write(ESC + "[2J" + ESC + "[H" + RESET + title + "\n")
        self.h = h

    def draw(self, cells):
        rows = [row_ansi(r) for r in cells]
        parts = [f"{ESC}[{self.top + y};1H{row}" for y, row in enumerate(rows) if y >= len(self.prev) or self.prev[y] != row]
        self.prev = rows
        if parts:
            self.out.write(SYNC_ON + "".join(parts))
            self.out.write(SYNC_OFF)
            self.out.flush()

    def end(self):
        self.out.write(f"{ESC}[{self.top + self.h};1H{RESET}\n")


def load_adapter_class():
    spec = importlib.util.spec_from_file_location("conformance_runner", REPO / "scripts" / "conformance-runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Adapter, mod.Transport


def build_adapter():
    if not shutil.which("go"):
        raise FileNotFoundError("`go` not found on PATH (needed to build the Go adapter)")
    tmp = tempfile.mkdtemp(prefix="mdgl-media-")
    atexit.register(shutil.rmtree, tmp, True)
    exe = os.path.join(tmp, "mdgl-conformance")
    p = subprocess.run(["go", "build", "-buildvcs=false", "-o", exe, "./cmd/conformance"], cwd=REPO / "go", capture_output=True, text=True)
    if p.returncode:
        raise SceneError("go build failed: " + p.stderr.strip()[-600:])
    return exe


def make_adapter(exe):
    Adapter, _ = load_adapter_class()
    return Adapter(shlex.quote(exe), str(REPO), 30.0)


def req_frame(ad, source, **kw):
    _, r = ad.call("frame", source, **kw)
    if not r["ok"]:
        d = r["error"]["diagnostics"][0]
        raise SceneError(f"invalid scene: line {d['line']}: {d['message']}")
    return r


def title_for(path):
    return f"== {Path(path).stem} =="


def play_plain(ad, scenes, out):
    """Fallback frame of each scene once, no ESC bytes."""
    rc = 0
    for path, source in scenes:
        try:
            hdr = parse_header(source)
            r = req_frame(ad, source, width=hdr["width"] or 200, height=hdr["height"] or 60, fallback=True)
        except SceneError as e:
            sys.stderr.write(f"{path}: {e}\n")
            rc = 1
            continue
        out.write(title_for(path) + "\n" + "\n".join(row_plain(r_) for r_ in r["cells"]) + "\n")
    out.flush()
    return rc


def play_scene(ad, source, out, title, loops, forever, trace, clock=time.monotonic, sleep=time.sleep):
    hdr = parse_header(source)
    w, h = hdr["width"] or 200, hdr["height"] or 60
    fps, lim = hdr["fps"], limit_ns(hdr, forever)
    rend = Renderer(out)
    n = 0
    n_loops = 0
    while forever or n_loops < loops:
        n_loops += 1
        rend.begin(title, h)
        def show(t):
            nonlocal n
            r = req_frame(ad, source, time_ns=t, width=w, height=h, fallback=False)
            rend.draw(r["cells"])
            n += 1
            if trace is not None:
                trace.write(f"{t}\n")
            return r
        t0, last_k, last_cells, done = clock(), -1, None, False
        while not done:
            el = int((clock() - t0) * 1e9)
            k = el * fps // 10**9  # newest due frame; late ones are dropped
            if k == last_k:
                sleep(max(0.0, min(0.01, (frame_time_ns(k + 1, fps) - el) / 1e9)))
                continue
            t = frame_time_ns(k, fps)
            if lim is not None and t >= lim:
                break
            if lim is None and t > CAP_S * 1e9:
                break
            r = show(t)
            last_k, last_cells = k, r["cells"]
            done = r["done"] and not forever
            h = r["height"]
        if not done and not forever and lim is not None and hdr["repeat"] != "infinite":
            show(lim)  # finite scene: draw the exact end state (done) once, then hold it
        sleep(HOLD_S)
    rend.end()
    return n


def cmd_play(args, ad_factory=None, stdout=None, is_tty=None):
    scenes, missing = [], []
    for p in args.scenes or DEFAULT_SCENES:
        path = Path(p) if os.path.isabs(p) or args.scenes else REPO / p
        try:
            scenes.append((str(p), path.read_text(encoding="utf-8")))
        except OSError as e:
            sys.stderr.write(f"example-media: missing scene {p}: {e.strerror}\n")
            missing.append(p)
    stdout = stdout or sys.stdout
    tty = stdout.isatty() if is_tty is None else is_tty
    plain = (not tty) or os.environ.get("NO_COLOR") or os.environ.get("MDGL_REDUCED_MOTION")
    if not scenes:
        return 1
    out = Out(stdout)
    try:
        ad = ad_factory() if ad_factory else make_adapter(build_adapter())
    except FileNotFoundError as e:
        sys.stderr.write(f"example-media: {e}\n")
        return 2
    except SceneError as e:
        sys.stderr.write(f"example-media: {e}\n")
        return 1
    _, Transport = load_adapter_class()
    rc = 0
    trace = open(args.trace, "w") if args.trace else None
    try:
        if plain:
            rc = play_plain(ad, scenes, out)
        else:
            if "utf-8" not in (locale.getpreferredencoding(False) or "").lower().replace("_", "-") \
                    and "utf" not in (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or "").lower():
                sys.stderr.write("example-media: warning: locale does not look like UTF-8; writing UTF-8 anyway\n")
            out.write(HIDE)
            try:
                for path, source in scenes:
                    try:
                        play_scene(ad, source, out, title_for(path), args.loops, args.forever, trace)
                    except SceneError as e:
                        out.write(SYNC_OFF + RESET + "\n")
                        sys.stderr.write(f"{path}: {e}\n")
                        rc = 1
            finally:
                out.write(SYNC_OFF + RESET + SHOW + "\n")
                out.flush()
        try:
            ad.close()
        except Transport as e:
            sys.stderr.write(f"example-media: adapter: {e}\n")
            rc = 1
    except Transport as e:
        sys.stderr.write(f"example-media: adapter error: {e}\n")
        rc = 1
        try:
            ad.kill()
        except Exception:
            pass
    except BaseException:
        try:
            ad.kill()
        except Exception:
            pass
        raise
    finally:
        if trace:
            trace.close()
    return 1 if missing else rc


def build_parser():
    ap = argparse.ArgumentParser(prog="example-media.py", description=__doc__.split("\n\n")[0],
                                 epilog="Usage:\n  python3 scripts/example-media.py                      play the three showcase demos once\n"
                                        "  python3 scripts/example-media.py play examples/llm.mdgl --loops 2\n"
                                        "  python3 scripts/example-media.py play > out.txt      plain fallback frames (not a TTY)\n"
                                        "Options (see `play -h`): --loops N repeat each scene N times; --forever is the ONLY unbounded mode (runs until Ctrl+C).\n"
                                        "Needs `go` on PATH (builds the Go adapter into a temp dir). Ctrl+C stops; the terminal is restored.\n"
                                        "Exit codes: 0 ok, 1 adapter/scene error or missing scene, 2 usage/missing tool (go), 130 interrupted.\n"
                                        "Env: NO_COLOR or MDGL_REDUCED_MOTION (non-empty) -> plain fallback frames, no ANSI.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("play", help="play scenes in the terminal (default subcommand)",
                       description="Play scenes in order with a title line between them. Each scene runs one period (explicit "
                                   "period) or until done (finite repeat), then holds the last frame ~1 s. When stdout is not a TTY, "
                                   "or NO_COLOR / MDGL_REDUCED_MOTION is set, prints each scene's plain-text fallback frame once.",
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scenes", nargs="*", metavar="SCENE.mdgl", help="default: " + ", ".join(DEFAULT_SCENES))
    p.add_argument("--loops", type=int, default=1, metavar="N", help="repeat each scene N times (default 1)")
    p.add_argument("--forever", action="store_true", help="UNBOUNDED: loop each scene (and never stop) until Ctrl+C")
    p.add_argument("--trace", metavar="FILE", help="write the time_ns of every shown frame to FILE (one per line)")
    p.set_defaults(func=cmd_play)
    spec = importlib.util.spec_from_file_location("example_media_export", Path(__file__).resolve().parent / "example_media_export.py")
    exp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exp)
    exp.add_parsers(sub)
    return ap


def main(argv=None, **hooks):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("play", "verify", "export", "-h", "--help"):
        argv = ["play"] + argv
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "loops", 1) < 1:
        ap.error("--loops must be >= 1")
    def on_term(*_):
        raise Interrupted()
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass
    try:
        return args.func(args, **hooks)
    except (KeyboardInterrupt, Interrupted):
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    if not sys.stdout.isatty() and getattr(sys.stdout, "encoding", "").lower().replace("_", "-") != "utf-8":
        pass  # Out writes UTF-8 bytes via sys.stdout.buffer regardless of the locale
    sys.exit(main())

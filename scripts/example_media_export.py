"""Five-adapter verify/export engine behind `scripts/example-media.py verify|export` (stdlib + Pillow + ffmpeg).

Pipeline: copy the source tree to an isolated stage, build all five conformance adapters there (Go, Rust, C, TypeScript,
Python), run `check` and then every frame of every scene through all five, streaming one frame at a time and comparing the
cells exactly (rune, fg, bg per cell, and `done`; no trimming, no normalisation). The fallback frame is compared separately.
Only when every scene agrees does `export` rasterise (Pillow) and encode (ffmpeg); a run with any difference publishes no media.

Exit codes: 0 ok; 1 adapter disagreement (first difference reported); 2 usage; 3 required tool unavailable; 4 build failed;
5 protocol / transport failure or malformed response; 6 invalid scene; 7 raster / encode failure.
Encoded bytes are only reproducible with the same ffmpeg and font versions; no cross-encoder byte identity is claimed.
"""
import hashlib, importlib.util, json, math, os, platform, shlex, shutil, subprocess, sys, tempfile, time
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
EXIT_OK, EXIT_MISMATCH, EXIT_USAGE, EXIT_TOOL, EXIT_BUILD, EXIT_PROTOCOL, EXIT_SCENE, EXIT_ENCODE = 0, 1, 2, 3, 4, 5, 6, 7
ADAPTERS = ("go", "rust", "c", "ts", "python")
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
CELL_W, CELL_H, FONT_PX, GLYPH_DY = 8, 16, 13, 1  # fixed raster geometry
BRAILLE_DOT, BRAILLE_X, BRAILLE_Y = 2, (1, 5), (1, 5, 9, 13)  # 2x2 px dots, top-left corners of the 2 cols x 4 rows
BRAILLE_BIT_POS = {0: (0, 0), 1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 1), 5: (1, 2), 6: (0, 3), 7: (1, 3)}  # bit -> (col, row)
GIF_FPS_CAP = 10  # raster/encode every ceil(fps/10)-th agreed frame (comparison still covers every frame)
HOLD_S = 1  # finite scenes: last frame held this long in the media
BUILD_TIMEOUT = 1800
MANIFEST = "example-media-manifest.json"
FFMPEG_GLOBAL = ["-hide_banner", "-loglevel", "error", "-y"]
FFMPEG_OUTPUT = ["-fflags", "+bitexact", "-map_metadata", "-1", "-an"]  # no metadata, no audio, bitexact muxing
NOTE = ("Encoded bytes are only reproducible with the same ffmpeg and font versions; no cross-encoder byte identity is "
        "claimed. The compared cell data (frame and sequence hashes) is the deterministic part.")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


em = _load("example_media_core", HERE / "example-media.py")
cr = _load("conformance_runner_core", HERE / "conformance-runner.py")
Transport = cr.Transport


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


class Mismatch(Exception):
    def __init__(self, report):
        super().__init__(describe(report))
        self.report = report


def describe(r):
    where = "fallback frame" if r["fallback"] else f"frame {r['frame_index']} time_ns={r['time_ns']}"
    pos = "" if r["row"] is None else f" row={r['row']} col={r['col']}"
    a, b = r["adapters"]
    return (f"MISMATCH scene={r['scene']} {where}{pos} field={r['field']} {a} vs {b}: "
            f"{a}={json.dumps(r['detail'][a], ensure_ascii=False)} {b}={json.dumps(r['detail'][b], ensure_ascii=False)}")


# ---------------------------------------------------------------- comparison

def canon(resp):
    """Canonical observable of an ok frame response: size, every cell's rune/fg/bg, and `done` (value, or absent for fallback)."""
    done = ["done", resp["done"]] if "done" in resp else ["no-done"]
    return json.dumps([resp["width"], resp["height"], [[[c["r"], c["fg"], c["bg"]] for c in row] for row in resp["cells"]], done],
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def diff_resp(ra, rb):
    """-> None or (field, row, col, detail_a, detail_b) for the first difference between two ok frame responses."""
    if (ra["width"], ra["height"]) != (rb["width"], rb["height"]):
        return "size", None, None, [ra["width"], ra["height"]], [rb["width"], rb["height"]]
    for y, (xa, xb) in enumerate(zip(ra["cells"], rb["cells"])):
        for x, (ca, cb) in enumerate(zip(xa, xb)):
            if ca != cb:
                keys = [k for k in ("r", "fg", "bg") if ca.get(k) != cb.get(k)]
                return "+".join(keys) or "cell", y, x, {k: ca.get(k) for k in ("r", "fg", "bg")}, {k: cb.get(k) for k in ("r", "fg", "bg")}
    if ra.get("done") != rb.get("done"):
        return "done", None, None, ra.get("done"), rb.get("done")
    return None


def ask(adapters, source, scene, idx, t, w, h, fallback=False):
    """One frame from every adapter, compared against the first; returns the agreed (reference) response."""
    names, got = list(adapters), {}
    for n in names:
        kw = {"fallback": True} if fallback else {"time_ns": t}
        req, r = adapters[n].call("frame", source, width=w, height=h, **kw)
        got[n] = (req, r)
    oks = {n: got[n][1]["ok"] for n in names}
    if not any(oks.values()):
        d = got[names[0]][1]["error"]["diagnostics"][0]
        raise Fail(EXIT_SCENE, f"{scene}: invalid scene: line {d['line']}: {d['message']}")
    ref = names[0]

    def view(n):  # what the adapter answered, for the report: "ok" or its error code/message
        r = got[n][1]
        return "ok" if r["ok"] else {"code": r["error"].get("code"), "message": r["error"].get("message")}

    for n in names[1:]:
        if oks[ref] and oks[n]:
            res = diff_resp(got[ref][1], got[n][1])
        elif view(ref) != view(n):
            res = ("ok", None, None, view(ref), view(n))
        else:
            res = None  # both refused identically; some other adapter accepted and will mismatch against ref
        if res:
            field, row, col, da, db = res
            req_view = {k: v for k, v in got[ref][0].items() if k not in ("source", "id")}
            full = lambda nm: ({"cell": (got[nm][1]["cells"][row][col] if row is not None else None), "done": got[nm][1].get("done")}
                               if oks[nm] else {"error": view(nm)})
            raise Mismatch({"scene": scene, "time_ns": None if fallback else t, "frame_index": idx, "fallback": fallback,
                            "request": req_view, "row": row, "col": col, "field": field, "adapters": [ref, n],
                            "detail": {ref: da, n: db}, "full": {ref: full(ref), n: full(n)}})
    return got[ref][1]


def compare_scene(scene, source, adapters, sink=None, cap_s=em.CAP_S):
    """Stream every frame of one scene through all adapters (same sampling as `play`). sink(idx, t, resp, is_end) sees
    each agreed frame once. Returns a summary dict; raises Mismatch / Fail / Transport."""
    hdr = em.parse_header(source)
    w, h, fps, lim = hdr["width"] or 200, hdr["height"] or 60, hdr["fps"], em.limit_ns(hdr)
    names = list(adapters)
    for n in names:  # check must agree: no diagnostics from anyone
        _, r = adapters[n].call("check", source)
        if r["diagnostics"]:
            d = r["diagnostics"][0]
            raise Fail(EXIT_SCENE, f"{scene}: {n} check reports line {d['line']} col {d['col']}: {d['message']}")
    seq, hashes, k, done, idx, times = hashlib.sha256(), [], 0, False, 0, []

    def take(t, is_end):
        nonlocal idx, done
        r = ask(adapters, source, scene, idx, t, w, h)
        fh = hashlib.sha256(canon(r)).hexdigest()
        hashes.append(fh)
        seq.update(f"{idx} {t} {int(r['done'])} {fh}\n".encode())
        if sink:
            sink(idx, t, r, is_end)
        idx += 1
        return r

    while True:
        t = em.frame_time_ns(k, fps)
        if (lim is not None and t >= lim) or (lim is None and t > cap_s * 10**9):
            break
        r = take(t, False)
        k += 1
        done = r["done"]
        if done:
            break
    end = False
    if not done and lim is not None and hdr["repeat"] != "infinite":
        take(lim, True)
        end = True
    fb = ask(adapters, source, scene, "fallback", None, w, h, fallback=True)
    return {"width": w, "height": h, "fps": fps, "period_ns": hdr["period_ns"], "repeat": hdr["repeat"], "frames": idx,
            "end_frame": end, "end_time_ns": lim if end else None, "frame_sha256": hashes, "sequence_sha256": seq.hexdigest(),
            "fallback_sha256": hashlib.sha256(canon(fb)).hexdigest()}


# ---------------------------------------------------------------- tools, stage, builds

def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def base_env():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir() and str(cargo_bin) not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = env.get("PATH", "") + os.pathsep + str(cargo_bin)
    return env


def need_tools(env, export, which=shutil.which):
    path = env.get("PATH")
    names = ["go", "cargo", "rustc", "cmake", "cc", "node", "npm", "python3"] + (["ffmpeg"] if export else [])
    missing = [n for n in names if not which(n, path=path)]
    if export:
        try:
            import PIL  # noqa: F401
        except ImportError:
            missing.append("python Pillow")
        if not FONT.is_file():
            missing.append(f"font {FONT}")
    if missing:
        raise Fail(EXIT_TOOL, "required tool(s) unavailable: " + ", ".join(missing))


def tool_versions(env, export):
    def first(*cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
            return (p.stdout or p.stderr).strip().splitlines()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            return "unknown"
    v = {"go": first("go", "version"), "rustc": first("rustc", "--version"), "cargo": first("cargo", "--version"),
         "cmake": first("cmake", "--version"), "cc": first("cc", "--version"), "node": first("node", "--version"),
         "npm": first("npm", "--version"), "python": platform.python_version()}
    if export:
        import PIL
        v["pillow"] = PIL.__version__
        v["ffmpeg"] = first("ffmpeg", "-version")
    return v


def copy_stage(root):
    """Copy the sources the five adapters need into root/src (no build outputs, no node_modules)."""
    ignore = shutil.ignore_patterns("node_modules", "target", "dist", "build", ".git", "__pycache__", ".examples", "*.pyc")
    src = Path(root) / "src"
    for d in ("go", "rust", "c", "ts", "python", "conformance", "examples"):
        shutil.copytree(REPO / d, src / d, ignore=ignore)
    for f in ("VERSION", "SPEC.md", "LICENSE-MIT", "LICENSE-APACHE"):
        if (REPO / f).is_file():
            shutil.copy2(REPO / f, src / f)
    return src


def run_build(label, cmd, cwd, env):
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=BUILD_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise Fail(EXIT_BUILD, f"build {label} failed: {e}")
    if p.returncode:
        raise Fail(EXIT_BUILD, f"build {label} failed (exit {p.returncode}): {(p.stderr or p.stdout).strip()[-700:]}")


def build_all(root, env, timings):
    """Build the five adapters inside root; -> {name: (command line, manifest command with placeholders)}."""
    root, src = Path(root), copy_stage(root)
    cache, bins = root / "cache", root / "bin"
    bins.mkdir(parents=True, exist_ok=True)
    genv = dict(env, GOCACHE=str(cache / "go-build"), GOFLAGS="-buildvcs=false", GOPATH=str(cache / "gopath"),
                GOMODCACHE=str(cache / "gomod"), GOTOOLCHAIN="local")
    try:  # seed from the user's module download cache when present (offline accelerator; network is the fallback)
        mc = subprocess.run(["go", "env", "GOMODCACHE"], capture_output=True, text=True, env=env).stdout.strip()
        if mc and (Path(mc) / "cache" / "download").is_dir():
            genv["GOPROXY"] = f"file://{mc}/cache/download,https://proxy.golang.org,direct"
    except OSError:
        pass
    renv = dict(env, CARGO_TARGET_DIR=str(cache / "cargo-target"))
    nenv = dict(env, npm_config_cache=str(cache / "npm"), npm_config_update_notifier="false")
    steps = [
        ("go", [["go", "build", "-buildvcs=false", "-o", str(bins / "mdgl-go"), "./cmd/conformance"]], src / "go", genv),
        ("rust", [["cargo", "build", "--release", "--locked", "--manifest-path", str(src / "rust" / "Cargo.toml"), "--bin", "mdgl-adapter"]], src, renv),
        ("c", [["cmake", "-S", str(src / "c"), "-B", str(root / "build" / "c")], ["cmake", "--build", str(root / "build" / "c"), "--target", "mdgl_adapter"]], src, env),
        ("ts", [["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], ["npm", "run", "build"]], src / "ts", nenv),
    ]
    for label, cmds, cwd, e in steps:
        t0 = time.monotonic()
        for c in cmds:
            run_build(label, c, cwd, e)
        timings[f"build_{label}"] = round(time.monotonic() - t0, 2)
    out = {
        "go": (shlex.quote(str(bins / "mdgl-go")), "<stage>/bin/mdgl-go"),
        "rust": (shlex.quote(str(cache / "cargo-target" / "release" / "mdgl-adapter")), "<stage>/cache/cargo-target/release/mdgl-adapter"),
        "c": (shlex.quote(str(root / "build" / "c" / "mdgl_adapter")), "<stage>/build/c/mdgl_adapter"),
        "ts": ("node " + shlex.quote(str(src / "ts" / "bin" / "mdgl-adapter.js")), "node <stage>/src/ts/bin/mdgl-adapter.js"),
        "python": (f"env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(str(src / 'python'))} python3 -m mdgl.adapter",
                   "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<stage>/src/python python3 -m mdgl.adapter"),
    }
    return {n: out[n] for n in ADAPTERS}


# ---------------------------------------------------------------- raster + encode

class Rasteriser:
    def __init__(self, font=FONT):
        from PIL import Image, ImageFont
        self.Image, self.font, self.tiles, self.rows = Image, ImageFont.truetype(str(font), FONT_PX), {}, {}

    def tile(self, rune, fg, bg):
        key = (rune, fg, bg)
        t = self.tiles.get(key)
        if t is None:
            from PIL import ImageDraw
            t = self.Image.new("RGB", (CELL_W, CELL_H), em.color_rgb(bg) if bg else (0, 0, 0))
            if "\u2800" <= rune <= "\u28ff":  # braille: drawn from the dot mask (the pinned font has no braille glyphs)
                mask, d, px = ord(rune) - 0x2800, ImageDraw.Draw(t), em.color_rgb(fg)
                for bit, (c, r) in BRAILLE_BIT_POS.items():
                    if mask >> bit & 1:
                        x, y = BRAILLE_X[c], BRAILLE_Y[r]
                        d.rectangle((x, y, x + BRAILLE_DOT - 1, y + BRAILLE_DOT - 1), fill=px)
            elif rune != " ":
                ImageDraw.Draw(t).text((0, GLYPH_DY), rune, font=self.font, fill=em.color_rgb(fg), anchor="la")
            if len(self.tiles) > 20000:
                self.tiles.clear()
            self.tiles[key] = t
        return t

    def frame(self, cells):
        w, h = len(cells[0]), len(cells)
        im = self.Image.new("RGB", (w * CELL_W, h * CELL_H), (0, 0, 0))
        for y, row in enumerate(cells):
            key = tuple((c["r"], c["fg"], c["bg"]) for c in row)
            strip = self.rows.get(key)
            if strip is None:
                strip = self.Image.new("RGB", (w * CELL_W, CELL_H))
                for x, c in enumerate(key):
                    strip.paste(self.tile(*c), (x * CELL_W, 0))
                if len(self.rows) > 4000:
                    self.rows.clear()
                self.rows[key] = strip
            im.paste(strip, (0, y * CELL_H))
        return im


def encoded_frames(n_frames, rate, hold):
    """Frames actually in the encoded media: the sampled raster frames plus the tpad end hold (HOLD_S at the media rate)."""
    return n_frames + (int(HOLD_S * rate) if hold else 0)


def encode(frames_dir, n_frames, rate, hold, fmt, dest, env):
    """ffmpeg PNG sequence -> GIF or MP4 at the rational frame rate `rate`; returns the argv used."""
    pad = f"tpad=stop_mode=clone:stop_duration={HOLD_S}," if hold else ""
    inp = ["-framerate", f"{rate.numerator}/{rate.denominator}", "-i", str(Path(frames_dir) / "%05d.png")]
    if fmt == "gif":
        vf = pad + "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle"
        tail = ["-vf", vf, "-loop", "0", "-flags:v", "+bitexact", "-f", "gif"]
    else:
        vf = pad + "pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p"
        tail = ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-threads", "1", "-flags:v", "+bitexact",
                "-movflags", "+faststart", "-f", "mp4"]
    flags = FFMPEG_GLOBAL + inp + FFMPEG_OUTPUT + tail
    p = subprocess.run(["ffmpeg"] + flags + [str(dest)], capture_output=True, text=True, env=env)
    if p.returncode:
        raise Fail(EXIT_ENCODE, f"ffmpeg {fmt} failed (exit {p.returncode}): {p.stderr.strip()[-500:]}")
    return ["ffmpeg"] + [("<frames>/%05d.png" if a == inp[-1] else a) for a in flags] + ["<out>"]


# ---------------------------------------------------------------- orchestration

def rel_scene(path):
    p = Path(path).resolve()
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return p.name


def default_scenes():
    return [REPO / s for s in em.DEFAULT_SCENES]


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def run(args, export, factory=None, stdout=None, stderr=None):
    """Shared verify/export driver. factory(root, env, timings) -> {name: (cmd, manifest_cmd)} lets tests inject adapters;
    its commands are started as real Adapter subprocesses unless it returns ready adapter objects with manifest_cmd None."""
    out, err = stdout or sys.stdout, stderr or sys.stderr
    timings, t_run = {}, time.monotonic()
    root = Path(tempfile.mkdtemp(prefix="mdgl-e2e-"))
    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="mdgl-media-out-"))
    report_tpl = args.failure_report or str(Path(tempfile.mkdtemp(prefix="mdgl-e2e-report-")) / "example-media-failure-{scene}.json")
    adapters, rc = {}, EXIT_OK
    try:
        env = base_env()
        formats = [f for f in args.formats.split(",") if f] if export else []
        if any(f not in ("gif", "mp4") for f in formats) or (export and not formats):
            raise Fail(EXIT_USAGE, "--formats must be a comma list of gif,mp4")
        scenes = [Path(s) for s in args.scenes] if args.scenes else default_scenes()
        sources = []
        for p in scenes:
            try:
                sources.append((p, p.read_bytes()))
            except OSError as e:
                raise Fail(EXIT_SCENE, f"missing scene {p}: {e.strerror}")
        need_tools(env, export)
        versions = tool_versions(env, export)
        t0 = time.monotonic()
        built = (factory or build_all)(root, env, timings)
        timings["build_total"] = round(time.monotonic() - t0, 2)
        manifest_cmds = {}
        for n, spec in built.items():
            if isinstance(spec, tuple):
                adapters[n] = cr.Adapter(spec[0], str(root), 60.0)
                manifest_cmds[n] = spec[1]
            else:
                adapters[n], manifest_cmds[n] = spec, "<test adapter>"
        ras = Rasteriser() if export else None
        entries, frames_root = [], root / "frames"
        for path, raw in sources:
            name, source = path.stem, raw.decode("utf-8")
            fdir = frames_root / name
            state = {"n": 0, "t": 0.0}
            hdr = em.parse_header(source)
            step = max(1, math.ceil(hdr["fps"] / GIF_FPS_CAP))
            rate = Fraction(hdr["fps"], step)
            def sink(idx, t, resp, is_end, fdir=fdir, step=step, state=state):
                if ras and (idx % step == 0 or is_end):
                    fdir.mkdir(parents=True, exist_ok=True)
                    t1 = time.monotonic()
                    ras.frame(resp["cells"]).save(fdir / f"{state['n']:05d}.png", compress_level=1)
                    state["n"] += 1
                    state["t"] += time.monotonic() - t1
            t0 = time.monotonic()
            try:
                summ = compare_scene(name, source, adapters, sink)
            except Mismatch as m:
                rep = dict(m.report, scene_path=rel_scene(path), scene_sha256=hashlib.sha256(raw).hexdigest(),
                           adapter_commands=manifest_cmds)
                dest = report_tpl.replace("{scene}", name)
                write_json(dest, rep)
                err.write(str(m) + f"\nexample-media: failure report: {dest}\n")
                return EXIT_MISMATCH
            timings[f"compare_{name}"] = round(time.monotonic() - t0 - state["t"], 2)
            if ras:
                timings[f"raster_{name}"] = round(state["t"], 2)
            ent = {"scene": rel_scene(path), "scene_sha256": hashlib.sha256(raw).hexdigest(), **summ,
                   "frames_dir": fdir if ras else None, "raster_frames": state["n"], "raster_rate": rate}
            entries.append(ent)
            out.write(f"{name}: {summ['frames']} frames x 5 adapters identical (+ fallback), sequence {summ['sequence_sha256'][:16]}\n")
        for a in adapters.values():
            a.close()
        adapters.clear()
        manifest = {"manifest_version": 1, "note": NOTE, "adapters": manifest_cmds, "tools": versions, "scenes": []}
        if export:
            manifest["raster"] = {"font_file": FONT.name, "font_sha256": sha256_file(FONT), "font_px": FONT_PX,
                                  "cell_px": [CELL_W, CELL_H], "glyph_dy": GLYPH_DY, "gif_fps_cap": GIF_FPS_CAP,
                                  "hold_s_finite_scenes": HOLD_S, "braille": "drawn procedurally from U+2800 dot masks (2x4 dots per 8x16 cell); the pinned font is used for all other glyphs and labels",
                                  "braille_dot_px": BRAILLE_DOT, "braille_dot_x": list(BRAILLE_X), "braille_dot_y": list(BRAILLE_Y),
                                  "braille_bit_to_col_row": {str(k): list(v) for k, v in BRAILLE_BIT_POS.items()}, "palette": "play PALETTE; bg empty = black"}
            manifest["ffmpeg_flags_common"] = {"global": FFMPEG_GLOBAL, "output": FFMPEG_OUTPUT}
        final = root / "publish"
        final.mkdir()
        for ent in entries:
            fdir = ent.pop("frames_dir")
            rate = ent.pop("raster_rate")
            n = ent.pop("raster_frames")
            if export:
                ent["media"] = {}
                for fmt in formats:
                    t0 = time.monotonic()
                    dest = final / f"{Path(ent['scene']).stem}.{fmt}"
                    flags = encode(fdir, n, rate, ent["end_frame"], fmt, dest, env)
                    timings[f"encode_{Path(ent['scene']).stem}_{fmt}"] = round(time.monotonic() - t0, 2)
                    ent["media"][fmt] = {"file": dest.name, "sha256": sha256_file(dest), "bytes": dest.stat().st_size,
                                         "frames_in_media": encoded_frames(n, rate, ent["end_frame"]), "frames_sampled_pre_hold": n, "frame_rate": f"{rate.numerator}/{rate.denominator}", "ffmpeg_flags": flags}
                shutil.rmtree(fdir, ignore_errors=True)
            manifest["scenes"].append(ent)
        write_json(final / MANIFEST, manifest)
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(final.iterdir()):  # publish only now: every scene agreed and every encode succeeded
            shutil.copy2(f, out_dir / f.name)
        timings["total"] = round(time.monotonic() - t_run, 2)
        out.write(f"output: {out_dir}\n" + "timings_s: " + json.dumps(timings, sort_keys=True) + "\n")
        return EXIT_OK
    except Fail as e:
        err.write(f"example-media: {e.msg}\n")
        rc = e.code
    except Transport as e:
        err.write(f"example-media: adapter protocol/transport failure: {e}\n")
        rc = EXIT_PROTOCOL
    finally:
        for a in adapters.values():
            try:
                a.kill()
                for pipe in (a.p.stdin, a.p.stdout):
                    pipe.close()
            except Exception:
                pass
        if not getattr(args, "keep_stage", False):
            shutil.rmtree(root, ignore_errors=True)
    return rc


def add_parsers(sub):
    for name, text in (("verify", "build all five adapters in an isolated stage, check and compare every frame; write the manifest only"),
                       ("export", "verify, then (only if all five agree) rasterise and encode GIF/MP4 plus the manifest")):
        p = sub.add_parser(name, help=text, description=text + ".\n\n" + NOTE + "\n\nExit codes: 0 ok, 1 adapter disagreement "
                           "(first difference reported), 2 usage, 3 tool unavailable, 4 build failed, 5 protocol/transport failure, "
                           "6 invalid scene, 7 raster/encode failure. Needs go, cargo/rustc, cmake+cc, node/npm (npm ci needs the "
                           "npm registry or a warm cache), python3; export also needs Pillow, ffmpeg and DejaVuSansMono.ttf.",
                           formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
        p.add_argument("scenes", nargs="*", metavar="SCENE.mdgl", help="default: " + ", ".join(em.DEFAULT_SCENES))
        p.add_argument("--out", metavar="DIR", help="output directory (default: a new temp dir, printed); media and manifest are "
                       "copied there only after every scene agreed" + ("" if name == "export" else "; verify writes the manifest only"))
        p.add_argument("--failure-report", metavar="FILE", help="JSON report on a disagreement ({scene} expands; default a fresh temp dir, path printed on failure)")
        p.add_argument("--keep-stage", action="store_true", help="keep the temp stage root (sources, builds, caches)")
        if name == "export":
            p.add_argument("--formats", default="gif,mp4", help="comma list of gif,mp4 (default gif,mp4)")
        p.set_defaults(func=(lambda a, **h: run(a, False, **h)) if name == "verify" else (lambda a, **h: run(a, True, **h)))
        if name == "verify":
            p.set_defaults(formats="")

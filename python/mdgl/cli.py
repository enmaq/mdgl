"""Command line: mdgl check FILE | frames FILE [--at T,...] | play FILE.

Exit codes: 0 ok, 1 invalid scene or output error, 2 usage or unreadable file, 130 interrupted (Ctrl+C).
`play` animates only on a TTY; redirected output, NO_COLOR or MDGL_REDUCED_MOTION (non-empty) print the
fallback frame once, with no timer and no escape sequences.
"""
import argparse
import os
import sys

from . import MdglError, __version__, compile
from .player import plain_lines, play

MAX_INPUT = 256 * 1024


def _parser():
    p = argparse.ArgumentParser(prog="mdgl", description="MDGL terminal tool (development tree).",
                                epilog="exit: 0 ok, 1 invalid scene or output error, 2 usage/unreadable file, 130 Ctrl+C")
    p.add_argument("--version", action="version", version="mdgl " + __version__)
    sub = p.add_subparsers(dest="command", required=True, metavar="{check,frames,play}")
    sub.add_parser("check", help="validate FILE").add_argument("file")
    f = sub.add_parser("frames", help="print frames at given times")
    f.add_argument("file")
    f.add_argument("--at", default="0", help="comma-separated seconds (default 0)")
    sub.add_parser("play", help="animate FILE in the terminal (fallback frame if not a TTY)").add_argument("file")
    return p


def _load(path, err):
    try:
        with open(path, "rb") as h:
            data = h.read(MAX_INPUT + 1)
    except OSError as e:
        print("mdgl: cannot read %s: %s" % (os.path.basename(path), e.strerror or e), file=err)
        return None, 2
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        print("%s:1:1: input is not UTF-8" % os.path.basename(path), file=err)
        return None, 1
    try:
        return compile(source), 0
    except MdglError as e:
        print("%s:%d:%d: %s" % (os.path.basename(path), e.line, e.col, e.message), file=err)
        return None, 1


def _animate_allowed(out):
    return (out.isatty() and not os.environ.get("NO_COLOR") and not os.environ.get("MDGL_REDUCED_MOTION"))


def main(argv=None, out=None, err=None, clock=None, sleep=None):
    out, err = out or sys.stdout, err or sys.stderr
    args = _parser().parse_args(argv)
    scene, code = _load(args.file, err)
    if scene is None:
        return code
    try:
        if args.command == "check":
            print("OK MDGL 0.1", file=out)
        elif args.command == "frames":
            times = []
            for item in args.at.split(","):
                try:
                    t = float(item.strip().removesuffix("s"))
                except ValueError:
                    t = -1.0
                if not (0 <= t <= 1e12):
                    print("mdgl: invalid frame time %r" % item, file=err)
                    return 2
                times.append(t)
            for t in times:
                print("@%g" % t, file=out)
                print("\n".join(plain_lines(scene.frame(t))), file=out)
        elif not _animate_allowed(out):
            print("\n".join(plain_lines(scene.fallback_frame())), file=out)
        else:
            kw = {k: v for k, v in (("clock", clock), ("sleep", sleep)) if v}
            play(scene, out.write, out.flush, **kw)
        out.flush()
    except KeyboardInterrupt:
        return 130
    except OSError as e:
        try:
            print("mdgl: output error: %s" % (e.strerror or e), file=err)
        except OSError:
            pass
        return 1
    return 0


def run():
    sys.exit(main())

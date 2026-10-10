#!/usr/bin/env python3
"""Render one frame of an MDGL scene as text.

    python examples/render.py [FILE] [--time SECONDS | --fallback]

FILE defaults to ../../examples/text.mdgl in a repository checkout. Needs the development
`mdgl` package (see the README); the published PyPI 0.2.0 does not include this API.
"""
import argparse
import sys
from pathlib import Path

import mdgl

DEFAULT = Path(__file__).resolve().parents[2] / "examples" / "text.mdgl"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render one MDGL frame to the terminal as text.")
    ap.add_argument("file", nargs="?", type=Path, default=DEFAULT, help="scene file (default: shared text.mdgl)")
    when = ap.add_mutually_exclusive_group()
    when.add_argument("--time", type=float, default=0.0, metavar="SECONDS", help="seek to this time (default 0)")
    when.add_argument("--fallback", action="store_true", help="show the scene's fallback frame")
    args = ap.parse_args(argv)
    try:
        source = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print("error: cannot read %s: %s" % (args.file.name, e.strerror or e), file=sys.stderr)
        return 2
    try:
        scene = mdgl.compile(source)
    except mdgl.MdglError as e:
        print("%s:%d:%d: %s" % (args.file.name, e.line, e.col, e.message), file=sys.stderr)
        return 1
    if args.fallback:
        frame = scene.fallback_frame()
    elif args.time < 0 or args.time != args.time or args.time == float("inf"):
        print("error: --time must be a finite number >= 0", file=sys.stderr)
        return 2
    else:
        frame = scene.frame_ns(round(args.time * 1e9))
    print("\n".join(line.rstrip() for line in frame.lines()))
    print("-- %dx%d, %s, done=%s" % (scene.width, scene.height, "fallback" if args.fallback else "t=%gs" % args.time, frame.done),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

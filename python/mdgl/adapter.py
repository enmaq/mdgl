"""NDJSON conformance adapter (protocol v1, conformance/PROTOCOL.md): python3 -m mdgl.adapter."""
import json
import sys
from decimal import Decimal

from . import check
from .animation import Animation
from .model import MdglError

MAX_LINE = 2097152
MAX_TIME_NS = 2 ** 53 - 1


class _Bad(Exception):
    def __init__(self, message, code="bad_request"):
        super().__init__(message)
        self.code = code


def _reject(name):
    raise ValueError("non-finite number " + name)


def _int(value, lo, hi, name):
    """Mathematical integer (1.0 and 1e9 accepted, 1.5 and 2^53-1+0.1 rejected) within lo..hi."""
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise _Bad("%s must be an integer in %d..%d" % (name, lo, hi))
    if not (lo <= value <= hi) or (isinstance(value, Decimal) and value != value.to_integral_value()):
        raise _Bad("%s must be an integer in %d..%d" % (name, lo, hi))
    return int(value)


def _no_surrogate(s):
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise _Bad("source contains a lone surrogate")


def _error(rid, code, message, diagnostics=None):
    err = {"code": code, "message": message}
    if diagnostics is not None:
        err["diagnostics"] = diagnostics
    return {"v": 1, "id": rid, "ok": False, "error": err}


def _cells(frame):
    return [[{"r": c.rune, "fg": c.color, "bg": c.background} for c in row] for row in frame.cells]


def handle(raw):
    """Process one request line (bytes without the newline); returns the response object."""
    rid = None
    try:
        if len(raw) > MAX_LINE:
            raise _Bad("request line exceeds %d bytes" % MAX_LINE)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _Bad("request is not UTF-8")
        if not text.strip(" \t\r"):
            raise _Bad("blank request line")
        try:
            req = json.loads(text, parse_float=Decimal, parse_constant=_reject)
        except (ValueError, RecursionError) as e:
            raise _Bad("malformed JSON: %s" % e)
        if not isinstance(req, dict):
            raise _Bad("request must be a JSON object")
        if isinstance(req.get("id"), str):
            rid = req["id"]
        v = req.get("v")
        if isinstance(v, bool) or not isinstance(v, (int, Decimal)) or (isinstance(v, Decimal) and v != v.to_integral_value()):
            raise _Bad("v must be an integer")
        if v != 1:
            raise _Bad("protocol version %s is not supported" % v, "unsupported_version")
        if rid is None:
            raise _Bad("id must be a string")
        op = req.get("op")
        if op not in ("check", "frame"):
            raise _Bad("op must be check or frame")
        source = req.get("source")
        if not isinstance(source, str):
            raise _Bad("source must be a string")
        _no_surrogate(source)
        if op == "check":
            return {"v": 1, "id": rid, "ok": True, "diagnostics": check(source)}
        fallback = req.get("fallback", False)
        if not isinstance(fallback, bool):
            raise _Bad("fallback must be a boolean")
        width = _int(req.get("width"), 1, 200, "width")
        height = _int(req.get("height"), 1, 60, "height")
        nanos = 0 if fallback else _int(req.get("time_ns"), 0, MAX_TIME_NS, "time_ns")
        try:
            anim = Animation(source)
        except MdglError as e:
            return _error(rid, "invalid_source", "source has diagnostics", [e.diagnostic])
        if fallback:
            frame = anim.fallback_frame(width, height)
        else:
            frame = anim.frame_ns(nanos, width, height)
        out = {"v": 1, "id": rid, "ok": True, "width": len(frame.cells[0]) if frame.cells else 0,
               "height": len(frame.cells), "cells": _cells(frame)}
        if not fallback:
            out["done"] = frame.done
        return out
    except _Bad as e:
        return _error(rid, e.code, str(e))
    except Exception as e:  # keep serving after an adapter bug
        return _error(rid, "internal", "%s: %s" % (type(e).__name__, e))


def main(stdin=None, stdout=None):
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    while True:
        line = stdin.readline(MAX_LINE + 2)
        if not line:
            return 0
        if line.endswith(b"\n"):
            raw = line[:-1]
        elif len(line) == MAX_LINE + 2:
            while line and not line.endswith(b"\n"):
                line = stdin.readline(1 << 16)
            raw = b"x" * (MAX_LINE + 1)
        else:
            raw = line  # final nonempty line without newline: answered once
        resp = handle(raw)
        stdout.write(json.dumps(resp, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n")
        stdout.flush()


if __name__ == "__main__":
    sys.exit(main())

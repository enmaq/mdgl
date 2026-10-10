#!/usr/bin/env python3
"""Transport tests for mdgl_adapter: python3 test_adapter.py PATH_TO_ADAPTER (stdlib only)."""
import json, subprocess, sys

BIN = sys.argv[1]
SRC = "scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n"
fails = 0

def run(data):
    p = subprocess.run([BIN], input=data, capture_output=True, timeout=30)
    return p.returncode, p.stdout

def one(name, line, check, raw=False):
    global fails
    rc, out = run(line if raw else line.encode() + b"\n")
    ok = rc == 0 and out.endswith(b"\n") and out.count(b"\n") == 1
    try:
        r = json.loads(out)
        ok = ok and check(r)
    except Exception as e:
        ok = False
    if not ok:
        fails += 1
        print("FAIL", name, rc, out[:200])

def frame(extra, src=SRC, **kw):
    d = {"v": 1, "id": "i", "op": "frame", "source": src, "width": 8, "height": 1}
    d.update(extra)
    return json.dumps(d)

def err(code):
    return lambda r: r.get("ok") is False and r["error"]["code"] == code
def bad(r): return err("bad_request")(r)

# exact numbers
one("1.0 ok", frame({"time_ns": 1.0}).replace('"time_ns": 1.0', '"time_ns": 1.0'), lambda r: r["ok"] and r["done"] is False)
for lex in ["1.0", "1e9", "1E9", "0", "-0", "-0.0", "0e5", "1000000000.000", "9007199254740991", "9.007199254740991e15"]:
    line = '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":%s,"width":8,"height":1}' % lex
    one("accept " + lex, line, lambda r: r["ok"] is True and r["done"] is True)
for lex in ["9007199254740991.1", "9007199254740992", "1.5", "-1", "-0.1", "1e400", "1e-1", "true", '"1"', "null", "[1]", "9007199254740991.0000001", "1e99999999999999"]:
    line = '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":%s,"width":8,"height":1}' % lex
    one("reject " + lex, line, bad)
one("90071992547409910e-1 is 2^53-1", '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":90071992547409910e-1,"width":8,"height":1}', lambda r: r["ok"] is True)
for lex in ["8.0", "8e0"]:
    one("width " + lex, '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":0,"width":%s,"height":1}' % lex, lambda r: r["ok"] is True)
for w, h in [("0", "1"), ("201", "1"), ("8", "61"), ("8.5", "1"), ('"8"', "1"), ("true", "1")]:
    one("size %s %s" % (w, h), '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":0,"width":%s,"height":%s}' % (w, h), bad)

# lossless exact integers: long digit/zero runs (bounded by the 2 MiB line cap)
def tl(lex): return '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":%s,"width":8,"height":1}' % lex
Z = "0" * 100
for lex in ["5." + Z, "5.0e0" + "", "9007199254740991." + Z, "9007199254740991." + "0" * 100000, "0." + Z + "e0", "0e-100000", "-0." + Z, "50e-1", "5" + Z + "e-100",
            "0." + Z + "5e" + str(101), "0.000" + "5e3", "1" + "0" * 15 + "e-15", "9007199254740991e0", "90071992547409910" + Z + "e-" + str(101)]:
    pass
for lex, good in [("5." + Z, 1), ("9007199254740991." + Z, 1), ("9007199254740991." + "0" * 100000, 1), ("0e-100000", 1), ("-0." + Z, 1), ("5" + Z + "e-100", 1),
                  ("0." + Z + "5e101", 1), ("1e-100000", 0), ("5." + Z + "1", 0), ("9007199254740991." + Z + "1", 0), ("9007199254740991." + "0" * 100000 + "1", 0),
                  ("0." + Z + "1e100", 0), ("1" + "0" * 40 + "e-39", 1), ("1" + "0" * 40 + "e-42", 0), ("90071992547409910" + Z + "e-" + str(101), 1), ("90071992547409920" + Z + "e-" + str(101), 0),
                  ("1e1000000000000", 0), ("1e999999999", 0), ("1e100000000", 0), ("1e99999999", 0), ("0e999999999", 1), ("5e-99999999", 0), ("5e-999999999", 0), ("0.5e999999999", 0), ("5e-1000000000000", 0), ("5." + "0" * 1000000 + "e0", 1)]:
    one(("lossless accept " if good else "lossless reject ") + lex[:30] + "..." + str(len(lex)), tl(lex), (lambda r: r["ok"] is True) if good else bad)
# v and size use the same exact rule
one("v long zeros", '{"v":1.' + Z + ',"id":"x","op":"check","source":""}', lambda r: r["ok"] is True)
one("v long zeros plus 1", '{"v":1.' + Z + '1,"id":"x","op":"check","source":""}', bad)
one("width long zeros", '{"v":1,"id":"n","op":"frame","source":"scene width=8 height=1 fallback=end\\n","time_ns":0,"width":8.' + Z + ',"height":1}', lambda r: r["ok"] is True)
# versions
one("v2", '{"v":2,"id":"e8","op":"check","source":""}', lambda r: err("unsupported_version")(r) and r["id"] == "e8")
one("v 1.0", '{"v":1.0,"id":"x","op":"check","source":""}', lambda r: r["ok"] is True)
one("v string", '{"v":"1","id":"x","op":"check","source":""}', bad)
one("v missing", '{"id":"x","op":"check","source":""}', bad)
one("v 0", '{"v":0,"id":"x","op":"check","source":""}', err("unsupported_version"))
one("v -1e0", '{"v":-1e0,"id":"x","op":"check","source":""}', err("unsupported_version"))
# fields
one("unknown op", '{"v":1,"id":"x","op":"nope","source":""}', bad)
one("no id", '{"v":1,"op":"check","source":""}', lambda r: bad(r) and r["id"] is None)
one("id number", '{"v":1,"id":5,"op":"check","source":""}', lambda r: bad(r) and r["id"] is None)
one("source number", '{"v":1,"id":"x","op":"check","source":1}', lambda r: bad(r) and r["id"] == "x")
one("unknown fields ignored", '{"v":1,"id":"x","op":"check","source":"","extra":{"a":[1,{"b":null}],"c":"\\ud800"},"z":1e999}', lambda r: r["ok"] is True)
one("check ignores time", '{"v":1,"id":"x","op":"check","source":"","time_ns":"junk","width":0,"fallback":5}', lambda r: r["ok"] is True)
one("frame fallback ignores time", frame({"fallback": True, "time_ns": "junk"}), lambda r: r["ok"] and "done" not in r)
one("frame fallback false needs time", frame({"fallback": False}), bad)
one("frame no time", frame({}), bad)
one("fallback not bool", frame({"fallback": 1, "time_ns": 0}), bad)
one("done omitted on fallback", frame({"fallback": True}), lambda r: r["ok"] and "done" not in r and r["cells"][0][0]["fg"] == "normal")
one("done present", frame({"time_ns": 0}), lambda r: r["ok"] and r["done"] is False)
one("done true at P", frame({"time_ns": 2000000000}), lambda r: r["ok"] and r["done"] is True and r["cells"][0][0]["r"] == "A")
one("blend", frame({"time_ns": 1000000000}), lambda r: r["cells"][0][0]["fg"] == "#808080" and r["cells"][0][2]["bg"] == "")
one("invalid_source", frame({"time_ns": 0}, src=""), lambda r: err("invalid_source")(r) and r["error"]["diagnostics"][0] == {"line": 1, "col": 1, "message": "missing scene"})
one("check byte col", json.dumps({"v": 1, "id": "e2", "op": "check", "source": 'scene width=8 height=1 fallback=end\nactor a = text("é") $\n'}), lambda r: r["diagnostics"] == [{"line": 2, "col": 22, "message": 'unexpected character "$"'}])
one("clamp", frame({"time_ns": 0, "width": 200, "height": 60}), lambda r: r["width"] == 8 and r["height"] == 1)
# syntax
for name, line in [("not json", "nope"), ("array", "[]"), ("trailing", '{"v":1} x'), ("trailing comma", '{"v":1,}'), ("single quote", "{'v':1}"), ("NaN", '{"v":NaN}'),
                   ("Infinity", '{"time_ns":Infinity}'), ("leading zero", '{"v":01}'), ("bare dot", '{"v":1.}'), ("raw control", '{"v":1,"id":"a\tb"}'),
                   ("bad escape", '{"v":1,"id":"a\\qb"}'), ("short u", '{"v":1,"id":"\\u12"}'), ("unterminated", '{"v":1,"id":"abc'), ("empty", ""), ("ws only", "   \t "),
                   ("deep", "[" * 300 + "]" * 300), ("deep field", '{"v":1,"x":' + "[" * 300 + "]" * 300 + "}")]:
    one("syntax " + name, line, lambda r: bad(r) and r["id"] is None)
one("lone high surrogate source", '{"v":1,"id":"x","op":"check","source":"a\\ud800b"}', lambda r: bad(r) and r["id"] == "x")
one("lone low surrogate source", '{"v":1,"id":"x","op":"check","source":"\\udc00"}', bad)
one("pair ok", '{"v":1,"id":"x","op":"check","source":"# \\ud83d\\ude00\\nscene\\n"}', lambda r: r["ok"] is True)
one("invalid utf8 raw", b'{"v":1,"id":"x","op":"check","source":"\xff"}\n', lambda r: bad(r), raw=True)
one("overlong utf8", b'{"v":1,"id":"x","op":"check","source":"\xc0\xaf"}\n', bad, raw=True)
one("surrogate utf8", b'{"v":1,"id":"x","op":"check","source":"\xed\xa0\x80"}\n', bad, raw=True)
one("raw utf8 ok", '{"v":1,"id":"é","op":"check","source":"# é"}'.encode() + b"\n", lambda r: r["id"] == "é", raw=True)
one("NUL in source", '{"v":1,"id":"x","op":"check","source":"scene\\u0000"}', lambda r: r["ok"] is True and r["diagnostics"][0]["line"] == 1)
one("id escaping roundtrip", '{"v":1,"id":"a\\"\\\\\\n\\u0001/","op":"check","source":""}', lambda r: r["id"] == 'a"\\\n\x01/')
# EOF and framing
rc, out = run(b'{"v":1,"id":"a","op":"check","source":""}')
if rc != 0 or out.count(b"\n") != 1 or not out.endswith(b"\n"): fails += 1; print("FAIL eof final line", rc, out)
rc, out = run(b'{"v":1,"id":"a","op":"check","source":""}\n\n{"v":1,"id":"b","op":"check","source":""}\n')
lines = out.split(b"\n")
if rc != 0 or len(lines) != 4 or json.loads(lines[1])["error"]["code"] != "bad_request" or json.loads(lines[2])["id"] != "b": fails += 1; print("FAIL blank line", out)
rc, out = run(b"")
if rc != 0 or out != b"": fails += 1; print("FAIL empty stdin")
rc, out = run(b'{"v":1,"id":"a","op":"check","source":""}\r\n')
if rc != 0 or json.loads(out)["ok"] is not True: fails += 1; print("FAIL CRLF")
# sizes
PRE = b'{"v":1,"id":"x","op":"check","source":"'
big = PRE + b"a" * (2097152 - len(PRE) - 2) + b'"}'
assert len(big) <= 2097152
rc, out = run(big + b"\n")
r = json.loads(out)
if rc != 0 or r["ok"] is not True: fails += 1; print("FAIL cap line", out[:100])
over = b'{"v":1,"id":"x","op":"check","source":"' + b"a" * 2097152 + b'"}'
rc, out = run(over + b'\n{"v":1,"id":"after","op":"check","source":""}\n')
ls = out.split(b"\n")
if rc != 0 or json.loads(ls[0])["error"]["code"] != "bad_request" or json.loads(ls[1])["id"] != "after": fails += 1; print("FAIL oversize", out[:150])
rc, out = run(over)  # oversize at EOF without newline
if rc != 0 or json.loads(out)["error"]["code"] != "bad_request": fails += 1; print("FAIL oversize eof")
# purity
a = run((frame({"time_ns": 1234567}) + "\n").encode() * 2)[1].split(b"\n")
if a[0] != a[1]: fails += 1; print("FAIL purity")
print("adapter transport tests:", "OK" if not fails else "%d FAILED" % fails)
sys.exit(1 if fails else 0)

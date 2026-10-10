#!/usr/bin/env python3
"""TEST DOUBLE ONLY - this is NOT an MDGL implementation. It replays canned JSON responses to test the runner.

  mock_adapter.py SCRIPT.json

SCRIPT.json: {"by_id": {"r3": RESP}, "by_key": {"frame:1000000000": RESP | [RESP, ...], "frame:fallback": ..,
              "check:<exact source>": ..}, "default": RESP, "log": "requests.jsonl", "exit_after": N}
A list value serves successive responses (the last repeats). RESP is an object (v and id are filled in from the
request unless present) or contains one special key:
  "_raw": "text"   write this line verbatim (e.g. malformed JSON)
  "_id": X         override the echoed id (wrong-id mode)
  "_hang": true    never answer (sleep)
  "_delay": S      sleep S seconds, then answer
  "_exit": true    exit immediately without answering
Script-level transport modes (all test double only):
  "unterminated_at": N   write the N-th served response without LF and exit 0
  "extra_after": N       after the N-th served response also write one extra unsolicited response line
  "extra_at_eof": true   after stdin EOF write one extra response line, then exit
  "exit_code_at_eof": C  exit with status C after stdin EOF
  "hang_at_eof": true    after stdin EOF never exit (sleep)
With no match and no default it answers an `internal` error.
"""
import json, sys, time


def main():
    script = json.load(open(sys.argv[1], encoding="utf-8"))
    counters, served = {}, 0
    log = open(script["log"], "a", encoding="utf-8") if script.get("log") else None
    for line in sys.stdin.buffer:  # a final line without "\n" is still a request; EOF ends with exit 0
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError
        except ValueError:  # includes blank lines: bad_request, id null (PROTOCOL 1)
            sys.stdout.write(json.dumps({"v": 1, "id": None, "ok": False, "error": {"code": "bad_request", "message": "mock: malformed line"}}) + "\n")
            sys.stdout.flush()
            continue
        if log:
            log.write(json.dumps(req, ensure_ascii=False) + "\n")
            log.flush()
        key = "check:" + req["source"] if req.get("op") == "check" else \
            "frame:fallback" if req.get("fallback") is True else f"frame:{req.get('time_ns')}"
        resp = script.get("by_id", {}).get(req["id"], script.get("by_key", {}).get(key, script.get("default")))
        if isinstance(resp, list):
            n = counters.get(key, 0)
            counters[key] = n + 1
            resp = resp[min(n, len(resp) - 1)]
        if resp is None:
            resp = {"ok": False, "error": {"code": "internal", "message": "mock: no canned response for " + key[:60]}}
        resp = dict(resp)
        if resp.pop("_exit", False) or (script.get("exit_after") is not None and served >= script["exit_after"]):
            sys.exit(3)
        if resp.pop("_hang", False):
            time.sleep(3600)
        time.sleep(resp.pop("_delay", 0))
        raw = resp.pop("_raw", None)
        if raw is None:
            resp.setdefault("v", 1)
            resp["id"] = resp.pop("_id") if "_id" in resp else resp.get("id", req["id"])
            raw = json.dumps(resp, ensure_ascii=False)
        served += 1
        if script.get("unterminated_at") == served:
            sys.stdout.write(raw)
            sys.stdout.flush()
            sys.exit(0)
        sys.stdout.write(raw + "\n")
        if script.get("extra_after") == served:
            sys.stdout.write(json.dumps({"v": 1, "id": "extra", "ok": True, "diagnostics": []}) + "\n")
        sys.stdout.flush()
    if script.get("extra_at_eof"):
        sys.stdout.write(json.dumps({"v": 1, "id": "extra", "ok": True, "diagnostics": []}) + "\n")
        sys.stdout.flush()
    if script.get("hang_at_eof"):
        time.sleep(3600)
    sys.exit(script.get("exit_code_at_eof", 0))


if __name__ == "__main__":
    main()

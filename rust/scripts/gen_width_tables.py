#!/usr/bin/env python3
"""Regenerate src/width_tables.rs.

usage: gen_width_tables.py UNISEG_V0_4_7_DIR MARKS_TXT > src/width_tables.rs
  UNISEG_V0_4_7_DIR  checkout of github.com/rivo/uniseg at tag v0.4.7 (Unicode 15.0.0)
  MARKS_TXT          output of `go run ./marks` (Go >= 1.21 whose unicode.Version is 15.0.0)
"""
import re
import sys

src, marks_path = sys.argv[1].rstrip("/") + "/", sys.argv[2]


def rows(name):
    text = open(src + name).read()
    return [(int(a, 16), int(b, 16), c) for a, b, c in re.findall(r"\{0x([0-9A-Fa-f]+), 0x([0-9A-Fa-f]+), (pr\w+)\}", text)]


GB = {"prControl": 0, "prCR": 1, "prLF": 2, "prExtend": 3, "prZWJ": 4, "prRegionalIndicator": 5, "prExtendedPictographic": 6,
      "prSpacingMark": 7, "prPrepend": 8, "prL": 9, "prV": 10, "prT": 11, "prLV": 12, "prLVT": 13}
EAW = {"prW": "W", "prF": "F", "prA": "A"}
marks = [tuple(int(x, 16) for x in line.split()) for line in open(marks_path) if not line.startswith("//")]


def table(name, items, ty):
    body = "".join(f"    (0x{a:X}, 0x{b:X}, {c}),\n" for a, b, c in items)
    return f"pub static {name}: &[(u32, u32, {ty})] = &[\n{body}];\n\n"


out = """//! Generated tables for Go-compatible cell glyph selection. DO NOT EDIT BY HAND.
//!
//! Sources: github.com/rivo/uniseg v0.4.7 (MIT, Copyright (c) 2019 Oliver Kuederle; full licence in
//! LICENSE-UNISEG) property tables, derived from Unicode 15.0.0 GraphemeBreakProperty.txt, emoji-data.txt
//! (Extended_Pictographic, Emoji_Presentation) and EastAsianWidth.txt; General_Category M* ranges from the
//! Go standard library `unicode` package (Unicode 15.0.0). Unicode data: https://www.unicode.org/license.html
//! Regenerate with scripts/gen_width_tables.py (see scripts/README.md).
#![allow(clippy::unreadable_literal, dead_code)]

"""
out += "".join(f"pub const {n}: u8 = {v};\n" for n, v in [("GB_OTHER", 255)] + [(k[2:].upper(), v) for k, v in GB.items()]) + "\n"
out += table("GRAPHEME", [(a, b, GB[c]) for a, b, c in rows("graphemeproperties.go") if c in GB], "u8")
out += table("EAST_ASIAN", [(a, b, "b'%s'" % EAW[c]) for a, b, c in rows("eastasianwidth.go") if c in EAW], "u8")
out += "pub static EMOJI_PRESENTATION: &[(u32, u32)] = &[\n" + "".join(f"    (0x{a:X}, 0x{b:X}),\n" for a, b, _ in rows("emojipresentation.go")) + "];\n\n"
out += "pub static MARKS: &[(u32, u32)] = &[\n" + "".join(f"    (0x{a:X}, 0x{b:X}),\n" for a, b in marks) + "];\n"
sys.stdout.write(out)

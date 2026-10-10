"""Extended grapheme clusters (UAX #29) and terminal cell width, Unicode 15.0.0.

Reference compatibility profile: the Go reference implementation uses rivo/uniseg v0.4.7 (Unicode 15.0.0,
rules GB1-GB13 without the Unicode 15.1 GB9c conjunct rule). This module reproduces that behavior from
the generated tables in _unicode15.py. The Unicode version is a compatibility profile of this
implementation, not a normative MDGL requirement.
"""
from bisect import bisect_right
from ._unicode15 import EAST_ASIAN_WIDTH, EMOJI_PRESENTATION, GRAPHEME

_G = ([r[0] for r in GRAPHEME], GRAPHEME)
_E = ([r[0] for r in EMOJI_PRESENTATION], EMOJI_PRESENTATION)
_W = ([r[0] for r in EAST_ASIAN_WIDTH], EAST_ASIAN_WIDTH)
UNICODE_VERSION = "15.0.0"

_ANY, _CR, _CTRL, _L, _LVV, _LVTT, _PREPEND, _EP, _EPZWJ, _RIODD, _RIEVEN = range(11)
_B, _N = True, False
# (state, property) -> (new state, boundary before this rune, rule); None property = any.
_T = {
    (_ANY, "CR"): (_CR, _B, 50), (_ANY, "LF"): (_CTRL, _B, 50), (_ANY, "Control"): (_CTRL, _B, 50),
    (_CR, None): (_ANY, _B, 40), (_CTRL, None): (_ANY, _B, 40), (_CR, "LF"): (_CTRL, _N, 30),
    (_ANY, "L"): (_L, _B, 9990), (_L, "L"): (_L, _N, 60), (_L, "V"): (_LVV, _N, 60),
    (_L, "LV"): (_LVV, _N, 60), (_L, "LVT"): (_LVTT, _N, 60),
    (_ANY, "LV"): (_LVV, _B, 9990), (_ANY, "V"): (_LVV, _B, 9990),
    (_LVV, "V"): (_LVV, _N, 70), (_LVV, "T"): (_LVTT, _N, 70),
    (_ANY, "LVT"): (_LVTT, _B, 9990), (_ANY, "T"): (_LVTT, _B, 9990), (_LVTT, "T"): (_LVTT, _N, 80),
    (_ANY, "Extend"): (_ANY, _N, 90), (_ANY, "ZWJ"): (_ANY, _N, 90),
    (_ANY, "SpacingMark"): (_ANY, _N, 91),
    (_ANY, "Prepend"): (_PREPEND, _B, 9990), (_PREPEND, None): (_ANY, _N, 92),
    (_ANY, "ExtendedPictographic"): (_EP, _B, 9990), (_EP, "Extend"): (_EP, _N, 110),
    (_EP, "ZWJ"): (_EPZWJ, _N, 110), (_EPZWJ, "ExtendedPictographic"): (_EP, _N, 110),
    (_ANY, "RegionalIndicator"): (_RIODD, _B, 9990), (_RIODD, "RegionalIndicator"): (_RIEVEN, _N, 120),
    (_RIEVEN, "RegionalIndicator"): (_RIODD, _B, 120),
}


def _prop(table, cp, default):
    starts, rows = table
    i = bisect_right(starts, cp) - 1
    if i >= 0 and cp <= rows[i][1]:
        return rows[i][2]
    return default


def grapheme_property(cp):
    if 0x20 <= cp <= 0x7E:
        return "Any"
    if cp == 0x0A:
        return "LF"
    if cp == 0x0D:
        return "CR"
    if cp <= 0x1F or cp == 0x7F:
        return "Control"
    return _prop(_G, cp, "Any")


def _transition(state, prop):
    t = _T.get((state, prop))
    if t:
        return t[0], prop, t[1]
    a = _T.get((state, None))
    b = _T.get((_ANY, prop))
    if a and b:
        return b[0], prop, (a[1] if a[2] < b[2] else b[1])
    if a:
        return a[0], prop, a[1]
    if b:
        return b[0], prop, b[1]
    return _ANY, prop, True


def _rune_width(cp, prop):
    if prop in ("Control", "CR", "LF", "Extend", "ZWJ"):
        return 0
    if prop == "RegionalIndicator":
        return 2
    if prop == "ExtendedPictographic":
        return 2 if _prop(_E, cp, "") == "EmojiPresentation" else 1
    if cp == 0x2E3A:
        return 3
    if cp == 0x2E3B:
        return 4
    if 0x20 <= cp <= 0x7E:
        return 1
    if cp <= 0x1F or cp == 0x7F:
        return 1
    ea = _prop(_W, cp, "")
    return 2 if ea in ("W", "F") else 1


def clusters(text):
    """Yield (cluster_text, cell_width) for each extended grapheme cluster."""
    state, start, first_prop, width, first_cp = _ANY, 0, None, 0, 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        if i == 0:
            state, prop, _ = _transition(_ANY, grapheme_property(cp))
            first_prop, first_cp = prop, cp
            width = _rune_width(cp, prop)
            continue
        state, prop, boundary = _transition(state, grapheme_property(cp))
        if boundary:
            yield text[start:i], width
            start, first_prop, first_cp = i, prop, cp
            width = _rune_width(cp, prop)
            continue
        if first_prop == "ExtendedPictographic":
            if cp == 0xFE0E:
                width = 1
            elif cp == 0xFE0F:
                width = 2
        elif first_prop not in ("RegionalIndicator", "L"):
            width += _rune_width(cp, prop)
    if text:
        yield text[start:], width

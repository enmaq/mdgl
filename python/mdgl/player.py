"""Animated terminal playback (SPEC "Limits and API"): absolute elapsed time, dirty-cell diffs, DEC 2026."""
import math
import time
import unicodedata

HIDE = "\x1b[?25l"
SYNC_ON, SYNC_OFF = "\x1b[?2026h", "\x1b[?2026l"
RESTORE = SYNC_OFF + "\x1b[0m\x1b[?25h\n"
_NAMED = {"black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35,
          "cyan": 36, "accent": 36, "white": 37}


def safe_rune(r):
    """Cell content never reaches the terminal as a control sequence."""
    return " " if unicodedata.category(r) in ("Cc", "Cs") or r in "  \u0085" else r


def plain_lines(frame):
    return ["".join(safe_rune(c.rune) for c in row) for row in frame.cells]


def ansi_color(color, background):
    if background and color in ("", "normal"):
        color = "black"
    if len(color) == 7 and color[0] == "#":
        try:
            v = int(color[1:], 16)
            return "\x1b[%d;2;%d;%d;%dm" % (48 if background else 38, v >> 16, v >> 8 & 255, v & 255)
        except ValueError:
            pass
    return "\x1b[%dm" % (_NAMED.get(color, 39) + (10 if background else 0))


def dirty(previous, current):
    """ANSI for cells that differ (rune, fg, bg); empty string when nothing changed."""
    out = []
    for r, row in enumerate(current.cells):
        for c, cell in enumerate(row):
            if previous is not None and r < len(previous.cells) and c < len(previous.cells[r]) \
                    and cell == previous.cells[r][c]:
                continue
            out.append("\x1b[%d;%dH%s%s%s" % (r + 1, c + 1, ansi_color(cell.color, False),
                                              ansi_color(cell.background, True), safe_rune(cell.rune)))
    return (SYNC_ON + "".join(out) + SYNC_OFF) if out else ""


def play(animation, write, flush=lambda: None, clock=time.monotonic, sleep=time.sleep):
    """Play to completion (finite) or until interrupted; always restores the terminal.

    Frame time is clock() minus the start instant, never accumulated ticks, so dropped
    frames cannot change state. KeyboardInterrupt and write errors propagate after cleanup.
    """
    def emit(text):
        if text:
            write(text)
            flush()

    try:
        emit(HIDE)
        previous = animation.frame(0.0)
        emit(dirty(None, previous))
        if not animation.active(0):
            return
        start, step = clock(), 1.0 / animation.fps
        while True:
            elapsed = max(0.0, clock() - start)
            current = animation.frame(elapsed)
            emit(dirty(previous, current))
            previous = current
            if not animation.active(elapsed):
                return
            nxt = (math.floor(elapsed / step + 1e-9) + 1) * step
            sleep(max(0.0, nxt - (clock() - start)))
    finally:
        try:
            write(RESTORE)
            flush()
        except Exception:  # cleanup must not mask the original error
            pass

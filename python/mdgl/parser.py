"""Lexer and statement parser: source text -> source-located Scene."""
import re
from .model import Action, Actor, MdglError, Pos, Scene, Value, finite, parse_float

_ESC = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, '"': 34}
_SPACE = " \t\r"


def go_quote(s):
    """strconv.Quote."""
    out = ['"']
    for c in s:
        if c in '"\\':
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif c.isprintable():
            out.append(c)
        elif ord(c) < 0x80 or c == "\x7f":
            out.append("\\x%02x" % ord(c))
        elif ord(c) < 0x10000:
            out.append("\\u%04x" % ord(c))
        else:
            out.append("\\U%08x" % ord(c))
    out.append('"')
    return "".join(out)


def go_unquote(raw):
    """strconv.Unquote for a double-quoted literal; ValueError if invalid."""
    body, buf, i = raw[1:-1], bytearray(), 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            buf += c.encode("utf-8")
            i += 1
            continue
        i += 1
        if i >= len(body):
            raise ValueError
        e = body[i]
        i += 1
        if e in _ESC:
            buf.append(_ESC[e])
        elif e == "x":
            h = body[i:i + 2]
            if len(h) != 2 or not re.fullmatch("[0-9a-fA-F]{2}", h):
                raise ValueError
            buf.append(int(h, 16))
            i += 2
        elif e in "01234567":
            o = body[i - 1:i + 2]
            if len(o) != 3 or not re.fullmatch("[0-7]{3}", o) or int(o, 8) > 255:
                raise ValueError
            buf.append(int(o, 8))
            i += 2
        elif e in "uU":
            n = 4 if e == "u" else 8
            h = body[i:i + n]
            if len(h) != n or not re.fullmatch("[0-9a-fA-F]+", h):
                raise ValueError
            cp = int(h, 16)
            if cp > 0x10FFFF or 0xD800 <= cp < 0xE000:
                raise ValueError
            buf += chr(cp).encode("utf-8")
            i += n
        else:
            raise ValueError
    return buf.decode("utf-8", "replace")


def edit_distance(a, b):
    a, b = a.encode("utf-8"), b.encode("utf-8")
    row = list(range(len(b) + 1))
    for i in range(len(a)):
        diag, row[0] = row[0], i + 1
        for j in range(len(b)):
            saved = row[j + 1]
            row[j + 1] = min(row[j] + 1, row[j + 1] + 1, diag + (a[i] != b[j]))
            diag = saved
    return row[len(b)]


def unknown(kind, name, choices):
    best, dist = "", 3
    for c in choices:
        d = edit_distance(name, c)
        if d < dist or (d == dist and c < best):
            best, dist = c, d
    msg = "unknown %s %s" % (kind, go_quote(name))
    if dist <= 2:
        msg += "; did you mean %s?" % go_quote(best)
    return msg


class Token:
    __slots__ = ("text", "col", "quoted")

    def __init__(self, text, col, quoted=False):
        self.text, self.col, self.quoted = text, col, quoted


def _letter(c):
    return 97 <= c <= 122 or 65 <= c <= 90 or c == 95


def _digit(c):
    return 48 <= c <= 57


def is_identifier(s):
    b = s.encode("utf-8")
    return bool(b) and _letter(b[0]) and all(_letter(c) or _digit(c) for c in b)


def lex(line, pos):
    """Tokens of one line; columns are one-based UTF-8 byte offsets."""
    b = line.encode("utf-8")
    out, i, n = [], 0, len(b)
    while i < n:
        c = b[i]
        if c in b" \t\r":
            i += 1
            continue
        start = i
        if c == 34:
            i += 1
            closed = False
            while i < n:
                if b[i] == 92:
                    i += 2
                    continue
                if b[i] == 34:
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:
                raise MdglError(pos.line, start + 1, "unterminated string")
            try:
                value = go_unquote(b[start:i].decode("utf-8", "replace"))
            except ValueError:
                raise MdglError(pos.line, start + 1, "invalid string escape")
            out.append(Token(value, start + 1, True))
            continue
        if _digit(c) or (c == 46 and i + 1 < n and _digit(b[i + 1])):
            i += 1
            while i < n and (_digit(b[i]) or b[i] == 46):
                i += 1
            if b[i:i + 3] in (b"rad", b"deg"):
                i += 3
            elif i < n and b[i] in b"s%":
                i += 1
        elif _letter(c):
            i += 1
            while i < n and (_letter(b[i]) or _digit(b[i]) or b[i] == 45):
                i += 1
        elif c in b"=(),@:.+-":
            i += 1
        else:
            raise MdglError(pos.line, start + 1, "unexpected character " + go_quote(chr(c)))
        out.append(Token(b[start:i].decode("utf-8"), start + 1))
    return out


class _Reader:
    def __init__(self, tokens, pos):
        self.t, self.i, self.pos = tokens, 0, pos

    def end(self):
        return self.i >= len(self.t)

    def peek(self):
        return Token("<end>", self.pos.col) if self.end() else self.t[self.i]

    def take(self):
        cur = self.peek()
        if not self.end():
            self.i += 1
        return cur

    def failure(self, msg):
        return MdglError(self.pos.line, self.peek().col, msg)

    def want(self, text):
        p = self.peek()
        if p.text != text or p.quoted:
            raise self.failure("expected " + go_quote(text))
        self.take()

    def is_(self, text):
        p = self.peek()
        return not p.quoted and p.text == text

    def value(self):
        cur = self.take()
        if cur.quoted:
            return Value(cur.text, (), True)
        if cur.text == "<end>":
            raise self.failure("expected value")
        if cur.text == "(":
            first = self.value()
            self.want(",")
            pair = [first, self.value()]
            if self.peek().text == ",":
                self.take()
                pair.append(self.value())
            self.want(")")
            return Value(pair=tuple(pair))
        text = cur.text
        if text in ("+", "-", "@"):
            nxt = self.take()
            if nxt.text == "<end>":
                raise self.failure("expected value")
            text += nxt.text
        if self.peek().text in ("+", "-"):
            text += self.take().text + self.take().text
        if any(ch in text for ch in "=),:"):
            raise self.failure("expected value")
        return Value(text)

    def attributes(self):
        out = {}
        while not self.end():
            name = self.take()
            if name.quoted or not is_identifier(name.text):
                raise self.pos.error("expected attribute identifier")
            self.want("=")
            v = self.value()
            if name.text in out:
                raise self.pos.error("duplicate attribute " + name.text)
            out[name.text] = v
        return out

    def arguments(self):
        self.want("(")
        out, ordinal = {}, 0
        while not self.is_(")"):
            if self.end():
                raise self.failure('expected ")"')
            key = str(ordinal)
            ordinal += 1
            if self.i + 1 < len(self.t) and self.t[self.i + 1].text == "=":
                name = self.take()
                if name.quoted or not is_identifier(name.text):
                    raise self.pos.error("expected argument identifier")
                key = name.text
                self.take()
            v = self.value()
            if key in out:
                raise self.pos.error("duplicate argument " + key)
            out[key] = v
            if self.is_(")"):
                break
            self.want(",")
            if self.is_(")"):
                raise self.failure("trailing comma")
        self.take()
        return out


def _gostrip(s):
    bad = "\x1c\x1d\x1e\x1f"
    a, b = 0, len(s)
    while a < b and s[a].isspace() and s[a] not in bad:
        a += 1
    while b > a and s[b - 1].isspace() and s[b - 1] not in bad:
        b -= 1
    return s[a:b]


def parse(source):
    """Parse source text into a Scene (not yet checked). Raises MdglError."""
    if not isinstance(source, str):
        raise TypeError("mdgl.parse: source must be str")
    try:
        raw = source.encode("utf-8")
    except UnicodeEncodeError:
        raise MdglError(1, 1, "input is not UTF-8")
    if len(raw) > 256 * 1024:
        raise MdglError(1, 1, "input exceeds 256 KiB")
    scene = Scene()
    seen_scene = seen_action = seen_version = False
    for index, line in enumerate(source.split("\n")):
        pos = Pos(index + 1, 1)
        if len(line.encode("utf-8")) > 16384:
            raise pos.error("line exceeds 16 KiB")
        trimmed = _gostrip(line)
        if trimmed == "" or trimmed.startswith("#"):
            continue
        tokens = lex(line, pos)
        rd = _Reader(tokens, pos)
        head = rd.take()
        if head.quoted:
            raise pos.error("expected statement identifier")
        pos = Pos(pos.line, head.col)
        rd.pos = pos
        err = None
        h = head.text
        if h == "mdgl":
            version = rd.take()
            if seen_scene or seen_version or version.quoted or version.text != "0.1" or not rd.end():
                raise pos.error("expected initial mdgl 0.1")
            seen_version = True
        elif h == "scene":
            if seen_scene:
                raise pos.error("duplicate scene")
            scene.pos = pos
            try:
                scene.attr = rd.attributes()
            except MdglError as e:
                err = e
            seen_scene = True
        elif h == "actor":
            if not seen_scene:
                raise pos.error("scene must precede actors")
            if seen_action:
                raise pos.error("actors must precede actions")
            name = rd.take()
            if name.quoted or not is_identifier(name.text):
                raise pos.error("expected actor identifier")
            rd.want("=")
            kind = rd.take()
            if kind.quoted or not is_identifier(kind.text):
                raise pos.error("expected shape identifier")
            args = rd.arguments()
            rd.want("at")
            point = rd.value()
            if len(point.pair) != 2:
                raise pos.error("expected (x, y) position")
            attr = {}
            try:
                attr = rd.attributes()
            except MdglError as e:
                err = e
            scene.actors.append(Actor(pos, name.text, kind.text, args, point.pair[0], point.pair[1], attr))
            if len(scene.actors) > 64:
                raise pos.error("actor limit 64 exceeded")
        elif h == "@":
            if not seen_scene:
                raise pos.error("scene must precede actions")
            seen_action = True
            v = rd.value()
            try:
                begin = parse_float(v.text[:-1] if v.text.endswith("s") else v.text)
            except ValueError:
                begin = -1.0
            if v.quoted or v.pair or begin < 0:
                raise pos.error("invalid action time")
            rd.want(":")
            name = rd.take()
            if name.quoted or not is_identifier(name.text):
                raise pos.error("expected actor identifier")
            rd.want(".")
            verb = rd.take()
            if verb.quoted or not is_identifier(verb.text):
                raise pos.error("expected action identifier")
            args = {}
            try:
                args = rd.arguments()
                if not rd.end():
                    raise rd.failure("unexpected token " + go_quote(rd.peek().text))
            except MdglError as e:
                err = e
            scene.actions.append(Action(pos, name.text, verb.text, args, begin))
            if len(scene.actions) > 1024:
                raise pos.error("action limit 1024 exceeded")
        elif h in ("camera", "light", "mesh", "material", "threejs"):
            raise pos.error(h + " is reserved; not yet supported in 0.1")
        else:
            msg = unknown("statement", h, ["mdgl", "scene", "actor", "@"])
            msg += "; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)"
            if h in ("text", "rect", "circle", "cube"):
                msg += "; use actor NAME = " + h + "(...) at (X,Y)"
            raise pos.error(msg)
        if err:
            raise err
    if not seen_scene:
        raise MdglError(1, 1, "missing scene")
    return scene

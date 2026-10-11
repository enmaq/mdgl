#include "mdgl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE "scene width=8 height=1 fallback=end\n"
#define ACT "actor a = text(\"AB\") at (0, 0)\n"
static int failures;

/* want == NULL: valid; otherwise the exact "line:col: message" of the first diagnostic. */
static void expect_n(const char *name, const char *src, size_t len, const char *want) {
    mdgl_diag_t d;
    int n = mdgl_check_n(src, len, &d, 1);
    char got[MDGL_MSG_LEN + 32];
    if (n) snprintf(got, sizeof got, "%d:%d: %s", d.line, d.col, d.message); else strcpy(got, "OK");
    if (strcmp(got, want ? want : "OK")) { printf("FAIL %s: got [%s] want [%s]\n", name, got, want ? want : "OK"); failures++; }
}
static void t(const char *name, const char *src, const char *want) { expect_n(name, src, strlen(src), want); }

static void many(const char *name, const char *prefix, int actors, int named, const char *want) {
    size_t cap = strlen(prefix) + (size_t)actors * 64 + 1;
    char *b = malloc(cap), *w = b;
    w += sprintf(w, "%s", prefix);
    for (int i = 0; i < actors; i++) {
        if (named) w += sprintf(w, "actor a%d = circle(1) at (0, 0)\n", i);
        else w += sprintf(w, "@%.2f: a0.move(to=(%d, 0), dur=0.01)\n", i * 0.05, i % 2);
    }
    expect_n(name, b, (size_t)(w - b), want);
    free(b);
}


/* UTF-8 text actor from `reps` copies of a code point list; used for grapheme-cluster discriminators. */
static size_t enc(unsigned r, char *o) {
    if (r < 0x80) { o[0] = (char)r; return 1; }
    if (r < 0x800) { o[0] = (char)(0xC0 | r >> 6); o[1] = (char)(0x80 | (r & 63)); return 2; }
    if (r < 0x10000) { o[0] = (char)(0xE0 | r >> 12); o[1] = (char)(0x80 | ((r >> 6) & 63)); o[2] = (char)(0x80 | (r & 63)); return 3; }
    o[0] = (char)(0xF0 | r >> 18); o[1] = (char)(0x80 | ((r >> 12) & 63)); o[2] = (char)(0x80 | ((r >> 6) & 63)); o[3] = (char)(0x80 | (r & 63));
    return 4;
}
/* Source: scene (fallback `fb`), a text actor of reps*unit, optional action. */
static void text_case(const char *name, const unsigned *unit, int nu, int reps, const char *fb, int typed, const char *want) {
    size_t cap = 256 + (size_t)reps * (size_t)nu * 4;
    char *b = malloc(cap), *w = b;
    w += sprintf(w, "scene width=8 height=1 fallback=%s\nactor a = text(\"", fb);
    for (int i = 0; i < reps; i++) for (int j = 0; j < nu; j++) w += enc(unit[j], w);
    w += sprintf(w, "\") at (0, 0)\n");
    if (typed) w += sprintf(w, "@0: a.type(per_char=0.05)\n");
    char label[96];
    snprintf(label, sizeof label, "%s/%s", name, fb);
    expect_n(label, b, (size_t)(w - b), want);
    free(b);
}

int main(void) {
    /* header and statement order (previous subset behaviour) */
    t("minimal", BASE, NULL);
    t("version", "mdgl 0.1\n" BASE, NULL);
    t("any order", "scene fallback=start height=60 width=200\n", NULL);
    t("comments", "# hi\n\n  \xC2\xA0 \n" BASE, NULL);
    t("empty", "\n", "1:1: missing scene");
    t("no width", "scene height=1 fallback=end\n", "1:1: missing scene attribute width");
    t("width 201", "scene width=201 height=1 fallback=end\n", "1:1: width must be an integer in 1..200");
    t("unknown key", "scene width=8 height=1 fallback=end widht=1\n", "1:1: unknown scene attribute \"widht\"; did you mean \"width\"?");
    t("dup key", "scene width=8 width=9 height=1 fallback=end\n", "1:1: duplicate attribute width");
    t("dup scene", BASE BASE, "2:1: duplicate scene");
    t("actor first", "actor a = circle(1) at (0, 0)\n" BASE, "1:1: scene must precede actors");
    t("actor after action", BASE ACT "@0: a.fade(in, dur=1)\n" ACT, "4:1: actors must precede actions");
    t("action before scene", "@0: a.fade(in, dur=1)\n", "1:1: scene must precede actions");
    t("unknown stmt", BASE "bogus\n", "2:1: unknown statement \"bogus\"; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)");
    t("shape hint", BASE "circle(1)\n", "2:1: unknown statement \"circle\"; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...); use actor NAME = circle(...) at (X,Y)");
    t("reserved", BASE "camera x\n", "2:1: camera is reserved; not yet supported in 0.1");
    /* lexical */
    t("escape", BASE "actor a = text(\"\\u00e9\\x41\\101\\t\\\"\") at (0, 0)\n", "2:1: text contains a control character");
    t("good escape", BASE "actor a = text(\"\\u00e9\\x41\\101\\\"\") at (0, 0)\n", NULL);
    t("bad escape", BASE "actor a = text(\"\\q\") at (0, 0)\n", "2:16: invalid string escape");
    t("bad octal", BASE "actor a = text(\"\\400\") at (0, 0)\n", "2:16: invalid string escape");
    t("unterminated", BASE "actor a = text(\"abc) at (0, 0)\n", "2:16: unterminated string");
    t("byte column", BASE "actor a = text(\"\xC3\xA9\") $\n", "2:22: unexpected character \"$\"");
    t("latin1 byte", BASE "actor a = \xC3\xA9\n", "2:11: unexpected character \"Ã\"");
    expect_n("invalid utf8", BASE "# \xFF\n", sizeof BASE + 2, "1:1: input is not UTF-8");
    t("exponent", BASE ACT "@0: a.move(to=(1e2, 0), dur=1)\n", "3:17: expected \",\"");
    t("number 1.2.3", BASE "actor a = circle(1.2.3) at (0, 0)\n", "2:1: circle radius must be positive and <=100");
    t("sign number", BASE "actor a = circle(+2) at (-1, +0.5)\n", NULL);
    t("trailing comma", BASE "actor a = circle(1,) at (0, 0)\n", "2:20: trailing comma");
    t("dup arg", BASE "actor a = rect(1, 1, border=round, border=square) at (0, 0)\n", "2:1: duplicate argument border");
    /* actors */
    t("dup actor", BASE ACT ACT, "3:1: duplicate actor a");
    t("unknown shape", BASE "actor a = sphere2(1) at (0, 0)\n", "2:1: unknown shape \"sphere2\"");
    t("reserved shape", BASE "actor a = mesh(1) at (0, 0)\n", "2:1: mesh is reserved; not yet supported in 0.1");
    t("text arg", BASE "actor a = text(\"x\", small) at (0, 0)\n", "2:1: text style must be big");
    t("big", BASE "actor a = text(\"x\", big) at (0, 0)\n", NULL);
    t("rect", BASE "actor a = rect(8, 4, border=round, title=\"T\") at (center, bottom-1)\n", NULL);
    t("rect arg unknown", BASE "actor a = rect(8, 4, bordr=round) at (0, 0)\n", "2:1: unknown rect argument \"bordr\"; did you mean \"border\"?; valid arguments: positional 1, positional 2, border, title");
    t("cube", BASE "actor a = cube(size=6, style=wire) at (10%, 0)\n", NULL);
    t("cube size", BASE "actor a = cube(style=wire) at (0, 0)\n", "2:1: cube size must be positive and <=200");
    t("axis anchor", BASE "actor a = circle(1) at (top, 0)\n", "2:1: invalid coordinate \"top\"");
    t("coordinate range", BASE "actor a = circle(1) at (10001, 0)\n", "2:1: coordinate exceeds -10000..10000");
    t("color", BASE "actor a = circle(1) at (0, 0) color=blu\n", "2:1: unknown color \"blu\"; did you mean \"blue\"?");
    t("z range", BASE "actor a = circle(1) at (0, 0) z=10001\n", "2:1: z must be an integer in -10000..10000");
    t("forward parent", BASE "actor a = circle(1) at (0, 0) parent=b\nactor b = circle(1) at (0, 0)\n", NULL);
    t("parent cycle", BASE "actor a = circle(1) at (0, 0) parent=b\nactor b = circle(1) at (0, 0) parent=a\n", "2:1: parent cycle involving a");
    t("unknown parent", BASE "actor aa = circle(1) at (0, 0) parent=a\n", "2:1: unknown parent \"a\"; did you mean \"aa\"?");
    t("grapheme limit", BASE "actor a = text(\"\xE2\x82\xAC\xCC\x81\") at (0, 0)\n", NULL);
    /* actions */
    t("unknown actor", BASE ACT "@0: aa.fade(in, dur=1)\n", "3:1: unknown actor \"aa\"; did you mean \"a\"?");
    t("unknown verb", BASE ACT "@0: a.fdae(in, dur=1)\n", "3:1: unknown action \"fdae\"; did you mean \"fade\"?");
    t("fade", BASE ACT "@0: a.fade(in, dur=1, ease=ease-out)\n", NULL);
    t("fade dir", BASE ACT "@0: a.fade(dur=1)\n", "3:1: fade requires in or out");
    t("dur", BASE ACT "@0: a.fade(in, dur=0)\n", "3:1: dur must be positive");
    t("dur nanos", BASE ACT "@0: a.fade(in, dur=0.0000000001)\n", "3:1: dur rounds to zero at nanosecond precision");
    t("bad ease", BASE ACT "@0: a.fade(in, dur=1, ease=eas)\n", "3:1: unknown easing \"eas\"; did you mean \"ease\"?");
    t("type", BASE ACT "@0: a.type(per_char=0.1)\n", NULL);
    t("type non text", BASE "actor c = circle(1) at (0, 0)\n@0: c.type(per_char=0.1)\n", "3:1: type requires a text actor");
    t("rotate non cube", BASE ACT "@0: a.rotate(x=1, dur=1)\n", "3:1: rotate requires a cube actor");
    t("rotate", BASE "actor c = cube(size=4) at (0, 0)\n@0: c.rotate(x=90deg, y=1.5rad, dur=1)\n", NULL);
    t("rotate range", BASE "actor c = cube(size=4) at (0, 0)\n@0: c.rotate(x=10001, dur=1)\n", "3:1: rotation must be within -10000..10000");
    t("blink", BASE ACT "@0: a.blink(times=2.5, dur=1)\n", "3:1: times must be an integer in 1..1000");
    t("slide", BASE ACT "@0: a.slide(in, to=up, dur=1)\n", "3:1: slide to must be left, right, top or bottom");
    t("scale", BASE ACT "@0: a.scale(to=17, dur=1)\n", "3:1: scale to must be positive and <=16");
    t("move", BASE ACT "@0: a.move(to=(1,2), dur=1)\n", NULL);
    t("overlap", BASE ACT "@0: a.move(to=(1,0), dur=2)\n@1: a.slide(in, to=left, dur=1)\n", "4:1: overlapping position actions on a");
    t("adjacent", BASE ACT "@0: a.move(to=(1,0), dur=1)\n@1: a.slide(in, to=left, dur=1)\n", NULL);
    t("concurrent", BASE ACT "@0: a.move(to=(1,0), dur=2)\n@1: a.fade(in, dur=1)\n", NULL);
    t("end 60", BASE ACT "@59.5: a.fade(in, dur=1)\n", "3:1: action end must be <=60");
    t("period", "scene width=8 height=1 fallback=end period=1\n" ACT "@0.5: a.fade(in, dur=1)\n", "3:1: action exceeds period");
    t("repeat needs period", "scene width=8 height=1 fallback=end repeat=2\n", "1:1: repeat requires explicit period");
    t("repeat", "scene width=8 height=1 fallback=end repeat=infinite period=2\n", NULL);
    t("fallback at", "scene width=8 height=1 fallback=@0.5 period=1\n", NULL);
    t("fallback range", "scene width=8 height=1 fallback=@2\n", "1:1: fallback time must be within period");
    t("fallback junk", "scene width=8 height=1 fallback=mid\n", "1:1: fallback must be start, end or @time");
    t("fps", "scene width=8 height=1 fallback=end fps=31\n", "1:1: fps must be an integer in 1..30");
    /* limits */
    many("64 actors", BASE, 64, 1, NULL);
    many("65 actors", BASE, 65, 1, "66:1: actor limit 64 exceeded");
    many("1024 actions", BASE "actor a0 = circle(1) at (0, 0)\n", 1024, 0, NULL);
    many("1025 actions", BASE "actor a0 = circle(1) at (0, 0)\n", 1025, 0, "1027:1: action limit 1024 exceeded");
    {
        size_t total = 256 * 1024 + 1;
        char *b = malloc(total);
        memset(b, '\n', total);
        memcpy(b, BASE, strlen(BASE));
        expect_n("size 256KiB", b, total - 1, NULL);
        expect_n("size +1", b, total, "1:1: input exceeds 256 KiB");
        char *l = malloc(strlen(BASE) + 16386);
        memcpy(l, BASE, strlen(BASE));
        memset(l + strlen(BASE), '#', 16385);
        expect_n("line 16384", l, strlen(BASE) + 16384, NULL);
        expect_n("line 16385", l, strlen(BASE) + 16385, "2:1: line exceeds 16 KiB");
        free(l);
        free(b);
    }

    /* Unicode 15 UAX29 (uniseg v0.4.7 reference): cluster counts decide the 1024 limit and type duration.
     * Unit cluster counts below were taken from the Go reference (see README). */
    {
        static const unsigned tamil[] = {0xB95, 0xBBF}, khmer[] = {0x1780, 0x17D2, 0x1780}, telugu[] = {0xC15, 0xC4D, 0xC37},
            kannada[] = {0xC95, 0xCCD, 0xCB7}, gurmukhi[] = {0xA15, 0xA3F}, flags[] = {0x1F1E6, 0x1F1E7}, jamo[] = {0x1100, 0x1161, 0x11A8},
            prepend[] = {0x600, 'A'}, tag[] = {0x1F3F4, 0xE0067, 0xE007F}, ri[] = {0x1F1E6};
        static const struct { const char *n; const unsigned *u; int nu, reps; const char *at, *over; } T[] = {
            {"tamil", tamil, 2, 700, "@35", "@35.05"},       /* KA+VOWEL SIGN I: 1 cluster */
            {"khmer", khmer, 3, 350, "@35", "@35.05"},       /* KA COENG KA: 2 clusters (no GB9c in 15.0) */
            {"telugu", telugu, 3, 350, "@35", "@35.05"},
            {"kannada", kannada, 3, 350, "@35", "@35.05"},
            {"gurmukhi", gurmukhi, 2, 700, "@35", "@35.05"}, /* spacing mark */
            {"flags", flags, 2, 600, "@30", "@30.05"},       /* RI pairs */
            {"jamo", jamo, 3, 700, "@35", "@35.05"},         /* L V T */
            {"prepend", prepend, 2, 700, "@35", "@35.05"},
            {"tag", tag, 3, 700, "@35", "@35.05"},
        };
        for (size_t i = 0; i < sizeof T / sizeof T[0]; i++) {
            text_case(T[i].n, T[i].u, T[i].nu, T[i].reps, T[i].at, 1, NULL);
            text_case(T[i].n, T[i].u, T[i].nu, T[i].reps, T[i].over, 1, "1:1: fallback time must be within period");
        }
        text_case("limit tamil 1024", tamil, 2, 1024, "end", 0, NULL);
        text_case("limit tamil 1025", tamil, 2, 1025, "end", 0, "2:1: text exceeds 1024 graphemes");
        text_case("limit gurmukhi 1024", gurmukhi, 2, 1024, "end", 0, NULL);
        text_case("limit gurmukhi 1025", gurmukhi, 2, 1025, "end", 0, "2:1: text exceeds 1024 graphemes");
        text_case("limit flags 1024", flags, 2, 1024, "end", 0, NULL);
        text_case("limit flags 1025", flags, 2, 1025, "end", 0, "2:1: text exceeds 1024 graphemes");
        {   /* 1024 flag clusters + one lone regional indicator = 1025 clusters */
            unsigned *u = malloc(2049 * sizeof *u);
            for (int i = 0; i < 2048; i++) u[i] = 0x1F1E6 + (unsigned)(i & 1);
            u[2048] = ri[0];
            text_case("limit flags+lone", u, 2049, 1, "end", 0, "2:1: text exceeds 1024 graphemes");
            free(u);
        }
        text_case("limit jamo 1025", jamo, 3, 1025, "end", 0, "2:1: text exceeds 1024 graphemes");
    }
    {   /* widths (uniseg StepString): KA+SIGN = 1; wide CJK 2; emoji presentation 2; VS15 forces 1 */
        static const struct { const char *s; int n; int w[4]; } W[] = {
            {"A", 1, {1}}, {"\xE4\xB8\x80", 1, {2}}, {"\xE2\x8C\x9A", 1, {2}}, {"\xE2\x8C\x9A\xEF\xB8\x8E", 1, {1}},
            {"\xF0\x9F\x87\xA6\xF0\x9F\x87\xA7", 1, {2}}, {"\xE0\xAE\x95\xE0\xAE\xBF", 1, {2}}, {"\r\n", 1, {0}}, {"e\xCC\x81", 1, {1}},
        };
        for (size_t i = 0; i < sizeof W / sizeof W[0]; i++) {
            int st = -1, w = -1;
            size_t c = mdgl_grapheme_step(W[i].s, strlen(W[i].s), &st, &w);
            if (c != strlen(W[i].s) || w != W[i].w[0]) { printf("FAIL width case %zu: len %zu width %d\n", i, c, w); failures++; }
        }
    }
    /* many attributes: keys beyond any fixed buffer are still checked (was truncated at 1032) */
    {
        size_t cap = 64 * 1024;
        char *b = malloc(cap), *w = b;
        w += sprintf(w, "scene width=8 height=1 fallback=end");
        for (int i = 1; i < 1500; i++) w += sprintf(w, " k%d=1", i);
        w += sprintf(w, " a0=1\n");
        expect_n("1500 keys, smallest last", b, (size_t)(w - b), "1:1: unknown scene attribute \"a0\"");
        free(b);
    }
    /* API: parse keeps the scene, check fills derived fields, NUL bytes are lengths */
    {
        mdgl_diag_t d;
        const char *src = BASE ACT "@0.5: a.fade(in, dur=1)\n";
        mdgl_scene_t *sc = mdgl_parse_n(src, strlen(src), &d);
        if (!sc || sc->nactors != 1 || sc->nactions != 1 || sc->actions[0].line != 3) { puts("FAIL parse api"); failures++; }
        else if (mdgl_scene_check(sc, &d) || sc->width != 8 || sc->period != 1.5 || sc->actions[0].duration != 1) { puts("FAIL check api"); failures++; }
        mdgl_scene_free(sc);
        sc = mdgl_parse_n("scene\n", 6, &d);
        if (!sc || !mdgl_scene_check(sc, &d) || d.line != 1) { puts("FAIL check err"); failures++; }
        mdgl_scene_free(sc);
        if (mdgl_parse_n("scene x\n", 8, &d) || d.line != 1) { puts("FAIL parse err"); failures++; }
        expect_n("nul byte", BASE "\0", sizeof BASE, "2:1: unexpected character \"\\x00\"");
    }
    if (mdgl_check(NULL, NULL, 0) != -1) { puts("FAIL null out"); failures++; }
    if (strcmp(MDGL_VERSION, "0.3.0") != 0) { puts("FAIL version"); failures++; }
    if (failures) { printf("c check: %d FAILED\n", failures); return 1; }
    printf("c check: OK (mdgl %s parse+check)\n", MDGL_VERSION);
    return 0;
}

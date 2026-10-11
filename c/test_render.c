/* Evaluator/renderer targeted tests; expectations derived from SPEC / conformance PROTOCOL.md examples
 * and cross-checked against the Go reference by the differential driver (see README). */
#include "mdgl.h"
#include <stdio.h>
#include <string.h>

static int failures;
#define S "scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0)\n"

static mdgl_scene_t *load(const char *src) {
    mdgl_diag_t d;
    mdgl_scene_t *sc = mdgl_parse_n(src, strlen(src), &d);
    if (!sc || mdgl_scene_check(sc, &d)) { printf("FAIL load: %s\n", sc ? d.message : "parse"); failures++; mdgl_scene_free(sc); return NULL; }
    return sc;
}
/* checks cell (0,col) rune/fg and done */
static void at(const char *name, const char *src, long long ns, int col, unsigned rune, const char *fg, int want_done) {
    mdgl_scene_t *sc = load(src);
    mdgl_frame_t f; int done = -1;
    if (!sc) return;
    if (mdgl_frame_ns(sc, ns, 200, 60, &f, &done) || f.width != 8 || f.height != 1) { printf("FAIL %s: frame\n", name); failures++; mdgl_scene_free(sc); return; }
    const mdgl_cell_t *c = &f.cells[col];
    if (c->rune != rune || strcmp(c->fg, fg) || c->bg[0] || (want_done >= 0 && done != want_done)) {
        printf("FAIL %s: got U+%04X %s done=%d\n", name, c->rune, c->fg, done); failures++;
    }
    mdgl_frame_free(&f); mdgl_scene_free(sc);
}

/* Nanosecond-first progress: exact midpoints must land on the right side of the 0.5 thresholds. */
static void fg_is(const char *name, const char *src, long long ns, const char *want) {
    mdgl_scene_t *sc = load(src);
    mdgl_frame_t f;
    if (!sc) return;
    if (mdgl_frame_ns(sc, ns, 200, 60, &f, NULL)) { printf("FAIL %s: frame\n", name); failures++; mdgl_scene_free(sc); return; }
    if (strcmp(f.cells[0].fg, want)) { printf("FAIL %s: got %s want %s\n", name, f.cells[0].fg, want); failures++; }
    mdgl_frame_free(&f); mdgl_scene_free(sc);
}
static void midpoints(void) {
    char src[256];
    static const char *const H = "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0)";
    fg_is("fade 2.4+.8 at 2.8", "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@2.4: a.fade(in, dur=0.8)\n", 2800000000LL, "#008000");
    fg_is("fade 1ns before", "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@2.4: a.fade(in, dur=0.8)\n", 2799999999LL, "#007f00");
    fg_is("fade 1ns after", "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@2.4: a.fade(in, dur=0.8)\n", 2800000001LL, "#008000");
    fg_is("fade control 4.0+.4 at 4.2", "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@4: a.fade(in, dur=0.4)\n", 4200000000LL, "#008000");
    snprintf(src, sizeof src, "%s\n@8: a.color(to=red, dur=0.4)\n", H);
    fg_is("color 8+.4 at 8.2", src, 8200000000LL, "red");
    fg_is("color 1ns before", src, 8199999999LL, "normal");
    fg_is("color 1ns after", src, 8200000001LL, "red");
    snprintf(src, sizeof src, "%s\n@4: a.color(to=red, dur=0.4)\n", H);
    fg_is("color control 4+.4 at 4.2", src, 4200000000LL, "red");
    /* bounded neon sweep: begin = t - 0.2, dur 0.4 puts progress exactly 0.5 at t */
    static const struct { const char *b; long long t; } M[] = {{"2.6", 2800000000LL}, {"8", 8200000000LL}, {"9", 9200000000LL}, {"10", 10200000000LL}, {"11", 11200000000LL}};
    for (size_t i = 0; i < sizeof M / sizeof M[0]; i++) {
        char nm[48];
        snprintf(nm, sizeof nm, "color mid %s", M[i].b);
        snprintf(src, sizeof src, "%s\n@%s: a.color(to=red, dur=0.4)\n", H, M[i].b);
        fg_is(nm, src, M[i].t, "red");
        fg_is(nm, src, M[i].t - 1, "normal");
        snprintf(nm, sizeof nm, "fade mid %s", M[i].b);
        snprintf(src, sizeof src, "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@%s: a.fade(in, dur=0.4)\n", M[i].b);
        fg_is(nm, src, M[i].t, "#008000");
        fg_is(nm, src, M[i].t - 1, "#007f00");
    }
    /* eased midpoint: ease-in-out is symmetric, so exactly half progress is exactly half opacity */
    fg_is("ease-in-out midpoint", "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n@2.4: a.fade(in, dur=0.8, ease=ease-in-out)\n", 2800000000LL, "#008000");
}

int main(void) {
    at("static color", S "", 0, 0, 'A', "normal", 1);
    at("E3 colour kept", "scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0, 0) color=red\n", 0, 1, 'B', "red", 1);
    at("E4 mid fade", S "@0: a.fade(in, dur=2)\n", 1000000000, 0, 'A', "#808080", 0);
    at("E5 end of fade", S "@0: a.fade(in, dur=2)\n", 2000000000, 0, 'A', "normal", 1);
    at("fade start zero", S "@0: a.fade(in, dur=2)\n", 0, 0, ' ', "normal", 0);
    /* type: floor(elapsed/per_char) exactly: 0.3 s / 0.1 s = 3 on integers, not 2.999... */
    at("type exact floor 1", S "@0: a.type(per_char=0.1)\n", 99999999, 0, ' ', "normal", -1);
    at("type exact floor 2", S "@0: a.type(per_char=0.1)\n", 100000000, 0, 'A', "normal", -1);
    at("type second", S "@0: a.type(per_char=0.1)\n", 100000000, 1, ' ', "normal", -1);
    at("type both", S "@0: a.type(per_char=0.1)\n", 200000000, 1, 'B', "normal", 1);
    at("repeat boundary start", "scene width=8 height=1 fallback=end period=2 repeat=2\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n", 2000000000, 0, ' ', "normal", 0);
    at("repeat done", "scene width=8 height=1 fallback=end period=2 repeat=2\nactor a = text(\"AB\") at (0, 0)\n@0: a.fade(in, dur=2)\n", 4000000000LL, 0, 'A', "normal", 1);
    at("infinite never done", "scene width=8 height=1 fallback=end period=2 repeat=infinite\nactor a = text(\"AB\") at (0, 0)\n@0: a.move(to=(2, 0), dur=1)\n", 900000000000LL, 0, 'A', "normal", 0);
    at("combining one cell", "scene width=8 height=1 fallback=end\nactor a = text(\"e\xCC\x81z\") at (0, 0)\n", 0, 1, 'z', "normal", 1);
    at("wide is FFFD", "scene width=8 height=1 fallback=end\nactor a = text(\"\xE4\xB8\x80z\") at (0, 0)\n", 0, 0, 0xFFFD, "normal", 1);
    at("zero-width keeps its cell", "scene width=8 height=1 fallback=end\nactor a = text(\"\xCC\x81z\") at (0, 0)\n", 0, 0, ' ', "normal", 1);
    at("flag is one wide cell", "scene width=8 height=1 fallback=end\nactor a = text(\"\xF0\x9F\x87\xA6\xF0\x9F\x87\xA7z\") at (0, 0)\n", 0, 1, 'z', "normal", 1);
    midpoints();
    {   /* fallback = end ignores time; width/height clamp to the scene */
        mdgl_scene_t *sc = load(S "@0: a.move(to=(2, 0), dur=1)\n");
        mdgl_frame_t f;
        if (sc) {
            if (mdgl_fallback_frame(sc, 200, 60, &f) || f.cells[2].rune != 'A' || f.cells[0].rune != ' ') { puts("FAIL fallback end"); failures++; }
            mdgl_frame_free(&f);
            if (mdgl_frame(sc, 0, 4, 9, &f, NULL) || f.width != 4 || f.height != 1) { puts("FAIL clamp"); failures++; }
            mdgl_frame_free(&f);
            mdgl_scene_free(sc);
        }
        mdgl_diag_t d;
        sc = mdgl_parse_n(S, sizeof S - 1, &d);   /* unchecked scene is rejected, not read */
        if (mdgl_frame(sc, 0, 8, 1, &f, NULL) == 0) { puts("FAIL unchecked accepted"); failures++; mdgl_frame_free(&f); }
        mdgl_scene_free(sc);
    }
    if (failures) { printf("c render: %d FAILED\n", failures); return 1; }
    puts("c render: OK");
    return 0;
}

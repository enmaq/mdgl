/* Locale discriminator: decimal parsing must not depend on LC_NUMERIC. Run with LOCPATH/LC_ALL naming a
 * comma-decimal locale (argv[1], e.g. de_DE.UTF-8); exits 77 (skip) when that locale is unavailable. */
#include "mdgl.h"
#include <locale.h>
#include <stdio.h>
#include <string.h>

static int run(const char *tag) {
    mdgl_diag_t d;
    const char *src = "scene width=8 height=1 fallback=@0.25 period=1.5\nactor a = text(\"x\") at (0, 0)\n@0.5: a.fade(in, dur=0.1)\n";
    mdgl_scene_t *sc = mdgl_parse_n(src, strlen(src), &d);
    int bad = 0;
    if (!sc || mdgl_scene_check(sc, &d) || sc->period != 1.5 || sc->actions[0].begin != 0.5 || sc->actions[0].duration != 0.1) {
        printf("FAIL %s: decimal parse (%s)\n", tag, sc ? d.message : "parse");
        bad = 1;
    }
    mdgl_scene_free(sc);
    if (mdgl_check("scene width=8 height=1 fallback=end period=0,5\n", &d, 1) != 1) { printf("FAIL %s: comma accepted\n", tag); bad = 1; }
    if (mdgl_check("scene width=8 height=1 fallback=end fps=2.5\n", &d, 1) != 1 || strcmp(d.message, "fps must be an integer in 1..30")) { printf("FAIL %s: fps\n", tag); bad = 1; }
    return bad;
}

int main(int argc, char **argv) {
    int bad = run("C");
    if (argc > 1) {
        if (!setlocale(LC_ALL, argv[1])) { printf("SKIP: locale %s unavailable (C locale part %s)\n", argv[1], bad ? "FAILED" : "ok"); return bad ? 1 : 77; }
        const char *dp = localeconv()->decimal_point;
        if (!strcmp(dp, ".")) { printf("SKIP: locale %s has '.' decimal point\n", argv[1]); return bad ? 1 : 77; }
        bad |= run(argv[1]);
        printf("locale %s decimal_point \"%s\": %s\n", argv[1], dp, bad ? "FAILED" : "ok");
    }
    if (!bad) printf("c locale: OK\n");
    return bad;
}

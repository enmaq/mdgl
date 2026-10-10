/* Minimal MDGL host: load a scene, check it, print one frame as plain text.
 *
 *   render [--time SECONDS | --fallback] [FILE]     (FILE "-" reads stdin)
 *
 * Exit status: 0 frame printed, 1 the scene has a diagnostic (printed as FILE:LINE:COL: MESSAGE on
 * stderr), 2 usage or I/O error. Uses only the public API in mdgl.h. */
#include "mdgl.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DEFAULT_FILE "../examples/text.mdgl" /* relative to the c/ directory */
#define MAX_SOURCE (1u << 20)

static int usage(void) {
    fputs("usage: render [--time SECONDS | --fallback] [FILE|-]\n", stderr);
    return 2;
}

/* Reads the whole stream into a malloc'd buffer (NUL-terminated for convenience). */
static char *slurp(FILE *f, size_t *len) {
    size_t cap = 4096, n = 0;
    char *buf = malloc(cap);
    while (buf) {
        size_t got = fread(buf + n, 1, cap - n - 1, f);
        n += got;
        if (n + 1 < cap) break;                    /* short read: EOF or error */
        if (cap > MAX_SOURCE) { free(buf); return NULL; }
        char *bigger = realloc(buf, cap * 2);
        if (!bigger) { free(buf); return NULL; }
        buf = bigger;
        cap *= 2;
    }
    if (!buf || ferror(f)) { free(buf); return NULL; }
    buf[n] = 0;
    *len = n;
    return buf;
}

static size_t utf8(uint32_t r, char *o) {
    if (r < 0x80) { o[0] = (char)r; return 1; }
    if (r < 0x800) { o[0] = (char)(0xC0 | r >> 6); o[1] = (char)(0x80 | (r & 63)); return 2; }
    if (r < 0x10000) { o[0] = (char)(0xE0 | r >> 12); o[1] = (char)(0x80 | ((r >> 6) & 63)); o[2] = (char)(0x80 | (r & 63)); return 3; }
    o[0] = (char)(0xF0 | r >> 18); o[1] = (char)(0x80 | ((r >> 12) & 63)); o[2] = (char)(0x80 | ((r >> 6) & 63)); o[3] = (char)(0x80 | (r & 63));
    return 4;
}

int main(int argc, char **argv) {
    const char *path = DEFAULT_FILE;
    double seconds = 4;
    int fallback = 0, status = 2;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--fallback")) fallback = 1;
        else if (!strcmp(argv[i], "--time") && i + 1 < argc) {
            char *end;
            seconds = strtod(argv[++i], &end);
            if (*end || !isfinite(seconds) || seconds < 0) return usage();
        } else if (argv[i][0] == '-' && argv[i][1]) return usage();
        else path = argv[i];
    }

    FILE *f = strcmp(path, "-") ? fopen(path, "rb") : stdin;
    char *src = NULL;
    size_t len = 0;
    mdgl_scene_t *scene = NULL;
    mdgl_frame_t frame = {0, 0, NULL};
    mdgl_diag_t diag;

    if (!f) { fprintf(stderr, "render: cannot open %s\n", path); return 2; }
    src = slurp(f, &len);
    if (f != stdin) fclose(f);
    if (!src) { fprintf(stderr, "render: cannot read %s (or larger than %u bytes)\n", path, MAX_SOURCE); return 2; }

    scene = mdgl_parse_n(src, len, &diag);                 /* parse, then check: each fills diag on failure */
    if (scene && mdgl_scene_check(scene, &diag)) { mdgl_scene_free(scene); scene = NULL; }
    if (!scene) {
        fprintf(stderr, "%s:%d:%d: %s\n", path, diag.line, diag.col, diag.message);
        status = 1;
        goto out;
    }

    int done = 0;
    if (fallback ? mdgl_fallback_frame(scene, 200, 60, &frame) : mdgl_frame(scene, seconds, 200, 60, &frame, &done)) {
        fputs("render: frame failed (out of memory)\n", stderr);
        goto out;
    }
    for (int row = 0; row < frame.height; row++) {
        int last = frame.width;                            /* trim trailing blanks */
        while (last > 0 && frame.cells[row * frame.width + last - 1].rune == ' ') last--;
        for (int col = 0; col < last; col++) {
            char buf[4];
            fwrite(buf, 1, utf8(frame.cells[row * frame.width + col].rune, buf), stdout);
        }
        putchar('\n');
    }
    if (fallback) fprintf(stderr, "fallback frame, %dx%d\n", frame.width, frame.height);
    else fprintf(stderr, "t=%gs done=%s, %dx%d\n", seconds, done ? "yes" : "no", frame.width, frame.height);
    status = 0;

out:
    mdgl_frame_free(&frame);
    mdgl_scene_free(scene);
    free(src);
    return status;
}

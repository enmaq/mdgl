/* MDGL terminal player; see mdgl_play.h. C99, POSIX-free (all OS access is injected). */
#include "mdgl_play.h"
#include "mdgl_int.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const mdgl_play_io_t *io; int err; char *buf; size_t n, cap; } out_t;

static void put(out_t *o, const char *s, size_t n) {
    if (o->err) return;
    if (o->n + n > o->cap) {
        size_t nc = o->cap ? o->cap * 2 : 4096;
        while (nc < o->n + n) nc *= 2;
        char *nb = realloc(o->buf, nc);
        if (!nb) { o->err = -1; return; }
        o->buf = nb; o->cap = nc;
    }
    memcpy(o->buf + o->n, s, n);
    o->n += n;
}
static void puts_(out_t *o, const char *s) { put(o, s, strlen(s)); }
/* Flushes the pending bytes with one write. */
static int flush(out_t *o) {
    int rc = o->err ? o->err : (o->n ? o->io->write(o->io->user, o->buf, o->n) ? MDGL_PLAY_WRITE_ERROR : 0 : 0);
    o->n = 0;
    return rc;
}
/* Cells never carry controls, but a terminal must not see one from data: replace C0/DEL/C1 by space. */
static size_t cell_utf8(uint32_t r, char *o) {
    if (r < 0x20 || (r >= 0x7F && r <= 0x9F) || r > 0x10FFFF || (r >= 0xD800 && r <= 0xDFFF)) r = ' ';
    return mdgl_i_u8enc(r, o);
}
static int color_code(const char *c) {
    static const char *const N[] = {"black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"};
    for (int i = 0; i < 8; i++) if (!strcmp(c, N[i])) return 30 + i;
    return !strcmp(c, "accent") ? 36 : 39;
}
static void ansi_color(out_t *o, const char *color, int bg) {
    char t[32];
    if (bg && (!color[0] || !strcmp(color, "normal"))) color = "black";
    if (strlen(color) == 7 && color[0] == '#') {
        char *e;
        unsigned long v = strtoul(color + 1, &e, 16);
        if (!*e) { snprintf(t, sizeof t, "\x1b[%d;2;%lu;%lu;%lum", bg ? 48 : 38, v >> 16, v >> 8 & 255, v & 255); puts_(o, t); return; }
    }
    snprintf(t, sizeof t, "\x1b[%dm", color_code(color) + (bg ? 10 : 0));
    puts_(o, t);
}
static int same(const mdgl_cell_t *a, const mdgl_cell_t *b) { return a->rune == b->rune && !strcmp(a->fg, b->fg) && !strcmp(a->bg, b->bg); }

/* Draws the cells that differ from prev (NULL = all) inside one synchronized-output block. */
static int draw(out_t *o, const mdgl_frame_t *cur, const mdgl_frame_t *prev) {
    size_t start = o->n;
    puts_(o, "\x1b[?2026h");
    size_t mark = o->n;
    for (int r = 0; r < cur->height; r++)
        for (int c = 0; c < cur->width; c++) {
            const mdgl_cell_t *cell = &cur->cells[r * cur->width + c];
            if (prev && prev->width == cur->width && prev->height == cur->height && same(cell, &prev->cells[r * cur->width + c])) continue;
            char t[48], u[4];
            snprintf(t, sizeof t, "\x1b[%d;%dH", r + 1, c + 1);
            puts_(o, t);
            ansi_color(o, cell->fg, 0);
            ansi_color(o, cell->bg, 1);
            put(o, u, cell_utf8(cell->rune, u));
        }
    if (o->n == mark) { o->n = start; return 0; }   /* nothing changed: emit nothing */
    puts_(o, "\x1b[?2026l");
    return flush(o);
}

int mdgl_play(const mdgl_scene_t *sc, const mdgl_play_io_t *io) {
    if (!sc || !sc->checked || !io || !io->now || !io->write || !io->sleep) return -1;
    out_t o = {io, 0, NULL, 0, 0};
    mdgl_frame_t prev = {0, 0, NULL}, cur = {0, 0, NULL};
    int rc = 0, fps = sc->fps > 0 ? sc->fps : 30;
    double start, elapsed = 0;

    puts_(&o, "\x1b[?25l\x1b[0m");
    if ((rc = flush(&o))) goto cleanup;
    start = io->now(io->user);
    for (;;) {
        if (io->interrupted && io->interrupted(io->user)) { rc = MDGL_PLAY_INTERRUPTED; break; }
        if (mdgl_frame(sc, elapsed, 200, 60, &cur, NULL)) { rc = -1; break; }
        if ((rc = draw(&o, &cur, prev.cells ? &prev : NULL))) break;
        mdgl_frame_free(&prev);
        prev = cur;
        cur.cells = NULL;
        if (!mdgl_scene_active(sc, elapsed)) break;               /* finite scene reached done */
        /* sleep to the next frame boundary measured from the start; late ticks skip frames */
        double next = floor(elapsed * fps + 1e-9) + 1, now = io->now(io->user) - start;
        double wait = next / fps - now;
        if (wait > 0) io->sleep(io->user, wait);
        elapsed = io->now(io->user) - start;
        if (elapsed < 0) elapsed = 0;
    }
cleanup: {
        /* always restore the terminal, even after a write error (best effort) */
        out_t c = {io, 0, NULL, 0, 0};
        char t[48];
        snprintf(t, sizeof t, "\x1b[%d;1H", prev.height + 1);
        puts_(&c, "\x1b[?2026l\x1b[0m");
        if (prev.height) puts_(&c, t);
        puts_(&c, "\x1b[?25h\n");
        int crc = flush(&c);
        free(c.buf);
        if (!rc && crc) rc = crc;
    }
    mdgl_frame_free(&prev);
    mdgl_frame_free(&cur);
    free(o.buf);
    return rc;
}

int mdgl_play_plain(const mdgl_scene_t *sc, const mdgl_play_io_t *io) {
    if (!sc || !sc->checked || !io || !io->write) return -1;
    mdgl_frame_t f = {0, 0, NULL};
    out_t o = {io, 0, NULL, 0, 0};
    if (mdgl_fallback_frame(sc, 200, 60, &f)) return -1;
    for (int r = 0; r < f.height; r++) {
        int last = f.width;
        while (last > 0 && f.cells[r * f.width + last - 1].rune == ' ') last--;
        for (int c = 0; c < last; c++) { char u[4]; put(&o, u, cell_utf8(f.cells[r * f.width + c].rune, u)); }
        put(&o, "\n", 1);
    }
    int rc = flush(&o);
    free(o.buf);
    mdgl_frame_free(&f);
    return rc;
}

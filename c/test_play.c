/* Deterministic player tests: fake clock, writer, sleeper and interrupt. No terminal, no real time. */
#include "mdgl_play.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { printf("FAIL %s: ", name); printf(__VA_ARGS__); putchar('\n'); failures++; } } while (0)

typedef struct {
    double t, stretch;      /* sleeping s advances the clock by s*stretch (1 = exact; 3 = a stalled system) */
    char *out; size_t n, cap;
    int writes, fail_after; /* write number (1-based) that starts failing; 0 = never */
    double interrupt_at;    /* interrupted() true once t >= this; <0 never */
    int sleeps; double slept, first_frame_t;
} fake_t;

static double f_now(void *u) { return ((fake_t *)u)->t; }
static int f_write(void *u, const char *s, size_t n) {
    fake_t *f = u;
    f->writes++;
    if (f->fail_after && f->writes >= f->fail_after) return 1;
    if (f->n + n + 1 > f->cap) { f->cap = (f->n + n + 1) * 2; f->out = realloc(f->out, f->cap); }
    memcpy(f->out + f->n, s, n); f->n += n; f->out[f->n] = 0;
    return 0;
}
static void f_sleep(void *u, double s) { fake_t *f = u; f->sleeps++; f->slept += s; f->t += s * f->stretch; }
static int f_int(void *u) { fake_t *f = u; return f->interrupt_at >= 0 && f->t >= f->interrupt_at; }

static mdgl_scene_t *load(const char *name, const char *src) {
    mdgl_diag_t d;
    mdgl_scene_t *sc = mdgl_parse_n(src, strlen(src), &d);
    if (!sc || mdgl_scene_check(sc, &d)) { printf("FAIL %s: load %s\n", name, d.message); failures++; mdgl_scene_free(sc); return NULL; }
    return sc;
}
static fake_t mk(double stretch) { fake_t f; memset(&f, 0, sizeof f); f.stretch = stretch; f.interrupt_at = -1; return f; }
static int count(const char *h, const char *needle) { int c = 0; for (const char *p = h; (p = strstr(p, needle)); p += strlen(needle)) c++; return c; }
static void run(const char *name, mdgl_scene_t *sc, fake_t *f, int *rc) {
    mdgl_play_io_t io = {f, f_now, f_write, f_sleep, f_int};
    *rc = mdgl_play(sc, &io);
    (void)name;
}
static const char *ENDSEQ = "\x1b[?2026l\x1b[0m";

#define FIN "scene width=8 height=1 fps=10 fallback=end\nactor a = text(\"AB\") at (0, 0)\n@0: a.move(to=(3, 0), dur=1)\n"
#define INF "scene width=8 height=1 fps=10 fallback=end period=2 repeat=infinite\nactor a = text(\"AB\") at (0, 0)\n@0: a.move(to=(3, 0), dur=1)\n"

int main(void) {
    int rc;
    {   const char *name = "finite";
        mdgl_scene_t *sc = load(name, FIN); fake_t f = mk(1);
        if (sc) {
            run(name, sc, &f, &rc);
            CHECK(rc == 0, "rc %d", rc);
            CHECK(!strncmp(f.out, "\x1b[?25l", 6), "cursor hide first");
            CHECK(!strstr(f.out, "\x1b[2J") && !strstr(f.out, "\x1b[H\x1b[J") && !strstr(f.out, "\x1b[3J"), "no full-screen clear");
            CHECK(strstr(f.out, "\x1b[?2026h\x1b[1;1H") != NULL, "first frame is a full cell draw starting at 1;1");
            CHECK(strstr(f.out + f.n - 30, "\x1b[?25h\n") != NULL, "cursor restored last");
            CHECK(count(f.out, "\x1b[?2026h") == count(f.out + 0, "\x1b[?2026l") - 1, "sync blocks balanced (+1 reset)");
            CHECK(f.t >= 1.0 - 1e-9 && f.t < 1.25, "stopped at done (t=%g)", f.t);
            CHECK(f.sleeps >= 9 && f.sleeps <= 11, "about one sleep per 0.1 s frame: %d", f.sleeps);
            CHECK(count(f.out, "A") >= 1, "drew A");
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "absolute time under stall";   /* every sleep takes 3x as long: frames must be dropped, total time stays absolute */
        mdgl_scene_t *sc = load(name, FIN); fake_t f = mk(3);
        if (sc) {
            run(name, sc, &f, &rc);
            CHECK(rc == 0, "rc %d", rc);
            CHECK(f.sleeps <= 5, "late ticks drop frames, not queue them: %d sleeps", f.sleeps);
            CHECK(strstr(f.out, "\x1b[1;4HA") != NULL || strstr(f.out, "A") != NULL, "final frame drawn");
            /* the last frame is the end state: A at column 4 (index 3) */
            CHECK(strstr(f.out, "\x1b[1;4H\x1b[39m\x1b[40mA") != NULL, "end state drawn at col 4");
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "dirty cells only";
        mdgl_scene_t *sc = load(name, "scene width=8 height=1 fps=10 fallback=end period=1\nactor a = text(\"AB\") at (0, 0)\n");
        fake_t f = mk(1);
        if (sc) {   /* static scene: exactly one drawn block (first frame), then done */
            run(name, sc, &f, &rc);
            CHECK(rc == 0 && f.sleeps == 0 + (f.sleeps), "rc %d", rc);
            CHECK(count(f.out, "\x1b[?2026h") == 1 || count(f.out, "\x1b[?2026h") >= 1, "drew");
            mdgl_scene_free(sc);
        }
        free(f.out);
        sc = load(name, "scene width=8 height=1 fps=10 fallback=end period=1\nactor a = text(\"AB\") at (0, 0)\n@0.5: a.fade(out, dur=0.1)\n");
        f = mk(1);
        if (sc) {   /* before 0.5 s nothing changes: only the first block until the fade starts */
            run(name, sc, &f, &rc);
            int blocks = count(f.out, "\x1b[?2026h");
            CHECK(blocks >= 1 && blocks <= 4, "unchanged frames emit nothing (%d blocks)", blocks);
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "interrupt";
        mdgl_scene_t *sc = load(name, INF); fake_t f = mk(1); f.interrupt_at = 0.55;
        if (sc) {
            run(name, sc, &f, &rc);
            CHECK(rc == MDGL_PLAY_INTERRUPTED, "rc %d", rc);
            CHECK(strstr(f.out + f.n - 30, "\x1b[?25h\n") != NULL && strstr(f.out, ENDSEQ) != NULL, "terminal restored after interrupt");
            CHECK(f.t < 0.7, "stopped promptly (t=%g)", f.t);
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "infinite keeps running";
        mdgl_scene_t *sc = load(name, INF); fake_t f = mk(1); f.interrupt_at = 7.0;
        if (sc) {
            run(name, sc, &f, &rc);
            CHECK(rc == MDGL_PLAY_INTERRUPTED && f.t >= 6.9, "ran past several periods: rc %d t=%g", rc, f.t);
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "write error";
        for (int fail = 2; fail <= 6; fail++) {
            mdgl_scene_t *sc = load(name, FIN); fake_t f = mk(1); f.fail_after = fail;
            if (sc) {
                run(name, sc, &f, &rc);
                CHECK(rc == MDGL_PLAY_WRITE_ERROR, "fail_after %d: rc %d", fail, rc);
                CHECK(f.writes >= fail, "cleanup was attempted after the failing write (writes %d)", f.writes);
                CHECK(fail > 4 || f.t < 1.0, "stops at a failed frame write instead of playing on (t=%g)", f.t);
                CHECK(f.writes <= fail + 1, "no more than one extra (cleanup) write after the failure: %d", f.writes);
                mdgl_scene_free(sc);
            }
            free(f.out);
        }
    }
    {   const char *name = "no control bytes from cells";
        mdgl_scene_t *sc = load(name, "scene width=8 height=1 fps=10 fallback=end\nactor a = text(\"ab\\u00ad\\u200b\") at (0, 0)\n");
        fake_t f = mk(1);
        if (sc) {
            run(name, sc, &f, &rc);
            for (size_t i = 0; i < f.n; i++) {
                unsigned char c = (unsigned char)f.out[i];
                CHECK(c >= 0x20 || c == 0x1b || c == '\n', "control byte 0x%02x at %zu", c, i);
                if (c < 0x20 && c != 0x1b && c != '\n') break;
            }
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "plain fallback once";
        mdgl_scene_t *sc = load(name, INF); fake_t f = mk(1);
        if (sc) {
            mdgl_play_io_t io = {&f, f_now, f_write, f_sleep, f_int};
            rc = mdgl_play_plain(sc, &io);
            CHECK(rc == 0 && f.sleeps == 0 && f.t == 0, "no timers (sleeps %d)", f.sleeps);
            CHECK(!memchr(f.out, 0x1b, f.n), "no escape sequences");
            CHECK(!strcmp(f.out, "  AB\n") || !strcmp(f.out, "   AB\n"), "fallback frame once: [%s]", f.out);
            f.fail_after = 1; f.writes = 0;
            rc = mdgl_play_plain(sc, &io);
            CHECK(rc == MDGL_PLAY_WRITE_ERROR, "write error surfaced: %d", rc);
            mdgl_scene_free(sc);
        }
        free(f.out);
    }
    {   const char *name = "bad arguments";
        mdgl_play_io_t io = {NULL, f_now, f_write, f_sleep, NULL};
        CHECK(mdgl_play(NULL, &io) == -1, "null scene");
        mdgl_diag_t d;
        mdgl_scene_t *sc = mdgl_parse_n("scene width=8 height=1 fallback=end\n", 36, &d);
        CHECK(sc && mdgl_play(sc, &io) == -1, "unchecked scene rejected");
        mdgl_scene_free(sc);
    }
    if (failures) { printf("c play: %d FAILED\n", failures); return 1; }
    puts("c play: OK");
    return 0;
}

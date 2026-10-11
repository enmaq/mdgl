#define _POSIX_C_SOURCE 200809L
/* mdgl command line: check, frames, play. POSIX terminal handling; on Windows play falls back to the
 * plain frame. Exit status: 0 ok, 1 invalid scene, 2 usage or I/O error, 130 interrupted (Ctrl+C). */
#include "mdgl_int.h"
#include "mdgl_play.h"
#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <time.h>
#include <unistd.h>
#endif

#define MAX_SOURCE (256u * 1024u + 1u)

static const char USAGE[] =
    "usage: mdgl check FILE\n"
    "       mdgl frames FILE [--at T1,T2,...]   plain frames at the given seconds (default 0)\n"
    "       mdgl play FILE                      animate in a terminal\n"
    "       mdgl --help | --version\n"
    "FILE may be - for standard input.\n"
    "play: on a terminal, runs the scene at its fps until done (Ctrl+C stops, exit 130). When stdout is\n"
    "not a terminal, or NO_COLOR or MDGL_REDUCED_MOTION is set and non-empty, prints the fallback frame\n"
    "once as plain text.\n"
    "exit status: 0 ok, 1 invalid scene, 2 usage or I/O error, 130 interrupted\n";

static volatile sig_atomic_t g_stop;
static void on_int(int sig) { (void)sig; g_stop = 1; }

static int w_write(void *u, const char *s, size_t n) { (void)u; return fwrite(s, 1, n, stdout) != n || fflush(stdout) != 0; }
static int w_interrupted(void *u) { (void)u; return g_stop; }
#ifndef _WIN32
static double w_now(void *u) { (void)u; struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (double)t.tv_sec + (double)t.tv_nsec / 1e9; }
static void w_sleep(void *u, double s) {
    (void)u;
    struct timespec t = {(time_t)s, (long)((s - floor(s)) * 1e9)};
    nanosleep(&t, NULL);                        /* returns early on SIGINT: the loop then checks the flag */
}
#else
static double w_now(void *u) { (void)u; return (double)clock() / CLOCKS_PER_SEC; }
static void w_sleep(void *u, double s) { (void)u; (void)s; }
#endif

static char *slurp(const char *path, size_t *len) {
    FILE *f = strcmp(path, "-") ? fopen(path, "rb") : stdin;
    if (!f) return NULL;
    char *buf = malloc(MAX_SOURCE + 1);
    size_t n = buf ? fread(buf, 1, MAX_SOURCE, f) : 0;
    int bad = !buf || ferror(f);
    if (f != stdin) fclose(f);
    if (bad) { free(buf); return NULL; }
    buf[n] = 0;                                  /* n == MAX_SOURCE means too large: the library reports it */
    *len = n;
    return buf;
}

static int nonempty_env(const char *name) { const char *v = getenv(name); return v && *v; }

int main(int argc, char **argv) {
    if (argc == 2 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) { fputs(USAGE, stdout); return 0; }
    if (argc == 2 && !strcmp(argv[1], "--version")) { puts("mdgl " MDGL_VERSION); return 0; }
    if (argc < 3 || (strcmp(argv[1], "check") && strcmp(argv[1], "frames") && strcmp(argv[1], "play"))) { fputs(USAGE, stderr); return 2; }
    const char *cmd = argv[1], *path = argv[2], *at = "0";
    if (!strcmp(cmd, "frames") && argc == 5 && !strcmp(argv[3], "--at")) at = argv[4];
    else if (argc != 3) { fputs(USAGE, stderr); return 2; }

    size_t len = 0;
    char *src = slurp(path, &len);
    if (!src) { fprintf(stderr, "mdgl: cannot read %s\n", path); return 2; }
    mdgl_diag_t d;
    mdgl_scene_t *sc = mdgl_parse_n(src, len, &d);
    if (sc && mdgl_scene_check(sc, &d)) { mdgl_scene_free(sc); sc = NULL; }
    free(src);
    if (!sc) { fprintf(stderr, "%s:%d:%d: %s\n", path, d.line, d.col, d.message); return 1; }

    mdgl_play_io_t io = {NULL, w_now, w_write, w_sleep, w_interrupted};
    int status = 0;
    if (!strcmp(cmd, "check")) {
        status = w_write(NULL, "OK MDGL 0.1\n", 12) ? 2 : 0;
    } else if (!strcmp(cmd, "frames")) {
        char *list = strdup(at), *save = NULL;
        for (char *tok = list ? strtok_r(list, ",", &save) : NULL; tok && !status; tok = strtok_r(NULL, ",", &save)) {
            char *e;
            double t = strtod(tok, &e);
            if (*e == 's') e++;
            if (*e || !(t >= 0) || t > 1e12) { fprintf(stderr, "mdgl: invalid frame time %s\n", tok); status = 2; break; }
            mdgl_frame_t f;
            char head[48];
            snprintf(head, sizeof head, "@%g\n", t);
            if (w_write(NULL, head, strlen(head)) || mdgl_frame(sc, t, 200, 60, &f, NULL)) { status = 2; break; }
            for (int r = 0; r < f.height && !status; r++) {
                for (int c = 0; c < f.width; c++) { char u[4]; size_t k = mdgl_i_u8enc(f.cells[r * f.width + c].rune, u); if (w_write(NULL, u, k)) status = 2; }
                if (w_write(NULL, "\n", 1)) status = 2;
            }
            mdgl_frame_free(&f);
        }
        free(list);
    } else {
        int tty = 0;
#ifndef _WIN32
        tty = isatty(STDOUT_FILENO);
#endif
        if (!tty || nonempty_env("NO_COLOR") || nonempty_env("MDGL_REDUCED_MOTION")) {
            status = mdgl_play_plain(sc, &io) ? 2 : 0;
        } else {
#ifndef _WIN32
            struct sigaction sa;
            memset(&sa, 0, sizeof sa);
            sa.sa_handler = on_int;                 /* no SA_RESTART: nanosleep must return */
            sigaction(SIGINT, &sa, NULL);
            sigaction(SIGTERM, &sa, NULL);
            signal(SIGPIPE, SIG_IGN);               /* a closed pipe surfaces as a write error */
#endif
            int rc = mdgl_play(sc, &io);
            status = rc == MDGL_PLAY_OK ? 0 : rc == MDGL_PLAY_INTERRUPTED ? 130 : 2;
            if (rc == MDGL_PLAY_WRITE_ERROR) fprintf(stderr, "mdgl: write error: %s\n", strerror(errno));
        }
    }
    mdgl_scene_free(sc);
    return status;
}

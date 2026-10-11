/* Terminal playback for MDGL scenes: absolute-time frames, dirty-cell diffs, DEC synchronized output.
 * Pure of the process environment: the clock, writer, sleeper and interrupt test are injected, so the
 * same code is driven by a real terminal (mdgl_cli.c) and by deterministic tests. */
#ifndef MDGL_PLAY_H
#define MDGL_PLAY_H

#include "mdgl.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    void *user;
    double (*now)(void *user);                         /* monotonic seconds */
    int (*write)(void *user, const char *s, size_t n); /* 0 ok, nonzero error */
    void (*sleep)(void *user, double seconds);         /* may return early (interrupt) */
    int (*interrupted)(void *user);                    /* nonzero after Ctrl+C; may be NULL */
} mdgl_play_io_t;

#define MDGL_PLAY_OK 0
#define MDGL_PLAY_WRITE_ERROR 1
#define MDGL_PLAY_INTERRUPTED 130

/* Animated playback of a checked scene. Hides the cursor, draws the first frame at t=0, then one frame per
 * 1/fps using elapsed = now() - start (absolute, never accumulated ticks; late ticks drop frames), until
 * the evaluator reports done (infinite repeat runs until interrupted). The terminal is restored (sync
 * mode off, attributes reset, cursor shown, newline) on every path, including write errors. Returns
 * MDGL_PLAY_OK, MDGL_PLAY_WRITE_ERROR or MDGL_PLAY_INTERRUPTED; -1 for an unchecked scene or no memory. */
int mdgl_play(const mdgl_scene_t *scene, const mdgl_play_io_t *io);

/* The plain fallback frame once: rows of text, trailing blanks trimmed, no escape sequences, no timer.
 * Returns MDGL_PLAY_OK, MDGL_PLAY_WRITE_ERROR or -1. */
int mdgl_play_plain(const mdgl_scene_t *scene, const mdgl_play_io_t *io);

#ifdef __cplusplus
}
#endif

#endif

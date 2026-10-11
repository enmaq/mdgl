/* MDGL 0.1 C parser and checker (development tree; VERSION 0.3.0).
 *
 * Implemented: lexing, parsing and semantic checking of scene/actor/action
 * statements, ported from the Go reference (parse + check packages) so that the
 * first diagnostic equals the Go "line:column: message" (one-based UTF-8 byte
 * columns). Evaluator and cells renderer: mdgl_frame* below. NOT implemented yet: the
 * NDJSON conformance adapter. Zero diagnostics means "parses and checks", 
 *
 * Grapheme clusters (1024 limit, text width, type duration) follow rivo/uniseg
 * v0.4.7 = Unicode 15.0.0 UAX29 via generated tables (mdgl_unicode.h, see
 * gen_unicode.py). Decimal parsing is locale independent (README.md). Name quoting in messages uses
 * Go's IsPrint table (exact).
 *
 * Ownership: mdgl_parse_n returns a scene that owns every string, array and
 * value reachable from it (one arena). Free it with mdgl_scene_free exactly
 * once; pointers into it dangle afterwards. The source buffer is never
 * retained. Diagnostics are plain structs the caller owns.
 */
#ifndef MDGL_H
#define MDGL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MDGL_VERSION "0.3.0"
#define MDGL_MAX_DIAGS 16
#define MDGL_MSG_LEN 512

/* ABI notes for this development tree (vs the published 0.2.0 subset):
 * mdgl_diag_t.message is 512 bytes (was 128); mdgl_check* now return 0 or 1
 * diagnostics (first diagnostic, like Go); scene/actor/action structs are new. */

typedef struct {
    int line;
    int col; /* one-based UTF-8 byte column */
    char message[MDGL_MSG_LEN];
} mdgl_diag_t;

typedef struct mdgl_value {
    const char *text; /* NUL-terminated; byte length in len (text may hold NULs if quoted) */
    size_t len;
    int quoted;
    int npair; /* 0 for scalars, 2 or 3 for "(a, b[, c])" */
    const struct mdgl_value *pair;
} mdgl_value_t;

typedef struct {
    const char *key; /* decimal ordinal for positional arguments */
    mdgl_value_t value;
} mdgl_arg_t;

typedef struct {
    int line, col;
    const char *name, *kind;
    mdgl_value_t x, y;
    const mdgl_arg_t *args;
    int nargs;
    const mdgl_arg_t *attrs;
    int nattrs;
    /* filled by mdgl_scene_check */
    const char *color, *parent; /* parent "" when none */
    const char *text;           /* text content or rect title, "" when none */
    double width, height, z;
} mdgl_actor_t;

typedef struct {
    int line, col;
    const char *actor, *verb;
    double begin;
    const mdgl_arg_t *args;
    int nargs;
    /* filled by mdgl_scene_check */
    double duration;
    const char *property, *ease;
} mdgl_action_t;

typedef struct mdgl_scene {
    int line, col;
    const mdgl_arg_t *attrs;
    int nattrs;
    mdgl_actor_t *actors;
    int nactors;
    mdgl_action_t *actions;
    int nactions;
    /* filled by mdgl_scene_check */
    int checked, width, height, fps;
    double period;
    int explicit_period;
    int repeat; /* 0 = infinite */
    const char *fallback;
    void *arena_; /* private */
} mdgl_scene_t;

/* Parse (lexical + syntactic, with the Go parser's limits). Returns a scene, or
 * NULL with *diag filled (also NULL with "out of memory"). */
mdgl_scene_t *mdgl_parse_n(const char *source, size_t len, mdgl_diag_t *diag);

/* Semantic check, in place. Returns 0 (checked, derived fields valid) or 1 with
 * *diag filled. Idempotent. */
int mdgl_scene_check(mdgl_scene_t *scene, mdgl_diag_t *diag);

void mdgl_scene_free(mdgl_scene_t *scene); /* NULL ok */

/* One extended grapheme cluster step (rivo/uniseg StepString semantics). *state starts at -1 and is
 * opaque. Returns the cluster length in bytes (0 when n==0) and its terminal width in *width. */
size_t mdgl_grapheme_step(const char *s, size_t n, int *state, int *width);

/* ---- evaluator + terminal cells (mdgl_render.c); scene must be checked ---- */
typedef struct {
    uint32_t rune;  /* one Unicode scalar; U+FFFD for wide graphemes */
    char fg[8];     /* "normal", a SPEC colour name, or blended "#rrggbb" */
    char bg[8];     /* "" = default black */
} mdgl_cell_t;
typedef struct { int width, height; mdgl_cell_t *cells; /* row-major, owned: mdgl_frame_free */ } mdgl_frame_t;

/* Pure, seekable. Time in seconds / nanoseconds (rounded to ns). *done may be NULL. Returns 0 or -1
 * (unchecked scene, bad args, out of memory). Size is min(request, scene size). */
int mdgl_frame(const mdgl_scene_t *scene, double seconds, int cols, int rows, mdgl_frame_t *out, int *done);
int mdgl_frame_ns(const mdgl_scene_t *scene, long long ns, int cols, int rows, mdgl_frame_t *out, int *done);
int mdgl_fallback_frame(const mdgl_scene_t *scene, int cols, int rows, mdgl_frame_t *out);
int mdgl_scene_active(const mdgl_scene_t *scene, double seconds); /* 1 while the timeline still plays */
void mdgl_frame_free(mdgl_frame_t *frame); /* NULL ok; frees cells only */

/* Parse + check of a NUL-terminated source (NULL = empty). Returns the number
 * of diagnostics written into `out` (0 = valid, 1 = first diagnostic like Go),
 * or -1 when out==0 or ndiags<=0. */
int mdgl_check(const char *source, mdgl_diag_t *out, int ndiags);

/* Same, for a buffer of explicit length (may contain NUL bytes). */
int mdgl_check_n(const char *source, size_t len, mdgl_diag_t *out, int ndiags);

#ifdef __cplusplus
}
#endif

#endif

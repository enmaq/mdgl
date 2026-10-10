/* MDGL 0.0.1 -- SUBSET limit/header checker. NOT a conformant MDGL implementation.
 *
 * Checks only: input <= 256 KiB, line <= 16 KiB, scene header (width 1..200,
 * height 1..60, fallback; no unknown/duplicate keys), statement order,
 * <= 64 actors, <= 1024 actions. Does NOT parse actor/action bodies or check
 * grammar, timing, references or rendering. Zero diagnostics means
 * "no limit/header problems found", NOT "valid MDGL". Reference: the Go module.
 * Raw-byte UTF-8 validity is NOT checked. C has no central registry: this is
 * distributed as a source tarball only (see README.md).
 */
#ifndef MDGL_H
#define MDGL_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MDGL_VERSION "0.2.0"
#define MDGL_MAX_DIAGS 16
#define MDGL_MSG_LEN 128

typedef struct {
    int line;
    int col;
    char message[MDGL_MSG_LEN];
} mdgl_diag_t;

/* Subset check of a NUL-terminated source (NULL = empty). Returns the number
 * of diagnostics written into `out` (0 = no limit/header problems found), or
 * -1 when out==0 or ndiags<=0. Writes at most MDGL_MAX_DIAGS entries. */
int mdgl_check(const char *source, mdgl_diag_t *out, int ndiags);

/* Same, for a buffer of explicit length (may contain NUL bytes). */
int mdgl_check_n(const char *source, size_t len, mdgl_diag_t *out, int ndiags);

#ifdef __cplusplus
}
#endif

#endif

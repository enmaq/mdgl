/* Allocation-failure injection: fail the Nth malloc/calloc (linker --wrap) and require a clean
 * "out of memory" diagnostic or a valid result, no crash, and no leak under LeakSanitizer. */
#include "mdgl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static long countdown = -1;
void *__real_malloc(size_t n);
void *__real_calloc(size_t a, size_t b);
void *__wrap_malloc(size_t n) { if (countdown >= 0 && countdown-- == 0) return NULL; return __real_malloc(n); }
void *__wrap_calloc(size_t a, size_t b) { if (countdown >= 0 && countdown-- == 0) return NULL; return __real_calloc(a, b); }

int main(void) {
    static const char *src =
        "scene width=8 height=1 fallback=end\nactor a = text(\"hello\") at (0, 0)\nactor b = circle(2) at (center, 1) parent=a color=red\n"
        "@0: a.fade(in, dur=1)\n@1: b.move(to=(1,0), dur=1)\n@2: a.type(per_char=0.1)\n";
    int oom = 0, ok = 0, bad = 0;
    for (long n = 0; n < 400; n++) {
        mdgl_diag_t d;
        countdown = n;
        int r = mdgl_check_n(src, strlen(src), &d, 1);
        long left = countdown;
        countdown = -1;
        if (r == 0) { ok++; if (left < 0) {} }
        else if (!strcmp(d.message, "out of memory") || strstr(d.message, "out of memory")) oom++;
        else { printf("FAIL n=%ld: unexpected diagnostic %d:%d %s\n", n, d.line, d.col, d.message); bad++; }
        if (r == 0 && left >= 0) break; /* injection point beyond the last allocation: done */
    }
    if (!oom || bad) { printf("FAIL oom: %d oom, %d unexpected\n", oom, bad); return 1; }
    printf("c oom: OK (%d injected failures survived, %d completed)\n", oom, ok);
    return 0;
}

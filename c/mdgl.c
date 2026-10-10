/* MDGL 0.0.1 subset limit/header check. See mdgl.h. Not a conformant implementation. */
#include "mdgl.h"
#include <stdio.h>
#include <string.h>

#define MAX_INPUT (256u * 1024u)
#define MAX_LINE 16384u
#define MAX_ACTORS 64
#define MAX_ACTIONS 1024

typedef struct { mdgl_diag_t *out; int cap, n; } sink_t;

static void emit(sink_t *s, int line, const char *fmt, const char *a, int b) {
    if (s->n >= s->cap || s->n >= MDGL_MAX_DIAGS) return;
    mdgl_diag_t *d = &s->out[s->n++];
    d->line = line;
    d->col = 1;
    snprintf(d->message, MDGL_MSG_LEN, fmt, a, b);
}

static int is_ws(char c) { return c == ' ' || c == '\t' || c == '\r'; }

/* Scene header: p..e is the text after "scene". Returns 0 ok, 1 diagnosed. */
static int scene_header(sink_t *s, int n, const char *p, const char *e) {
    static const char *keys[] = {"width", "height", "period", "repeat", "fallback", "fps"};
    int seen[6] = {0, 0, 0, 0, 0, 0};
    long val[2] = {-1, -1}; /* width, height */
    while (p < e) {
        while (p < e && is_ws(*p)) p++;
        if (p >= e) break;
        const char *t = p;
        while (p < e && !is_ws(*p)) p++;
        const char *eq = memchr(t, '=', (size_t)(p - t));
        if (!eq || eq == t || eq + 1 == p) { emit(s, n, "malformed scene attribute%s%d", "", 0); return 1; }
        size_t kl = (size_t)(eq - t);
        int k = -1;
        for (int i = 0; i < 6; i++)
            if (strlen(keys[i]) == kl && memcmp(keys[i], t, kl) == 0) k = i;
        if (k < 0) { emit(s, n, "unknown scene attribute%s%d", "", 0); return 1; }
        if (seen[k]) { emit(s, n, "duplicate scene attribute %s%d", keys[k], 0); return 1; }
        seen[k] = 1;
        if (k == 0 || k == 1) {
            long v = 0; int ok = 1; const char *q = eq + 1;
            if (p - q > 9) ok = 0;
            for (; ok && q < p; q++) { if (*q < '0' || *q > '9') ok = 0; else v = v * 10 + (*q - '0'); }
            val[k] = ok ? v : 0;
        }
    }
    int bad = 0;
    if (!seen[0]) { emit(s, n, "scene header missing %s%d", "width=", 0); bad = 1; }
    if (!seen[1]) { emit(s, n, "scene header missing %s%d", "height=", 0); bad = 1; }
    if (!seen[4]) { emit(s, n, "scene header missing %s%d", "fallback=", 0); bad = 1; }
    if (bad) return 1;
    if (val[0] < 1 || val[0] > 200) { emit(s, n, "%s must be an integer 1..%d", "width", 200); return 1; }
    if (val[1] < 1 || val[1] > 60) { emit(s, n, "%s must be an integer 1..%d", "height", 60); return 1; }
    return 0;
}

int mdgl_check_n(const char *source, size_t len, mdgl_diag_t *out, int ndiags) {
    if (!out || ndiags <= 0) return -1;
    sink_t s = {out, ndiags, 0};
    if (!source) { source = ""; len = 0; }
    if (len > MAX_INPUT) { emit(&s, 1, "input exceeds 256 KiB%s%d", "", 0); return s.n; }
    int scene = 0, action = 0, version = 0, actors = 0, actions = 0, n = 0;
    const char *p = source, *end = source + len;
    for (;;) {
        n++;
        const char *nl = memchr(p, '\n', (size_t)(end - p));
        const char *le = nl ? nl : end;
        if ((size_t)(le - p) > MAX_LINE) { emit(&s, n, "line exceeds 16 KiB%s%d", "", 0); return s.n; }
        const char *a = p, *b = le;
        while (a < b && is_ws(*a)) a++;
        while (b > a && is_ws(b[-1])) b--;
        if (a < b && *a != '#') {
            const char *he = a;
            if (*a == '@') he = a + 1; else while (he < b && *he != ' ' && *he != '\t') he++;
            size_t hl = (size_t)(he - a);
            if (hl == 4 && !memcmp(a, "mdgl", 4)) {
                const char *r = a + 4, *re = b;
                while (r < re && is_ws(*r)) r++;
                if (scene || version || re - r != 3 || memcmp(r, "0.1", 3)) {
                    emit(&s, n, "expected initial mdgl 0.1%s%d", "", 0); return s.n;
                }
                version = 1;
            } else if (hl == 5 && !memcmp(a, "scene", 5)) {
                if (scene) { emit(&s, n, "duplicate scene%s%d", "", 0); return s.n; }
                scene = 1;
                if (scene_header(&s, n, a + 5, b)) return s.n;
            } else if (hl == 5 && !memcmp(a, "actor", 5)) {
                if (!scene) { emit(&s, n, "scene must precede actors%s%d", "", 0); return s.n; }
                if (action) { emit(&s, n, "actors must precede actions%s%d", "", 0); return s.n; }
                if (++actors > MAX_ACTORS) { emit(&s, n, "actor limit 64 exceeded%s%d", "", 0); return s.n; }
            } else if (hl == 1 && *a == '@') {
                if (!scene) { emit(&s, n, "scene must precede actions%s%d", "", 0); return s.n; }
                action = 1;
                if (++actions > MAX_ACTIONS) { emit(&s, n, "action limit 1024 exceeded%s%d", "", 0); return s.n; }
            } else {
                emit(&s, n, "unsupported statement (expected mdgl, scene, actor or @)%s%d", "", 0);
                return s.n;
            }
        }
        if (!nl) break;
        p = nl + 1;
    }
    if (!scene) emit(&s, 1, "missing scene%s%d", "", 0);
    return s.n;
}

int mdgl_check(const char *source, mdgl_diag_t *out, int ndiags) {
    return mdgl_check_n(source, source ? strlen(source) : 0, out, ndiags);
}

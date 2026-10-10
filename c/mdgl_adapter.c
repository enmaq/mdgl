/* MDGL conformance adapter, protocol v1 (conformance/PROTOCOL.md): newline-delimited JSON on stdin,
 * exactly one newline-terminated JSON response per request on stdout. C99, no dependencies beyond the
 * MDGL library. Stateless: every request is a pure function of its fields. */
#include "mdgl.h"
#include "mdgl_int.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_LINE 2097152u
#define MAX_DEPTH 256

/* ---------- growable output buffer ---------- */
typedef struct { char *b; size_t n, cap; int oom; } out_t;
static void o_add(out_t *o, const char *s, size_t n) {
    if (o->oom) return;
    if (o->n + n + 1 > o->cap) {
        size_t nc = o->cap ? o->cap : 4096;
        while (nc < o->n + n + 1) nc *= 2;
        char *nb = realloc(o->b, nc);
        if (!nb) { o->oom = 1; return; }
        o->b = nb; o->cap = nc;
    }
    memcpy(o->b + o->n, s, n);
    o->n += n;
    o->b[o->n] = 0;
}
static void o_s(out_t *o, const char *s) { o_add(o, s, strlen(s)); }
/* JSON string body for UTF-8 bytes; invalid sequences become U+FFFD. */
static void o_str(out_t *o, const char *s, size_t n) {
    char t[8];
    o_s(o, "\"");
    for (size_t i = 0; i < n;) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { t[0] = '\\'; t[1] = (char)c; o_add(o, t, 2); i++; }
        else if (c < 0x20) { snprintf(t, sizeof t, "\\u%04x", c); o_add(o, t, 6); i++; }
        else if (c < 0x80) { o_add(o, s + i, 1); i++; }
        else {
            uint32_t r;
            int w = mdgl_i_u8dec((const unsigned char *)s + i, n - i, &r);
            if (r == 0xFFFD && !(w == 3 && (unsigned char)s[i] == 0xEF)) o_s(o, "\xEF\xBF\xBD"); else o_add(o, s + i, (size_t)w);
            i += (size_t)w;
        }
    }
    o_s(o, "\"");
}

/* ---------- strict JSON reader ---------- */
typedef struct { const unsigned char *p, *e; int depth; int err; } jr_t;
typedef struct { int present, type; char *s; size_t n; int lone; } fld_t; /* type: 1 string 2 number 3 bool 4 other */
enum { T_STR = 1, T_NUM, T_BOOL, T_OTHER };

static void ws(jr_t *j) { while (j->p < j->e && (*j->p == ' ' || *j->p == '\t' || *j->p == '\r' || *j->p == '\n')) j->p++; }
static int hex4(const unsigned char *p, uint32_t *v) {
    *v = 0;
    for (int i = 0; i < 4; i++) {
        int c = p[i], d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0) return 0;
        *v = *v << 4 | (uint32_t)d;
    }
    return 1;
}
/* Parses a string at '"'. store!=0: decoded bytes in *out (malloc, NUL-terminated). Lone surrogates set *lone. */
static int jstring(jr_t *j, int store, char **out, size_t *outn, int *lone) {
    j->p++;
    size_t cap = (size_t)(j->e - j->p) + 1, n = 0;
    char *buf = store ? malloc(cap) : NULL;
    if (store && !buf) { j->err = 2; return 0; }
    if (lone) *lone = 0;
    while (j->p < j->e) {
        unsigned char c = *j->p;
        if (c == '"') {
            j->p++;
            if (store) { buf[n] = 0; *out = buf; *outn = n; }
            return 1;
        }
        if (c < 0x20) break;
        if (c == '\\') {
            if (j->e - j->p < 2) break;
            unsigned char d = j->p[1];
            uint32_t r = 0;
            j->p += 2;
            switch (d) {
            case '"': r = '"'; break; case '\\': r = '\\'; break; case '/': r = '/'; break; case 'b': r = 8; break;
            case 'f': r = 12; break; case 'n': r = 10; break; case 'r': r = 13; break; case 't': r = 9; break;
            case 'u': {
                uint32_t hi;
                if (j->e - j->p < 4 || !hex4(j->p, &hi)) goto bad;
                j->p += 4;
                if (hi >= 0xD800 && hi <= 0xDBFF) {
                    uint32_t lo;
                    if (j->e - j->p >= 6 && j->p[0] == '\\' && j->p[1] == 'u' && hex4(j->p + 2, &lo) && lo >= 0xDC00 && lo <= 0xDFFF) {
                        j->p += 6;
                        r = 0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00);
                    } else { r = 0xFFFD; if (lone) *lone = 1; }
                } else if (hi >= 0xDC00 && hi <= 0xDFFF) { r = 0xFFFD; if (lone) *lone = 1; }
                else r = hi;
                break;
            }
            default: goto bad;
            }
            if (store) n += mdgl_i_u8enc(r, buf + n);
            continue;
        }
        if (c >= 0x80) {
            uint32_t r;
            int w = mdgl_i_u8dec(j->p, (size_t)(j->e - j->p), &r);
            if (r == 0xFFFD && !(w == 3 && j->p[0] == 0xEF)) goto bad; /* invalid UTF-8 */
            if (store) memcpy(buf + n, j->p, (size_t)w), n += (size_t)w;
            j->p += w;
            continue;
        }
        if (store) buf[n++] = (char)c;
        j->p++;
    }
bad:
    free(buf);
    if (!j->err) j->err = 1;
    return 0;
}
static int isd(int c) { return c >= '0' && c <= '9'; }
/* Validates a number per RFC 8259; lexeme copied if store. */
static int jnumber(jr_t *j, int store, char **out, size_t *outn) {
    const unsigned char *s = j->p;
    if (j->p < j->e && *j->p == '-') j->p++;
    if (j->p >= j->e || !isd(*j->p)) goto bad;
    if (*j->p == '0') j->p++; else while (j->p < j->e && isd(*j->p)) j->p++;
    if (j->p < j->e && *j->p == '.') { j->p++; if (j->p >= j->e || !isd(*j->p)) goto bad; while (j->p < j->e && isd(*j->p)) j->p++; }
    if (j->p < j->e && (*j->p == 'e' || *j->p == 'E')) {
        j->p++;
        if (j->p < j->e && (*j->p == '+' || *j->p == '-')) j->p++;
        if (j->p >= j->e || !isd(*j->p)) goto bad;
        while (j->p < j->e && isd(*j->p)) j->p++;
    }
    if (store) {
        *outn = (size_t)(j->p - s);
        *out = malloc(*outn + 1);
        if (!*out) { j->err = 2; return 0; }
        memcpy(*out, s, *outn); (*out)[*outn] = 0;
    }
    return 1;
bad:
    if (!j->err) j->err = 1;
    return 0;
}
static int jvalue(jr_t *j, fld_t *f);
static int jskip_container(jr_t *j) {
    int obj = *j->p == '{';
    if (++j->depth > MAX_DEPTH) { j->err = 1; return 0; }
    j->p++;
    ws(j);
    if (j->p < j->e && *j->p == (obj ? '}' : ']')) { j->p++; j->depth--; return 1; }
    for (;;) {
        ws(j);
        if (obj) {
            if (j->p >= j->e || *j->p != '"' || !jstring(j, 0, NULL, NULL, NULL)) { if (!j->err) j->err = 1; return 0; }
            ws(j);
            if (j->p >= j->e || *j->p != ':') { j->err = 1; return 0; }
            j->p++;
        }
        if (!jvalue(j, NULL)) return 0;
        ws(j);
        if (j->p < j->e && *j->p == ',') { j->p++; continue; }
        if (j->p < j->e && *j->p == (obj ? '}' : ']')) { j->p++; j->depth--; return 1; }
        j->err = 1;
        return 0;
    }
}
/* Any JSON value; scalars are captured in *f (strings/numbers only when f != NULL). */
static int jvalue(jr_t *j, fld_t *f) {
    ws(j);
    if (j->p >= j->e) { j->err = 1; return 0; }
    unsigned char c = *j->p;
    fld_t skip;                 /* f == NULL: validate only, store nothing */
    if (!f) { memset(&skip, 0, sizeof skip); f = &skip; }
    int keep = f != &skip;
    f->present = 1;
    if (c == '"') { f->type = T_STR; return jstring(j, keep, &f->s, &f->n, &f->lone); }
    if (c == '-' || isd(c)) { f->type = T_NUM; return jnumber(j, keep, &f->s, &f->n); }
    if (c == '{' || c == '[') { f->type = T_OTHER; return jskip_container(j); }
    if (j->e - j->p >= 4 && !memcmp(j->p, "true", 4)) { j->p += 4; f->type = T_BOOL; f->n = 1; return 1; }
    if (j->e - j->p >= 5 && !memcmp(j->p, "false", 5)) { j->p += 5; f->type = T_BOOL; f->n = 0; return 1; }
    if (j->e - j->p >= 4 && !memcmp(j->p, "null", 4)) { j->p += 4; f->type = T_OTHER; return 1; }
    j->err = 1;
    return 0;
}

enum { F_V, F_ID, F_OP, F_SOURCE, F_TIME, F_WIDTH, F_HEIGHT, F_FALLBACK, F_N };
static const char *const FN[F_N] = {"v", "id", "op", "source", "time_ns", "width", "height", "fallback"};
static void f_free(fld_t *f) { free(f->s); memset(f, 0, sizeof *f); }

/* Whole line: must be exactly one object. Known members land in fl[]; later duplicates replace earlier. */
static int parse_request(const unsigned char *line, size_t n, fld_t *fl, int *err) {
    jr_t j = {line, line + n, 0, 0};
    ws(&j);
    if (j.p >= j.e || *j.p != '{') { *err = j.err ? j.err : 1; return 0; }
    j.p++; j.depth = 1;
    ws(&j);
    if (j.p < j.e && *j.p == '}') j.p++;
    else for (;;) {
        char *key = NULL; size_t kn = 0; int lone;
        ws(&j);
        if (j.p >= j.e || *j.p != '"' || !jstring(&j, 1, &key, &kn, &lone)) { *err = j.err ? j.err : 1; return 0; }
        ws(&j);
        if (j.p >= j.e || *j.p != ':') { free(key); *err = 1; return 0; }
        j.p++;
        int which = -1;
        for (int i = 0; i < F_N; i++) if (strlen(FN[i]) == kn && !memcmp(FN[i], key, kn) && !lone) which = i;
        free(key);
        fld_t tmp;
        memset(&tmp, 0, sizeof tmp);
        if (!jvalue(&j, &tmp)) { f_free(&tmp); *err = j.err; return 0; }
        if (which >= 0) { f_free(&fl[which]); fl[which] = tmp; } else f_free(&tmp);
        ws(&j);
        if (j.p < j.e && *j.p == ',') { j.p++; continue; }
        if (j.p < j.e && *j.p == '}') { j.p++; break; }
        *err = 1;
        return 0;
    }
    ws(&j);
    if (j.p != j.e) { *err = 1; return 0; }
    return 1;
}

/* Exact integer test of a JSON number lexeme, lossless for any length (the line cap bounds it).
 * Returns 1 if mathematically integral (sets *neg, and *mag when the value fits in 19 digits, else
 * *big=1), 0 if it has a fractional part. "-0", "0.0", "0e-100000" are zero; "5." followed by 100
 * zeros is 5; "1e-100000" is fractional. Digits are not truncated: only the first 19 significant
 * digits are kept, but trailing zeros are counted exactly, so a nonzero digit anywhere (however far)
 * makes the effective scale negative. The exponent saturates near 1e8 (fits a 32-bit long: exp*10+9 < 2^31), far beyond any representable
 * magnitude, so no overflow. */
static int exact_int(const char *s, size_t n, int *neg, unsigned long long *mag, int *big) {
    size_t i = 0;
    char digits[24];
    size_t kept = 0, total = 0, run0 = 0, fracs = 0;
    long exp = 0;
    int seen_nz = 0;
    *neg = 0; *mag = 0; *big = 0;
    if (i < n && s[i] == '-') { *neg = 1; i++; }
    for (; i < n && isd(s[i]); i++) {
        if (s[i] != '0') seen_nz = 1;
        if (!seen_nz) continue;
        if (kept < sizeof digits) digits[kept++] = s[i];
        total++;
        run0 = s[i] == '0' ? run0 + 1 : 0;
    }
    if (i < n && s[i] == '.') {
        for (i++; i < n && isd(s[i]); i++, fracs++) {
            if (s[i] != '0') seen_nz = 1;
            if (!seen_nz) continue;
            if (kept < sizeof digits) digits[kept++] = s[i];
            total++;
            run0 = s[i] == '0' ? run0 + 1 : 0;
        }
    }
    if (i < n && (s[i] == 'e' || s[i] == 'E')) {
        int es = 1;
        i++;
        if (s[i] == '+') i++; else if (s[i] == '-') { es = -1; i++; }
        for (; i < n; i++) if (exp < 100000000L) exp = exp * 10 + (s[i] - '0');
        exp *= es;
    }
    if (!seen_nz) { *neg = 0; return 1; } /* zero, whatever its spelling */
    long sig = (long)(total - run0), scale = exp - (long)fracs + (long)run0;
    if (scale < 0) return 0;
    if (sig + scale > 19) { *big = 1; return 1; }
    unsigned long long v = 0;
    for (long k = 0; k < sig; k++) v = v * 10 + (unsigned)(digits[k] - '0'); /* sig <= 19 <= kept */
    for (long k = 0; k < scale; k++) v *= 10;
    *mag = v;
    return 1;
}
static int int_in(const fld_t *f, long lo, long hi, long *out) {
    int neg, big;
    unsigned long long m;
    if (f->type != T_NUM || !exact_int(f->s, f->n, &neg, &m, &big) || big) return 0;
    if (neg && m) return 0;
    if (m < (unsigned long long)lo || m > (unsigned long long)hi) return 0;
    *out = (long)m;
    return 1;
}

/* ---------- responses ---------- */
static void head(out_t *o, const fld_t *id) {
    o_s(o, "{\"v\":1,\"id\":");
    if (id && id->present && id->type == T_STR && !id->lone) o_str(o, id->s, id->n); else o_s(o, "null");
}
static void fail(out_t *o, const fld_t *id, const char *code, const char *msg) {
    head(o, id);
    o_s(o, ",\"ok\":false,\"error\":{\"code\":\""); o_s(o, code); o_s(o, "\",\"message\":"); o_str(o, msg, strlen(msg)); o_s(o, "}}");
}
static void diag_json(out_t *o, const mdgl_diag_t *d) {
    char t[48];
    snprintf(t, sizeof t, "{\"line\":%d,\"col\":%d,\"message\":", d->line, d->col);
    o_s(o, t); o_str(o, d->message, strlen(d->message)); o_s(o, "}");
}
static void cell_json(out_t *o, const mdgl_cell_t *c) {
    char r[5];
    size_t n = mdgl_i_u8enc(c->rune, r);
    o_s(o, "{\"r\":"); o_str(o, r, n); o_s(o, ",\"fg\":"); o_str(o, c->fg, strlen(c->fg)); o_s(o, ",\"bg\":"); o_str(o, c->bg, strlen(c->bg)); o_s(o, "}");
}

static void handle(const unsigned char *line, size_t n, out_t *o) {
    fld_t fl[F_N];
    int err = 0;
    memset(fl, 0, sizeof fl);
    if (!parse_request(line, n, fl, &err)) {
        if (err == 2) fail(o, NULL, "internal", "out of memory");
        else fail(o, NULL, "bad_request", "malformed JSON request (top level must be a JSON object)");
        goto done;
    }
    {
        const fld_t *id = &fl[F_ID];
        int neg, big;
        unsigned long long m;
        if (!fl[F_V].present || fl[F_V].type != T_NUM || !exact_int(fl[F_V].s, fl[F_V].n, &neg, &m, &big)) { fail(o, id, "bad_request", "v must be an integer"); goto done; }
        if (big || neg || m != 1) { fail(o, id, "unsupported_version", "protocol version is not supported"); goto done; }
        if (!fl[F_OP].present || fl[F_OP].type != T_STR || fl[F_OP].lone) { fail(o, id, "bad_request", "op must be \"check\" or \"frame\""); goto done; }
        int is_check = fl[F_OP].n == 5 && !memcmp(fl[F_OP].s, "check", 5), is_frame = fl[F_OP].n == 5 && !memcmp(fl[F_OP].s, "frame", 5);
        if (!is_check && !is_frame) { fail(o, id, "bad_request", "unknown op"); goto done; }
        if (!id->present || id->type != T_STR || id->lone) { fail(o, NULL, "bad_request", "id must be a string"); goto done; }
        if (!fl[F_SOURCE].present || fl[F_SOURCE].type != T_STR || fl[F_SOURCE].lone) { fail(o, id, "bad_request", "source must be a string without lone surrogates"); goto done; }
        long ns = 0, width = 0, height = 0;
        int fallback = 0;
        if (is_frame) {
            if (fl[F_FALLBACK].present) {
                if (fl[F_FALLBACK].type != T_BOOL) { fail(o, id, "bad_request", "fallback must be a boolean"); goto done; }
                fallback = (int)fl[F_FALLBACK].n;
            }
            if (!fallback) {
                const fld_t *t = &fl[F_TIME];
                int tn, tb;
                unsigned long long tm;
                if (!t->present || t->type != T_NUM || !exact_int(t->s, t->n, &tn, &tm, &tb) || tb || (tn && tm) || tm > 9007199254740991ULL) {
                    fail(o, id, "bad_request", "time_ns must be an integer in 0..2^53-1"); goto done;
                }
                ns = (long)tm;
            }
            if (!int_in(&fl[F_WIDTH], 1, 200, &width)) { fail(o, id, "bad_request", "width must be an integer in 1..200"); goto done; }
            if (!int_in(&fl[F_HEIGHT], 1, 60, &height)) { fail(o, id, "bad_request", "height must be an integer in 1..60"); goto done; }
        }
        mdgl_diag_t d;
        mdgl_scene_t *sc = mdgl_parse_n(fl[F_SOURCE].s, fl[F_SOURCE].n, &d);
        int bad = sc ? mdgl_scene_check(sc, &d) : 1;
        if (is_check) {
            head(o, id);
            o_s(o, ",\"ok\":true,\"diagnostics\":[");
            if (bad) diag_json(o, &d);
            o_s(o, "]}");
        } else if (bad) {
            head(o, id);
            o_s(o, ",\"ok\":false,\"error\":{\"code\":\"invalid_source\",\"message\":\"source has diagnostics\",\"diagnostics\":[");
            diag_json(o, &d);
            o_s(o, "]}}");
        } else {
            mdgl_frame_t fr;
            int dn = 0, rc = fallback ? mdgl_fallback_frame(sc, (int)width, (int)height, &fr) : mdgl_frame_ns(sc, ns, (int)width, (int)height, &fr, &dn);
            if (rc) fail(o, id, "internal", "frame failed");
            else {
                char t[64];
                head(o, id);
                snprintf(t, sizeof t, ",\"ok\":true,\"width\":%d,\"height\":%d,\"cells\":[", fr.width, fr.height);
                o_s(o, t);
                for (int r = 0; r < fr.height; r++) {
                    if (r) o_s(o, ",");
                    o_s(o, "[");
                    for (int c = 0; c < fr.width; c++) { if (c) o_s(o, ","); cell_json(o, &fr.cells[r * fr.width + c]); }
                    o_s(o, "]");
                }
                o_s(o, "]");
                if (!fallback) o_s(o, dn ? ",\"done\":true" : ",\"done\":false");
                o_s(o, "}");
                mdgl_frame_free(&fr);
            }
        }
        mdgl_scene_free(sc);
    }
done:
    for (int i = 0; i < F_N; i++) f_free(&fl[i]);
}

static void respond(out_t *o) {
    if (o->oom) { o->n = 0; if (o->b) o->b[0] = 0; o_s(o, "{\"v\":1,\"id\":null,\"ok\":false,\"error\":{\"code\":\"internal\",\"message\":\"out of memory\"}}"); o->oom = 0; }
    o_add(o, "\n", 1);
    fwrite(o->b, 1, o->n, stdout);
    fflush(stdout);
    o->n = 0;
}

int main(void) {
    unsigned char *buf = malloc(MAX_LINE + 1);
    out_t o = {0};
    if (!buf) return 1;
    for (;;) {
        size_t n = 0;
        int c, toolong = 0, any = 0;
        while ((c = getc(stdin)) != EOF && c != '\n') {
            any = 1;
            if (n < MAX_LINE) buf[n++] = (unsigned char)c; else toolong = 1;
        }
        if (c == EOF && !any) break; /* the empty final segment is not a request */
        if (toolong) fail(&o, NULL, "bad_request", "request line exceeds 2097152 bytes");
        else {
            size_t i = 0;
            while (i < n && (buf[i] == ' ' || buf[i] == '\t' || buf[i] == '\r')) i++;
            if (i == n) fail(&o, NULL, "bad_request", "blank request line");
            else handle(buf, n, &o);
        }
        respond(&o);
        if (c == EOF) break;
    }
    free(buf); free(o.b);
    return 0;
}

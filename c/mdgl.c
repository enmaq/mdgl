/* MDGL 0.1 parser and checker, ported from the Go reference. See mdgl.h. */
#include "mdgl.h"
#include "mdgl_unicode.h"
#include "mdgl_int.h"
#include <math.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <locale.h>
#include <stdlib.h>
#include <string.h>

#define MAX_INPUT (256u * 1024u)
#define MAX_LINE 16384u
#define MAX_ACTORS 64
#define MAX_ACTIONS 1024

/* ---------- message builder, arena, error plumbing ---------- */

typedef struct { char b[MDGL_MSG_LEN]; size_t n; } sb_t;
typedef struct chunk { struct chunk *next; union { double d; long long l; void *p; } al; } chunk_t;
typedef struct { chunk_t *chunks; jmp_buf jb; int can_jump; mdgl_diag_t *diag; sb_t m; void *toks; } P;

static void sb_add(sb_t *s, const char *t, size_t n) {
    if (n > MDGL_MSG_LEN - 1 - s->n) n = MDGL_MSG_LEN - 1 - s->n;
    memcpy(s->b + s->n, t, n);
    s->n += n;
    s->b[s->n] = 0;
}
static void sb_s(sb_t *s, const char *t) { sb_add(s, t, strlen(t)); }
static void sb_i(sb_t *s, long v) { char t[32]; snprintf(t, sizeof t, "%ld", v); sb_s(s, t); }

static void *ar_alloc(P *p, size_t n) {
    chunk_t *c = malloc(sizeof *c + n);
    if (!c) {
        if (p->can_jump) longjmp(p->jb, 1);
        return NULL;
    }
    c->next = p->chunks;
    p->chunks = c;
    return c + 1;
}
static char *ar_dup(P *p, const char *s, size_t n) {
    char *d = ar_alloc(p, n + 1);
    if (n) memcpy(d, s, n);
    d[n] = 0;
    return d;
}
static void ar_free(chunk_t *c) {
    while (c) { chunk_t *n = c->next; free(c); c = n; }
}

static int ferr(P *p, int line, int col) {
    p->diag->line = line;
    p->diag->col = col;
    memcpy(p->diag->message, p->m.b, p->m.n + 1);
    return 0;
}
static int ferr_s(P *p, int line, int col, const char *msg) {
    p->m.n = 0; p->m.b[0] = 0;
    sb_s(&p->m, msg);
    return ferr(p, line, col);
}
static void m_reset(P *p) { p->m.n = 0; p->m.b[0] = 0; }

/* ---------- UTF-8 (Go semantics) ---------- */

int mdgl_i_u8dec(const unsigned char *s, size_t n, uint32_t *r) {
    if (n == 0) { *r = 0xFFFD; return 0; }
    unsigned c = s[0];
    if (c < 0x80) { *r = c; return 1; }
    if (c >= 0xC2 && c <= 0xDF && n >= 2 && (s[1] & 0xC0) == 0x80) { *r = ((c & 0x1F) << 6) | (s[1] & 0x3F); return 2; }
    if (c >= 0xE0 && c <= 0xEF && n >= 3 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) {
        uint32_t v = ((c & 0x0F) << 12) | ((s[1] & 0x3Fu) << 6) | (s[2] & 0x3F);
        if (v >= 0x800 && (v < 0xD800 || v > 0xDFFF)) { *r = v; return 3; }
    }
    if (c >= 0xF0 && c <= 0xF4 && n >= 4 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80 && (s[3] & 0xC0) == 0x80) {
        uint32_t v = ((c & 0x07u) << 18) | ((s[1] & 0x3Fu) << 12) | ((s[2] & 0x3Fu) << 6) | (s[3] & 0x3F);
        if (v >= 0x10000 && v <= 0x10FFFF) { *r = v; return 4; }
    }
    *r = 0xFFFD;
    return 1; /* invalid: width 1 */
}
static int u8valid(const char *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        uint32_t r;
        int w = mdgl_i_u8dec((const unsigned char *)s + i, n - i, &r);
        if (w == 1 && r == 0xFFFD && (unsigned char)s[i] >= 0x80) return 0;
        i += (size_t)w;
    }
    return 1;
}
size_t mdgl_i_u8enc(uint32_t r, char *o) {
    if (r < 0x80) { o[0] = (char)r; return 1; }
    if (r < 0x800) { o[0] = (char)(0xC0 | r >> 6); o[1] = (char)(0x80 | (r & 0x3F)); return 2; }
    if (r < 0x10000) { o[0] = (char)(0xE0 | r >> 12); o[1] = (char)(0x80 | ((r >> 6) & 0x3F)); o[2] = (char)(0x80 | (r & 0x3F)); return 3; }
    o[0] = (char)(0xF0 | r >> 18); o[1] = (char)(0x80 | ((r >> 12) & 0x3F)); o[2] = (char)(0x80 | ((r >> 6) & 0x3F)); o[3] = (char)(0x80 | (r & 0x3F));
    return 4;
}

#define IN_RANGES(tab, r, out) do {                                                   \
        size_t lo_ = 0, hi_ = sizeof(tab) / sizeof((tab)[0]);                         \
        (out) = 0;                                                                    \
        while (hi_ > lo_) {                                                           \
            size_t mid_ = (lo_ + hi_) / 2;                                            \
            if ((r) < (tab)[mid_].lo) hi_ = mid_;                                     \
            else if ((r) > (tab)[mid_].hi) lo_ = mid_ + 1;                            \
            else { (out) = 1; break; }                                                \
        }                                                                             \
    } while (0)

/* Go unicode.IsPrint (Unicode 15.0.0 table generated from Go's stdlib). */
static int is_print(uint32_t r) { int ok; IN_RANGES(print_table, r, ok); return ok; }
/* Go unicode.IsMark (Mn|Mc|Me). */
int mdgl_i_is_mark(uint32_t r) { int ok; IN_RANGES(mark_table, r, ok); return ok; }

/* Go strconv.Quote. */
static void sb_quote(sb_t *s, const char *t, size_t n) {
    static const char hex[] = "0123456789abcdef";
    char tmp[16];
    sb_add(s, "\"", 1);
    for (size_t i = 0; i < n;) {
        uint32_t r;
        int w = mdgl_i_u8dec((const unsigned char *)t + i, n - i, &r);
        if (w == 1 && r == 0xFFFD && (unsigned char)t[i] >= 0x80) {
            tmp[0] = '\\'; tmp[1] = 'x'; tmp[2] = hex[(unsigned char)t[i] >> 4]; tmp[3] = hex[(unsigned char)t[i] & 15];
            sb_add(s, tmp, 4);
            i++;
            continue;
        }
        i += (size_t)w;
        if (r == '"' || r == '\\') { tmp[0] = '\\'; tmp[1] = (char)r; sb_add(s, tmp, 2); continue; }
        if (is_print(r)) { sb_add(s, tmp, mdgl_i_u8enc(r, tmp)); continue; }
        switch (r) {
        case 7: sb_s(s, "\\a"); break;
        case 8: sb_s(s, "\\b"); break;
        case 12: sb_s(s, "\\f"); break;
        case 10: sb_s(s, "\\n"); break;
        case 13: sb_s(s, "\\r"); break;
        case 9: sb_s(s, "\\t"); break;
        case 11: sb_s(s, "\\v"); break;
        default:
            if (r < 0x20 || r == 0x7F) snprintf(tmp, sizeof tmp, "\\x%02x", (unsigned)r);
            else if (r < 0x10000) snprintf(tmp, sizeof tmp, "\\u%04x", (unsigned)r);
            else snprintf(tmp, sizeof tmp, "\\U%08x", (unsigned)r);
            sb_s(s, tmp);
        }
    }
    sb_add(s, "\"", 1);
}
static void sb_qs(sb_t *s, const char *t) { sb_quote(s, t, strlen(t)); }

/* ---------- Go strconv.Unquote for "..." ---------- */

static int hexv(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
/* in = text between the quotes; out has room for n bytes. Returns length or -1. */
static long unquote(const char *in, size_t n, char *out) {
    size_t i = 0, o = 0;
    if (memchr(in, '\n', n)) return -1;
    while (i < n) {
        unsigned char c = (unsigned char)in[i];
        if (c != '\\') { out[o++] = (char)c; i++; continue; }
        if (n - i < 2) return -1;
        c = (unsigned char)in[i + 1];
        i += 2;
        switch (c) {
        case 'a': out[o++] = 7; break;
        case 'b': out[o++] = 8; break;
        case 'f': out[o++] = 12; break;
        case 'n': out[o++] = 10; break;
        case 'r': out[o++] = 13; break;
        case 't': out[o++] = 9; break;
        case 'v': out[o++] = 11; break;
        case '\\': out[o++] = '\\'; break;
        case '"': out[o++] = '"'; break;
        case 'x': case 'u': case 'U': {
            int k = c == 'x' ? 2 : c == 'u' ? 4 : 8;
            uint32_t v = 0;
            if ((size_t)k > n - i) return -1;
            for (int j = 0; j < k; j++) {
                int h = hexv((unsigned char)in[i + (size_t)j]);
                if (h < 0) return -1;
                v = v << 4 | (uint32_t)h;
            }
            i += (size_t)k;
            if (c == 'x') { out[o++] = (char)v; break; }
            if (v > 0x10FFFF || (v >= 0xD800 && v <= 0xDFFF)) return -1;
            o += mdgl_i_u8enc(v, out + o);
            break;
        }
        case '0': case '1': case '2': case '3': case '4': case '5': case '6': case '7': {
            uint32_t v = c - '0';
            if (n - i < 2) return -1;
            for (int j = 0; j < 2; j++) {
                unsigned char d = (unsigned char)in[i + (size_t)j];
                if (d < '0' || d > '7') return -1;
                v = v << 3 | (uint32_t)(d - '0');
            }
            i += 2;
            if (v > 255) return -1;
            out[o++] = (char)v;
            break;
        }
        default: return -1;
        }
    }
    return (long)o;
}

/* ---------- lexer ---------- */

typedef struct { const char *t; size_t n; int col; int quoted; } tok_t;
typedef struct { tok_t *v; int n, off, line, col; } rd_t;

static int isdig(int c) { return c >= '0' && c <= '9'; }
static int isltr(int c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }
static int tis(tok_t t, const char *s) { size_t n = strlen(s); return t.n == n && memcmp(t.t, s, n) == 0; }
static int identifier(tok_t t) {
    if (t.quoted || t.n == 0 || !isltr((unsigned char)t.t[0])) return 0;
    for (size_t i = 0; i < t.n; i++)
        if (!isltr((unsigned char)t.t[i]) && !isdig((unsigned char)t.t[i])) return 0;
    return 1;
}

/* Returns token count or -1 with the diagnostic written. */
static int lex(P *p, const char *line, size_t len, int lineno, tok_t *out) {
    int nt = 0;
    for (size_t off = 0; off < len;) {
        unsigned char c = (unsigned char)line[off];
        if (c == ' ' || c == '\t' || c == '\r') { off++; continue; }
        size_t start = off;
        if (c == '"') {
            int closed = 0;
            off++;
            while (off < len) {
                if (line[off] == '\\') { off += 2; continue; }
                if (line[off] == '"') { off++; closed = 1; break; }
                off++;
            }
            if (!closed) { ferr_s(p, lineno, (int)start + 1, "unterminated string"); return -1; }
            char *buf = ar_alloc(p, off - start);
            long ul = unquote(line + start + 1, off - start - 2, buf);
            if (ul < 0) { ferr_s(p, lineno, (int)start + 1, "invalid string escape"); return -1; }
            buf[ul] = 0;
            out[nt++] = (tok_t){buf, (size_t)ul, (int)start + 1, 1};
            continue;
        }
        if (isdig(c) || (c == '.' && off + 1 < len && isdig((unsigned char)line[off + 1]))) {
            off++;
            while (off < len && (isdig((unsigned char)line[off]) || line[off] == '.')) off++;
            if (len - off >= 3 && (!memcmp(line + off, "rad", 3) || !memcmp(line + off, "deg", 3))) off += 3;
            else if (off < len && (line[off] == 's' || line[off] == '%')) off++;
        } else if (isltr(c)) {
            off++;
            while (off < len && (isltr((unsigned char)line[off]) || isdig((unsigned char)line[off]) || line[off] == '-')) off++;
        } else if (strchr("=(),@:.+-", c) && c) {
            off++;
        } else {
            m_reset(p);
            sb_s(&p->m, "unexpected character ");
            { char u[4]; sb_quote(&p->m, u, mdgl_i_u8enc(c, u)); } /* Go: string(byte) is the Latin-1 rune */
            ferr(p, lineno, (int)start + 1);
            return -1;
        }
        out[nt++] = (tok_t){line + start, off - start, (int)start + 1, 0};
    }
    return nt;
}

/* ---------- reader / value / argument parsing ---------- */

static tok_t peek(rd_t *r) {
    static const tok_t end = {"<end>", 5, 0, 0};
    if (r->off >= r->n) { tok_t t = end; t.col = r->col; return t; }
    return r->v[r->off];
}
static tok_t take(rd_t *r) { tok_t t = peek(r); if (r->off < r->n) r->off++; return t; }
static int at_end(rd_t *r) { return r->off >= r->n; }
static int is_tok(rd_t *r, const char *s) { tok_t t = peek(r); return !t.quoted && tis(t, s); }
static int rfail_s(P *p, rd_t *r, const char *msg) { return ferr_s(p, r->line, peek(r).col, msg); }
static int want(P *p, rd_t *r, const char *s) {
    tok_t t = peek(r);
    if (t.quoted || !tis(t, s)) {
        m_reset(p); sb_s(&p->m, "expected "); sb_qs(&p->m, s);
        return ferr(p, r->line, t.col);
    }
    take(r);
    return 1;
}

static int parse_value(P *p, rd_t *r, mdgl_value_t *v) {
    tok_t cur = take(r);
    memset(v, 0, sizeof *v);
    if (cur.quoted) { v->text = ar_dup(p, cur.t, cur.n); v->len = cur.n; v->quoted = 1; return 1; }
    if (tis(cur, "<end>")) return rfail_s(p, r, "expected value");
    if (tis(cur, "(")) {
        mdgl_value_t *pr = ar_alloc(p, 3 * sizeof *pr);
        int n = 0;
        if (!parse_value(p, r, &pr[0]) || !want(p, r, ",") || !parse_value(p, r, &pr[1])) return 0;
        n = 2;
        if (tis(peek(r), ",")) {
            take(r);
            if (!parse_value(p, r, &pr[2])) return 0;
            n = 3;
        }
        if (!want(p, r, ")")) return 0;
        v->pair = pr;
        v->npair = n;
        v->text = "";
        return 1;
    }
    /* build text in a scratch buffer: concatenations stay small */
    size_t cap = cur.n + 1, len = 0;
    char *buf;
    tok_t a = {0}, b = {0}, c2 = {0};
    int ext1 = 0, ext2 = 0;
    if (tis(cur, "+") || tis(cur, "-") || tis(cur, "@")) {
        a = take(r);
        if (tis(a, "<end>")) return rfail_s(p, r, "expected value");
        ext1 = 1;
        cap += a.n;
    }
    {
        tok_t pk = peek(r);
        if (tis(pk, "+") || tis(pk, "-")) { b = take(r); c2 = take(r); ext2 = 1; cap += b.n + c2.n; }
    }
    buf = ar_alloc(p, cap);
    memcpy(buf, cur.t, cur.n); len = cur.n;
    if (ext1) { memcpy(buf + len, a.t, a.n); len += a.n; }
    if (ext2) { memcpy(buf + len, b.t, b.n); len += b.n; memcpy(buf + len, c2.t, c2.n); len += c2.n; }
    buf[len] = 0;
    for (size_t i = 0; i < len; i++)
        if (strchr("=),:", buf[i]) && buf[i]) return rfail_s(p, r, "expected value");
    v->text = buf;
    v->len = len;
    return 1;
}

static const mdgl_value_t EMPTY = {"", 0, 0, 0, NULL};
const mdgl_value_t *mdgl_i_argv_find(const mdgl_arg_t *a, int n, const char *key) {
    for (int i = 0; i < n; i++) if (!strcmp(a[i].key, key)) return &a[i].value;
    return NULL;
}
const mdgl_value_t *mdgl_i_argv_get(const mdgl_arg_t *a, int n, const char *key) {
    const mdgl_value_t *v = mdgl_i_argv_find(a, n, key);
    return v ? v : &EMPTY;
}

/* key=value attribute list to end of line */
static int parse_attrs(P *p, rd_t *r, const mdgl_arg_t **out, int *nout) {
    int cap = (r->n - r->off) / 3 + 1, n = 0;
    mdgl_arg_t *a = ar_alloc(p, (size_t)cap * sizeof *a);
    while (!at_end(r)) {
        tok_t name = take(r);
        if (!identifier(name)) return ferr_s(p, r->line, r->col, "expected attribute identifier");
        if (!want(p, r, "=")) return 0;
        mdgl_value_t v;
        if (!parse_value(p, r, &v)) return 0;
        char *key = ar_dup(p, name.t, name.n);
        if (mdgl_i_argv_find(a, n, key)) {
            m_reset(p); sb_s(&p->m, "duplicate attribute "); sb_s(&p->m, key);
            return ferr(p, r->line, r->col);
        }
        if (n >= cap) return ferr_s(p, r->line, r->col, "expected attribute identifier");
        a[n].key = key; a[n].value = v; n++;
    }
    *out = a; *nout = n;
    return 1;
}

static int parse_args(P *p, rd_t *r, const mdgl_arg_t **out, int *nout) {
    if (!want(p, r, "(")) return 0;
    int cap = r->n - r->off + 1, n = 0, ordinal = 0;
    mdgl_arg_t *a = ar_alloc(p, (size_t)cap * sizeof *a);
    while (!is_tok(r, ")")) {
        if (at_end(r)) return rfail_s(p, r, "expected \")\"");
        char kb[32];
        snprintf(kb, sizeof kb, "%d", ordinal++);
        const char *key = NULL;
        if (r->off + 1 < r->n && tis(r->v[r->off + 1], "=")) {
            tok_t name = take(r);
            if (!identifier(name)) return ferr_s(p, r->line, r->col, "expected argument identifier");
            key = ar_dup(p, name.t, name.n);
            take(r);
        } else key = ar_dup(p, kb, strlen(kb));
        mdgl_value_t v;
        if (!parse_value(p, r, &v)) return 0;
        if (mdgl_i_argv_find(a, n, key)) {
            m_reset(p); sb_s(&p->m, "duplicate argument "); sb_s(&p->m, key);
            return ferr(p, r->line, r->col);
        }
        a[n].key = key; a[n].value = v; n++;
        if (is_tok(r, ")")) break;
        if (!want(p, r, ",")) return 0;
        if (is_tok(r, ")")) return rfail_s(p, r, "trailing comma");
    }
    take(r);
    *out = a; *nout = n;
    return 1;
}

/* ---------- numbers, edit distance, Unknown() ---------- */

/* Finite decimal literal, optional sign, no exponent. The literal is validated against the MDGL
 * grammar, copied into a private buffer with '.' replaced by the current locale's decimal separator
 * (read, never changed: no setlocale), and converted by strtod, which must consume the whole buffer.
 * Rounding is the C library's (correct in glibc, musl, Apple, MSVC UCRT). */
static int dec_parse(const char *s, size_t n, double *out) {
    size_t i = 0, d1 = 0, d2 = 0, dot = (size_t)-1;
    if (n && (s[0] == '+' || s[0] == '-')) i++;
    size_t b = i;
    while (i < n && isdig((unsigned char)s[i])) { i++; d1++; }
    if (i < n && s[i] == '.') { dot = i; i++; while (i < n && isdig((unsigned char)s[i])) { i++; d2++; } }
    if (i != n || (d1 == 0 && d2 == 0) || (d1 == 0 && s[b] != '.')) return 0;
    const struct lconv *lc = localeconv();
    const char *dp = lc && lc->decimal_point && lc->decimal_point[0] ? lc->decimal_point : ".";
    size_t dl = strlen(dp);
    char stackbuf[64], *buf = n + dl < sizeof stackbuf ? stackbuf : malloc(n + dl + 1);
    if (!buf) return 0;
    size_t o = 0;
    for (size_t k = 0; k < n; k++) {
        if (k == dot) { memcpy(buf + o, dp, dl); o += dl; } else buf[o++] = s[k];
    }
    buf[o] = 0;
    char *end = NULL;
    double v = strtod(buf, &end);
    int ok = end == buf + o && isfinite(v);
    if (buf != stackbuf) free(buf);
    if (ok) *out = v;
    return ok;
}
/* Go mdgl_i_number(): trims one trailing "s". */
int mdgl_i_number_t(const char *s, size_t n, double *out) {
    if (n && s[n - 1] == 's') n--;
    return dec_parse(s, n, out);
}
int mdgl_i_number(const mdgl_value_t *v, double *out) {
    if (v->quoted || v->npair) return 0;
    return mdgl_i_number_t(v->text, v->len, out);
}
double mdgl_i_gotime(double v) { return fabs(v) > 1e6 ? v : round(v * 1e9) / 1e9; }

static int edit_distance(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    int *row = malloc((lb + 1) * sizeof *row);
    if (!row) return 99;
    for (size_t i = 0; i <= lb; i++) row[i] = (int)i;
    for (size_t i = 0; i < la;) {
        int diag = row[0];
        row[0] = (int)i + 1;
        for (size_t j = 0; j < lb;) {
            int saved = row[j + 1], cost = a[i] != b[j];
            int m = row[j] + 1;
            if (row[j + 1] + 1 < m) m = row[j + 1] + 1;
            if (diag + cost < m) m = diag + cost;
            row[j + 1] = m;
            diag = saved;
            uint32_t r;
            j += (size_t)mdgl_i_u8dec((const unsigned char *)b + j, lb - j, &r);
        }
        uint32_t r;
        i += (size_t)mdgl_i_u8dec((const unsigned char *)a + i, la - i, &r);
    }
    int d = row[lb];
    free(row);
    return d;
}
/* Appends 'unknown KIND "name"[; did you mean "x"?]' to p->m (fresh message). */
static void unknown(P *p, const char *kind, const char *name, const char *const *choices, int nch) {
    const char *best = "";
    int dist = 3;
    for (int i = 0; i < nch; i++) {
        int d = edit_distance(name, choices[i]);
        if (d < dist || (d == dist && strcmp(choices[i], best) < 0)) { best = choices[i]; dist = d; }
    }
    m_reset(p);
    sb_s(&p->m, "unknown "); sb_s(&p->m, kind); sb_s(&p->m, " "); sb_qs(&p->m, name);
    if (dist <= 2) { sb_s(&p->m, "; did you mean "); sb_qs(&p->m, best); sb_s(&p->m, "?"); }
}

/* ---------- parser ---------- */

static int is_space_rune(uint32_t r) {
    return r == ' ' || (r >= 9 && r <= 13) || r == 0x85 || r == 0xA0 || r == 0x1680 || (r >= 0x2000 && r <= 0x200A) ||
           r == 0x2028 || r == 0x2029 || r == 0x202F || r == 0x205F || r == 0x3000;
}
/* Go strings.TrimSpace; returns start offset and sets *end. */
static size_t trim_space(const char *s, size_t n, size_t *end) {
    size_t a = 0, b = n;
    while (a < b) {
        uint32_t r;
        int w = mdgl_i_u8dec((const unsigned char *)s + a, b - a, &r);
        if (!is_space_rune(r)) break;
        a += (size_t)w;
    }
    while (b > a) {
        size_t k = b - 1;
        while (k > a && ((unsigned char)s[k] & 0xC0) == 0x80 && b - k < 4) k--;
        uint32_t r;
        int w = mdgl_i_u8dec((const unsigned char *)s + k, b - k, &r);
        if (k + (size_t)w != b) { k = b - 1; r = 0xFFFD; }
        if (!is_space_rune(r)) break;
        b = k;
    }
    *end = b;
    return a;
}

static const char *const STMT_CHOICES[] = {"mdgl", "scene", "actor", "@"};

static mdgl_scene_t *parse_impl(P *p, const char *src, size_t len) {
    if (len > MAX_INPUT) { ferr_s(p, 1, 1, "input exceeds 256 KiB"); return NULL; }
    if (!u8valid(src, len)) { ferr_s(p, 1, 1, "input is not UTF-8"); return NULL; }
    mdgl_scene_t *sc = ar_alloc(p, sizeof *sc);
    memset(sc, 0, sizeof *sc);
    sc->actors = ar_alloc(p, (MAX_ACTORS + 1) * sizeof *sc->actors);
    sc->actions = ar_alloc(p, (MAX_ACTIONS + 1) * sizeof *sc->actions);
    int seen_scene = 0, seen_action = 0, seen_version = 0, lineno = 0;
    tok_t *toks = NULL;
    size_t toks_cap = 0;
    for (size_t pos = 0;; ) {
        const char *ls = src + pos;
        const char *nl = memchr(ls, '\n', len - pos);
        size_t ll = nl ? (size_t)(nl - ls) : len - pos;
        lineno++;
        if (ll > MAX_LINE) { ferr_s(p, lineno, 1, "line exceeds 16 KiB"); goto fail; }
        size_t te, ts = trim_space(ls, ll, &te);
        if (ts == te || ls[ts] == '#') goto next;
        if (ll + 1 > toks_cap) {
            free(toks);
            p->toks = toks = NULL;
            toks_cap = ll + 1;
            toks = malloc(toks_cap * sizeof *toks);
            if (!toks) longjmp(p->jb, 1);
            p->toks = toks;
        }
        int nt = lex(p, ls, ll, lineno, toks);
        if (nt < 0) goto fail;
        rd_t r = {toks, nt, 0, lineno, 1};
        tok_t head = take(&r);
        if (head.quoted) { ferr_s(p, lineno, 1, "expected statement identifier"); goto fail; }
        r.col = head.col;
        int col = head.col;
        if (tis(head, "mdgl")) {
            tok_t v = take(&r);
            if (seen_scene || seen_version || v.quoted || !tis(v, "0.1") || !at_end(&r)) { ferr_s(p, lineno, col, "expected initial mdgl 0.1"); goto fail; }
            seen_version = 1;
        } else if (tis(head, "scene")) {
            if (seen_scene) { ferr_s(p, lineno, col, "duplicate scene"); goto fail; }
            sc->line = lineno; sc->col = col;
            seen_scene = 1;
            if (!parse_attrs(p, &r, &sc->attrs, &sc->nattrs)) goto fail;
        } else if (tis(head, "actor")) {
            if (!seen_scene) { ferr_s(p, lineno, col, "scene must precede actors"); goto fail; }
            if (seen_action) { ferr_s(p, lineno, col, "actors must precede actions"); goto fail; }
            mdgl_actor_t a;
            memset(&a, 0, sizeof a);
            a.line = lineno; a.col = col;
            tok_t name = take(&r);
            if (!identifier(name)) { ferr_s(p, lineno, col, "expected actor identifier"); goto fail; }
            a.name = ar_dup(p, name.t, name.n);
            if (!want(p, &r, "=")) goto fail;
            tok_t kind = take(&r);
            if (!identifier(kind)) { ferr_s(p, lineno, col, "expected shape identifier"); goto fail; }
            a.kind = ar_dup(p, kind.t, kind.n);
            if (!parse_args(p, &r, &a.args, &a.nargs) || !want(p, &r, "at")) goto fail;
            mdgl_value_t pt;
            if (!parse_value(p, &r, &pt)) goto fail;
            if (pt.npair != 2) { ferr_s(p, lineno, col, "expected (x, y) position"); goto fail; }
            a.x = pt.pair[0]; a.y = pt.pair[1];
            int ok = parse_attrs(p, &r, &a.attrs, &a.nattrs);
            sc->actors[sc->nactors++] = a;
            if (sc->nactors > MAX_ACTORS) { ferr_s(p, lineno, col, "actor limit 64 exceeded"); goto fail; }
            if (!ok) goto fail;
        } else if (tis(head, "@")) {
            if (!seen_scene) { ferr_s(p, lineno, col, "scene must precede actions"); goto fail; }
            seen_action = 1;
            mdgl_value_t tv;
            if (!parse_value(p, &r, &tv)) goto fail;
            double begin;
            if (tv.quoted || tv.npair || !mdgl_i_number_t(tv.text, tv.len, &begin) || begin < 0) { ferr_s(p, lineno, col, "invalid action time"); goto fail; }
            mdgl_action_t a;
            memset(&a, 0, sizeof a);
            a.line = lineno; a.col = col; a.begin = begin;
            if (!want(p, &r, ":")) goto fail;
            tok_t name = take(&r);
            if (!identifier(name)) { ferr_s(p, lineno, col, "expected actor identifier"); goto fail; }
            a.actor = ar_dup(p, name.t, name.n);
            if (!want(p, &r, ".")) goto fail;
            tok_t verb = take(&r);
            if (!identifier(verb)) { ferr_s(p, lineno, col, "expected action identifier"); goto fail; }
            a.verb = ar_dup(p, verb.t, verb.n);
            int ok = parse_args(p, &r, &a.args, &a.nargs);
            if (ok && !at_end(&r)) {
                m_reset(p); sb_s(&p->m, "unexpected token "); sb_quote(&p->m, peek(&r).t, peek(&r).n);
                ok = ferr(p, lineno, peek(&r).col);
            }
            sc->actions[sc->nactions++] = a;
            if (sc->nactions > MAX_ACTIONS) { ferr_s(p, lineno, col, "action limit 1024 exceeded"); goto fail; }
            if (!ok) goto fail;
        } else if (tis(head, "camera") || tis(head, "light") || tis(head, "mesh") || tis(head, "material") || tis(head, "threejs")) {
            m_reset(p); sb_add(&p->m, head.t, head.n); sb_s(&p->m, " is reserved; not yet supported in 0.1");
            ferr(p, lineno, col);
            goto fail;
        } else {
            char *hs = ar_dup(p, head.t, head.n);
            unknown(p, "statement", hs, STMT_CHOICES, 4);
            sb_s(&p->m, "; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)");
            if (!strcmp(hs, "text") || !strcmp(hs, "rect") || !strcmp(hs, "circle") || !strcmp(hs, "cube")) {
                sb_s(&p->m, "; use actor NAME = "); sb_s(&p->m, hs); sb_s(&p->m, "(...) at (X,Y)");
            }
            ferr(p, lineno, col);
            goto fail;
        }
    next:
        if (!nl) break;
        pos = (size_t)(nl - src) + 1;
    }
    free(toks);
    p->toks = NULL;
    if (!seen_scene) { ferr_s(p, 1, 1, "missing scene"); return NULL; }
    return sc;
fail:
    free(toks);
    p->toks = NULL;
    return NULL;
}

/* ---------- checker ---------- */

static const char *const COLORS[] = {"normal", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "accent"};
static const char *const EASES[] = {"linear", "ease", "ease-in", "ease-out", "ease-in-out", "bounce"};
static const char *const VERBS[] = {"fade", "move", "scale", "color", "type", "blink", "wipe", "slide", "rotate"};
#define NEL(a) ((int)(sizeof(a) / sizeof((a)[0])))

static int one_of(const mdgl_value_t *v, const char *const *ch, int n) {
    if (v->quoted || v->npair) return 0;
    for (int i = 0; i < n; i++) if (v->len == strlen(ch[i]) && !memcmp(v->text, ch[i], v->len)) return 1;
    return 0;
}
static int in_list(const char *s, const char *const *ch, int n) {
    for (int i = 0; i < n; i++) if (!strcmp(s, ch[i])) return 1;
    return 0;
}
static int cmp_args(const void *a, const void *b) { return strcmp((*(const mdgl_arg_t *const *)a)->key, (*(const mdgl_arg_t *const *)b)->key); }

/* Go keys(): unknown/reserved argument or attribute. Writes p->m, returns 1 if ok. */
static int keys_ok(P *p, const mdgl_arg_t *args, int n, const char *const *allowed, int nallowed, const char *kind) {
    static const char *const RESERVED[] = {"camera", "light", "material", "position", "rotation", "threejs"};
    const mdgl_arg_t **sorted = malloc((size_t)(n ? n : 1) * sizeof *sorted);
    if (!sorted) { m_reset(p); sb_s(&p->m, "out of memory"); return 0; }
    for (int i = 0; i < n; i++) sorted[i] = &args[i];
    qsort(sorted, (size_t)n, sizeof sorted[0], cmp_args);
    size_t kl = strlen(kind);
    int is_arg = kl >= 8 && !strcmp(kind + kl - 8, "argument");
    for (int i = 0; i < n; i++) {
        const char *k = sorted[i]->key;
        if (in_list(k, RESERVED, NEL(RESERVED))) {
            m_reset(p); sb_s(&p->m, k); sb_s(&p->m, " is reserved; not yet supported in 0.1");
            { free(sorted); return 0; }
        }
        if (in_list(k, allowed, nallowed)) continue;
        const char *choices[8];
        int nc = 0;
        for (int j = 0; j < nallowed; j++) if (!isdig((unsigned char)allowed[j][0])) choices[nc++] = allowed[j];
        if (!is_arg) { unknown(p, kind, k, allowed, nallowed); free(sorted); return 0; }
        unknown(p, kind, k, choices, nc);
        sb_s(&p->m, "; valid arguments: ");
        for (int j = 0; j < nallowed; j++) {
            if (j) sb_s(&p->m, ", ");
            if (isdig((unsigned char)allowed[j][0])) { sb_s(&p->m, "positional "); sb_i(&p->m, atoi(allowed[j]) + 1); }
            else sb_s(&p->m, allowed[j]);
        }
        { free(sorted); return 0; }
    }
    free(sorted);
    return 1;
}

static int integer_v(P *p, const mdgl_value_t *v, long lo, long hi, const char *name) {
    double d;
    if (!mdgl_i_number(v, &d) || d != trunc(d) || d < (double)lo || d > (double)hi) {
        m_reset(p); sb_s(&p->m, name); sb_s(&p->m, " must be an integer in "); sb_i(&p->m, lo); sb_s(&p->m, ".."); sb_i(&p->m, hi);
        return 0;
    }
    return 1;
}
static double num_or0(const mdgl_value_t *v) { double d = 0; mdgl_i_number(v, &d); return d; }

static int dimension(const mdgl_value_t *v, double *out) {
    double d;
    if (!mdgl_i_number(v, &d) || d <= 0 || d > 200) return 0;
    *out = d;
    return 1;
}

static int coordinate(const mdgl_value_t *v, int horizontal) {
    if (v->quoted || v->npair) return 0;
    const char *t = v->text;
    size_t n = v->len;
    double d;
    if (n && t[n - 1] == '%') {
        if (mdgl_i_number_t(t, n - 1, &d)) return fabs(d) <= 10000;
        return 0;
    }
    if (mdgl_i_number_t(t, n, &d)) return fabs(d) <= 10000;
    static const char *const H[] = {"center", "left", "right"}, *const V[] = {"center", "top", "bottom"};
    const char *const *an = horizontal ? H : V;
    for (int i = 0; i < 3; i++) {
        size_t al = strlen(an[i]);
        if (n >= al && !memcmp(t, an[i], al)) {
            if (n == al) return 1;
            if ((t[al] == '+' || t[al] == '-') && mdgl_i_number_t(t + al, n - al, &d) && fabs(d) <= 10000) return 1;
        }
    }
    return 0;
}
/* Go: coordinate with "%" suffix is validated by mdgl_i_number() of the trimmed text. Fix-up above covers it. */

int mdgl_i_angle_deg(const mdgl_value_t *v, double *out) {
    if (v->quoted || v->npair) return 0;
    if (v->len >= 3 && !memcmp(v->text + v->len - 3, "rad", 3)) {
        double a;
        if (!mdgl_i_number_t(v->text, v->len - 3, &a)) return 0;
        *out = a * 180 / 3.14159265358979323846;
        return 1;
    }
    size_t n = v->len;
    if (n >= 3 && !memcmp(v->text + n - 3, "deg", 3)) n -= 3;
    return mdgl_i_number_t(v->text, n, out);
}

/* Grapheme clusters: port of rivo/uniseg v0.4.7 (Unicode 15.0.0 UAX29 GB3-GB13/GB999,
 * no GB9c) and its StepString width rules, over the generated mdgl_unicode.h tables. */
#define TAB_FIND(tab, r, dflt) do {                                                   \
        size_t lo_ = 0, hi_ = sizeof(tab) / sizeof((tab)[0]);                          \
        res_ = (dflt);                                                                \
        while (hi_ > lo_) {                                                           \
            size_t mid_ = (lo_ + hi_) / 2;                                            \
            if ((r) < (tab)[mid_].lo) hi_ = mid_;                                     \
            else if ((r) > (tab)[mid_].hi) lo_ = mid_ + 1;                            \
            else { res_ = (tab)[mid_].v; break; }                                     \
        }                                                                             \
    } while (0)

static int gr_prop(uint32_t r) {
    int res_;
    if (r >= 0x20 && r <= 0x7E) return GB_Any;
    if (r == 0x0A) return GB_LF;
    if (r == 0x0D) return GB_CR;
    if (r <= 0x1F || r == 0x7F) return GB_Control;
    TAB_FIND(gb_table, r, GB_Any);
    return res_;
}
static int ea_prop(uint32_t r) {
    int res_;
    if (r >= 0x20 && r <= 0x7E) return EA_Na;
    if (r <= 0x1F || r == 0x7F) return EA_N;
    TAB_FIND(ea_table, r, EA_N);
    return res_;
}
static int rune_width(uint32_t r, int prop) {
    int res_;
    switch (prop) {
    case GB_Control: case GB_CR: case GB_LF: case GB_Extend: case GB_ZWJ: return 0;
    case GB_RI: return 2;
    case GB_ExtPict:
        TAB_FIND(ep_table, r, 0);
        return res_ ? 2 : 1;
    }
    if (r == 0x2E3A) return 3;
    if (r == 0x2E3B) return 4;
    res_ = ea_prop(r);
    return res_ == EA_W || res_ == EA_F ? 2 : 1;
}

enum { S_Any, S_CR, S_ControlLF, S_L, S_LVV, S_LVTT, S_Prepend, S_ExtPict, S_ExtPictZWJ, S_RIOdd, S_RIEven };
#define ANYP 99
typedef struct { signed char st, prop, ns, brk; short rule; } gtr_t;
static const gtr_t GTR[] = {
    {S_Any, GB_CR, S_CR, 1, 50}, {S_Any, GB_LF, S_ControlLF, 1, 50}, {S_Any, GB_Control, S_ControlLF, 1, 50},
    {S_CR, ANYP, S_Any, 1, 40}, {S_ControlLF, ANYP, S_Any, 1, 40}, {S_CR, GB_LF, S_ControlLF, 0, 30},
    {S_Any, GB_L, S_L, 1, 9990}, {S_L, GB_L, S_L, 0, 60}, {S_L, GB_V, S_LVV, 0, 60}, {S_L, GB_LV, S_LVV, 0, 60}, {S_L, GB_LVT, S_LVTT, 0, 60},
    {S_Any, GB_LV, S_LVV, 1, 9990}, {S_Any, GB_V, S_LVV, 1, 9990}, {S_LVV, GB_V, S_LVV, 0, 70}, {S_LVV, GB_T, S_LVTT, 0, 70},
    {S_Any, GB_LVT, S_LVTT, 1, 9990}, {S_Any, GB_T, S_LVTT, 1, 9990}, {S_LVTT, GB_T, S_LVTT, 0, 80},
    {S_Any, GB_Extend, S_Any, 0, 90}, {S_Any, GB_ZWJ, S_Any, 0, 90}, {S_Any, GB_SpacingMark, S_Any, 0, 91},
    {S_Any, GB_Prepend, S_Prepend, 1, 9990}, {S_Prepend, ANYP, S_Any, 0, 92},
    {S_Any, GB_ExtPict, S_ExtPict, 1, 9990}, {S_ExtPict, GB_Extend, S_ExtPict, 0, 110}, {S_ExtPict, GB_ZWJ, S_ExtPictZWJ, 0, 110},
    {S_ExtPictZWJ, GB_ExtPict, S_ExtPict, 0, 110},
    {S_Any, GB_RI, S_RIOdd, 1, 9990}, {S_RIOdd, GB_RI, S_RIEven, 0, 120}, {S_RIEven, GB_RI, S_RIOdd, 1, 120},
};
static const gtr_t *gtr_find(int st, int prop) {
    for (size_t i = 0; i < sizeof GTR / sizeof GTR[0]; i++) if (GTR[i].st == st && GTR[i].prop == prop) return &GTR[i];
    return NULL;
}
/* uniseg transitionGraphemeState */
static int gr_transition(int st, int prop, int *brk) {
    const gtr_t *t = gtr_find(st, prop);
    if (t) { *brk = t->brk; return t->ns; }
    const gtr_t *a = gtr_find(st, ANYP), *b = gtr_find(S_Any, prop);
    if (a && b) { *brk = a->rule < b->rule ? a->brk : b->brk; return b->ns; }
    if (a) { *brk = a->brk; return a->ns; }
    if (b) { *brk = b->brk; return b->ns; }
    *brk = 1;
    return S_Any;
}

size_t mdgl_grapheme_step(const char *s, size_t n, int *state, int *width) {
    const unsigned char *u = (const unsigned char *)s;
    uint32_t r;
    int w0 = 0, st, first, brk;
    if (n == 0) { *width = 0; return 0; }
    size_t len = (size_t)mdgl_i_u8dec(u, n, &r);
    if (n <= len) { *width = rune_width(r, gr_prop(r)); *state = S_Any; return n; }
    if (*state < 0) { st = gr_transition(S_Any, first = gr_prop(r), &brk); }
    else { st = *state & 0xFF; first = *state >> 8; }
    w0 = rune_width(r, first);
    for (;;) {
        int prop;
        size_t l = (size_t)mdgl_i_u8dec(u + len, n - len, &r);
        prop = gr_prop(r);
        st = gr_transition(st, prop, &brk);
        if (brk) { *width = w0; *state = st | prop << 8; return len; }
        if (first == GB_ExtPict) { if (r == 0xFE0E) w0 = 1; else if (r == 0xFE0F) w0 = 2; }
        else if (first != GB_RI && first != GB_L) w0 += rune_width(r, prop);
        len += l;
        if (n <= len) { *width = w0; *state = S_Any; return n; }
    }
}
long mdgl_i_glyph_count(const char *s, size_t n) {
    long count = 0;
    int st = -1, w;
    while (n) { size_t c = mdgl_grapheme_step(s, n, &st, &w); s += c; n -= c; count++; }
    return count;
}
static int valid_text(const mdgl_value_t *v, const char **err) {
    if (mdgl_i_glyph_count(v->text, v->len) > 1024) { *err = "text exceeds 1024 graphemes"; return 0; }
    for (size_t i = 0; i < v->len;) {
        uint32_t r;
        i += (size_t)mdgl_i_u8dec((const unsigned char *)v->text + i, v->len - i, &r);
        if (r < 0x20 || (r >= 0x7F && r <= 0x9F) || r == 0x2028 || r == 0x2029) { *err = "text contains a control character"; return 0; }
    }
    return 1;
}

int mdgl_i_find_actor(const mdgl_scene_t *sc, const char *name) {
    for (int i = 0; i < sc->nactors; i++) if (!strcmp(sc->actors[i].name, name)) return i;
    return -1;
}

static int check_actor(P *p, mdgl_scene_t *sc, mdgl_actor_t *a, int index) {
    static const char *const AKEYS[] = {"color", "parent", "z", "anchor"};
    static const char *const TEXT[] = {"0", "1"}, *const RECT[] = {"0", "1", "border", "title"}, *const CIRC[] = {"0"}, *const CUBE[] = {"size", "style"};
    static const char *const SHAPES[] = {"text", "rect", "circle", "cube"};
    static const char *const BORDER[] = {"round", "square"}, *const WIRE[] = {"wire"};
    int L = a->line, C = a->col;
    const char *terr;
    for (int j = 0; j < index; j++)
        if (!strcmp(sc->actors[j].name, a->name)) { m_reset(p); sb_s(&p->m, "duplicate actor "); sb_s(&p->m, a->name); return ferr(p, L, C); }
    if (!keys_ok(p, a->attrs, a->nattrs, AKEYS, 4, "actor attribute")) return ferr(p, L, C);
    a->color = "normal"; a->parent = ""; a->text = ""; a->z = 0;
    const mdgl_value_t *v;
    if ((v = mdgl_i_argv_find(a->attrs, a->nattrs, "color"))) {
        if (!one_of(v, COLORS, NEL(COLORS))) { unknown(p, "color", v->text, COLORS, NEL(COLORS)); return ferr(p, L, C); }
        a->color = v->text;
    }
    if ((v = mdgl_i_argv_find(a->attrs, a->nattrs, "parent"))) {
        if (v->quoted || v->npair) return ferr_s(p, L, C, "parent must be an actor identifier");
        a->parent = v->text;
    }
    if ((v = mdgl_i_argv_find(a->attrs, a->nattrs, "z"))) {
        if (!integer_v(p, v, -10000, 10000, "z")) return ferr(p, L, C);
        a->z = num_or0(v);
    }
    if (!strcmp(a->kind, "text")) {
        if (!keys_ok(p, a->args, a->nargs, TEXT, 2, "text argument")) return ferr(p, L, C);
        v = mdgl_i_argv_find(a->args, a->nargs, "0");
        if (!v || !v->quoted) return ferr_s(p, L, C, "text requires a quoted string");
        a->text = v->text;
        const mdgl_value_t *st = mdgl_i_argv_find(a->args, a->nargs, "1");
        if (st && (st->quoted || st->npair || strcmp(st->text, "big") != 0)) return ferr_s(p, L, C, "text style must be big");
        if (!valid_text(v, &terr)) return ferr_s(p, L, C, terr);
        a->width = (double)mdgl_i_glyph_count(v->text, v->len);
        a->height = 1;
    } else if (!strcmp(a->kind, "rect")) {
        if (!keys_ok(p, a->args, a->nargs, RECT, 4, "rect argument")) return ferr(p, L, C);
        if (!dimension(mdgl_i_argv_get(a->args, a->nargs, "0"), &a->width)) return ferr_s(p, L, C, "rect width must be positive and <=200");
        if (!dimension(mdgl_i_argv_get(a->args, a->nargs, "1"), &a->height)) return ferr_s(p, L, C, "rect height must be positive and <=200");
        if ((v = mdgl_i_argv_find(a->args, a->nargs, "border")) && !one_of(v, BORDER, 2)) return ferr_s(p, L, C, "border must be round or square");
        if ((v = mdgl_i_argv_find(a->args, a->nargs, "title"))) {
            if (!v->quoted) return ferr_s(p, L, C, "title requires a quoted string");
            a->text = v->text;
            if (!valid_text(v, &terr)) return ferr_s(p, L, C, terr);
        }
    } else if (!strcmp(a->kind, "circle")) {
        if (!keys_ok(p, a->args, a->nargs, CIRC, 1, "circle argument")) return ferr(p, L, C);
        double rad;
        if (!dimension(mdgl_i_argv_get(a->args, a->nargs, "0"), &rad) || rad > 100) return ferr_s(p, L, C, "circle radius must be positive and <=100");
        a->width = a->height = rad * 2;
    } else if (!strcmp(a->kind, "cube")) {
        if (!keys_ok(p, a->args, a->nargs, CUBE, 2, "cube argument")) return ferr(p, L, C);
        if (!dimension(mdgl_i_argv_get(a->args, a->nargs, "size"), &a->width)) return ferr_s(p, L, C, "cube size must be positive and <=200");
        a->height = a->width;
        if ((v = mdgl_i_argv_find(a->args, a->nargs, "style")) && !one_of(v, WIRE, 1)) return ferr_s(p, L, C, "only cube style=wire is supported in 0.1");
    } else if (!strcmp(a->kind, "mesh") || !strcmp(a->kind, "sphere") || !strcmp(a->kind, "plane") || !strcmp(a->kind, "threejs") || !strcmp(a->kind, "cells")) {
        m_reset(p); sb_s(&p->m, a->kind); sb_s(&p->m, " is reserved; not yet supported in 0.1");
        return ferr(p, L, C);
    } else {
        unknown(p, "shape", a->kind, SHAPES, 4);
        return ferr(p, L, C);
    }
    if (!coordinate(&a->x, 1) || !coordinate(&a->y, 0)) {
        const mdgl_value_t *bad = !coordinate(&a->x, 1) ? &a->x : &a->y;
        if (bad->quoted || bad->npair) return ferr_s(p, L, C, "invalid coordinate");
        double d;
        if (mdgl_i_number_t(bad->text, bad->len - (bad->len && bad->text[bad->len - 1] == '%'), &d) && fabs(d) > 10000) return ferr_s(p, L, C, "coordinate exceeds -10000..10000");
        m_reset(p); sb_s(&p->m, "invalid coordinate "); sb_qs(&p->m, bad->text);
        return ferr(p, L, C);
    }
    if ((v = mdgl_i_argv_find(a->attrs, a->nattrs, "anchor"))) {
        if (v->npair != 2) return ferr_s(p, L, C, "anchor requires (x, y)");
        for (int ax = 0; ax < 2; ax++)
            if (!coordinate(&v->pair[ax], ax == 0)) {
                const mdgl_value_t *bad = &v->pair[ax];
                if (bad->quoted || bad->npair) return ferr_s(p, L, C, "invalid coordinate");
                double d;
                if (mdgl_i_number_t(bad->text, bad->len - (bad->len && bad->text[bad->len - 1] == '%'), &d) && fabs(d) > 10000) return ferr_s(p, L, C, "coordinate exceeds -10000..10000");
                m_reset(p); sb_s(&p->m, "invalid coordinate "); sb_qs(&p->m, bad->text);
                return ferr(p, L, C);
            }
    }
    return 1;
}

static const char *prop_of(const char *verb) {
    if (!strcmp(verb, "fade") || !strcmp(verb, "blink")) return "opacity";
    if (!strcmp(verb, "type") || !strcmp(verb, "wipe")) return "reveal";
    if (!strcmp(verb, "move") || !strcmp(verb, "slide")) return "position";
    if (!strcmp(verb, "scale")) return "scale";
    if (!strcmp(verb, "color")) return "color";
    return "rotation";
}

static int check_coord_pt(P *p, const mdgl_value_t *pt, int L, int C) {
    for (int ax = 0; ax < 2; ax++) {
        const mdgl_value_t *c = &pt->pair[ax];
        if (coordinate(c, ax == 0)) continue;
        if (c->quoted || c->npair) return ferr_s(p, L, C, "invalid coordinate");
        double d;
        if (mdgl_i_number_t(c->text, c->len - (c->len && c->text[c->len - 1] == '%'), &d) && fabs(d) > 10000) return ferr_s(p, L, C, "coordinate exceeds -10000..10000");
        m_reset(p); sb_s(&p->m, "invalid coordinate "); sb_qs(&p->m, c->text);
        return ferr(p, L, C);
    }
    return 1;
}

static int check_action(P *p, mdgl_scene_t *sc, mdgl_action_t *a, int index) {
    static const char *const FADE[] = {"0", "dur", "ease"}, *const MOVE[] = {"to", "dur", "ease"}, *const TYPE[] = {"per_char"},
        *const ROT[] = {"x", "y", "z", "dur", "ease"}, *const BLINK[] = {"times", "dur"}, *const SLIDE[] = {"0", "to", "dur", "ease"};
    static const char *const INOUT[] = {"in", "out"}, *const SIDES[] = {"left", "right", "top", "bottom"};
    int L = a->line, C = a->col;
    int ai = mdgl_i_find_actor(sc, a->actor);
    if (ai < 0) {
        const char *names[MAX_ACTORS];
        for (int i = 0; i < sc->nactors; i++) names[i] = sc->actors[i].name;
        unknown(p, "actor", a->actor, names, sc->nactors);
        return ferr(p, L, C);
    }
    const mdgl_actor_t *actor = &sc->actors[ai];
    if (!in_list(a->verb, VERBS, NEL(VERBS))) { unknown(p, "action", a->verb, VERBS, NEL(VERBS)); return ferr(p, L, C); }
    a->begin = mdgl_i_gotime(a->begin);
    const char *const *allowed;
    int nallowed;
    if (!strcmp(a->verb, "fade") || !strcmp(a->verb, "wipe")) { allowed = FADE; nallowed = 3; }
    else if (!strcmp(a->verb, "move") || !strcmp(a->verb, "scale") || !strcmp(a->verb, "color")) { allowed = MOVE; nallowed = 3; }
    else if (!strcmp(a->verb, "slide")) { allowed = SLIDE; nallowed = 4; }
    else if (!strcmp(a->verb, "type")) { allowed = TYPE; nallowed = 1; }
    else if (!strcmp(a->verb, "rotate")) { allowed = ROT; nallowed = 5; }
    else { allowed = BLINK; nallowed = 2; }
    if (!keys_ok(p, a->args, a->nargs, allowed, nallowed, "action argument")) return ferr(p, L, C);
    a->ease = "linear";
    const mdgl_value_t *v;
    if (!strcmp(a->verb, "fade") || !strcmp(a->verb, "wipe")) {
        if (!one_of(mdgl_i_argv_get(a->args, a->nargs, "0"), INOUT, 2)) { m_reset(p); sb_s(&p->m, a->verb); sb_s(&p->m, " requires in or out"); return ferr(p, L, C); }
    } else if (!strcmp(a->verb, "slide")) {
        if (!one_of(mdgl_i_argv_get(a->args, a->nargs, "0"), INOUT, 2)) return ferr_s(p, L, C, "slide requires in or out");
        if (!one_of(mdgl_i_argv_get(a->args, a->nargs, "to"), SIDES, 4)) return ferr_s(p, L, C, "slide to must be left, right, top or bottom");
    } else if (!strcmp(a->verb, "type")) {
        if (strcmp(actor->kind, "text")) return ferr_s(p, L, C, "type requires a text actor");
    } else if (!strcmp(a->verb, "blink")) {
        if (!integer_v(p, mdgl_i_argv_get(a->args, a->nargs, "times"), 1, 1000, "times")) return ferr(p, L, C);
    } else if (!strcmp(a->verb, "rotate")) {
        if (strcmp(actor->kind, "cube")) return ferr_s(p, L, C, "rotate requires a cube actor");
        int found = 0;
        for (int i = 0; i < 3; i++) {
            static const char *const AX[] = {"x", "y", "z"};
            if ((v = mdgl_i_argv_find(a->args, a->nargs, AX[i]))) {
                double ang;
                found = 1;
                if (!mdgl_i_angle_deg(v, &ang) || fabs(ang) > 10000) return ferr_s(p, L, C, "rotation must be within -10000..10000");
            }
        }
        if (!found) return ferr_s(p, L, C, "rotate requires x, y or z");
    }
    if ((v = mdgl_i_argv_find(a->args, a->nargs, "ease"))) {
        if (!one_of(v, EASES, NEL(EASES))) { unknown(p, "easing", v->text, EASES, NEL(EASES)); return ferr(p, L, C); }
        a->ease = v->text;
    }
    if (!strcmp(a->verb, "type")) {
        double sec;
        if (!mdgl_i_number(mdgl_i_argv_get(a->args, a->nargs, "per_char"), &sec) || sec <= 0) return ferr_s(p, L, C, "per_char must be positive");
        sec = mdgl_i_gotime(sec);
        if (sec == 0) return ferr_s(p, L, C, "per_char rounds to zero at nanosecond precision");
        a->duration = sec * (double)mdgl_i_glyph_count(actor->text, strlen(actor->text));
    } else {
        if (!mdgl_i_number(mdgl_i_argv_get(a->args, a->nargs, "dur"), &a->duration) || a->duration <= 0) return ferr_s(p, L, C, "dur must be positive");
    }
    a->property = prop_of(a->verb);
    if (!strcmp(a->verb, "move")) {
        v = mdgl_i_argv_get(a->args, a->nargs, "to");
        if (v->npair != 2) return ferr_s(p, L, C, "move requires to=(x, y)");
        if (!check_coord_pt(p, v, L, C)) return 0;
    } else if (!strcmp(a->verb, "scale")) {
        double f;
        if (!mdgl_i_number(mdgl_i_argv_get(a->args, a->nargs, "to"), &f) || f <= 0 || f > 16) return ferr_s(p, L, C, "scale to must be positive and <=16");
    } else if (!strcmp(a->verb, "color")) {
        v = mdgl_i_argv_get(a->args, a->nargs, "to");
        if (!one_of(v, COLORS, NEL(COLORS))) { unknown(p, "color", v->text, COLORS, NEL(COLORS)); return ferr(p, L, C); }
    }
    a->duration = mdgl_i_gotime(a->duration);
    if (a->duration == 0 && strcmp(a->verb, "type")) return ferr_s(p, L, C, "dur rounds to zero at nanosecond precision");
    double end = mdgl_i_gotime(a->begin + a->duration);
    if (!isfinite(end) || end > 60) return ferr_s(p, L, C, "action end must be <=60");
    if (sc->explicit_period) {
        if (end > sc->period) return ferr_s(p, L, C, "action exceeds period");
    } else if (end > sc->period) sc->period = end;
    for (int e = 0; e < index; e++) {
        const mdgl_action_t *o = &sc->actions[e];
        if (!strcmp(a->actor, o->actor) && !strcmp(a->property, o->property) && a->begin < mdgl_i_gotime(o->begin + o->duration) && o->begin < end) {
            m_reset(p); sb_s(&p->m, "overlapping "); sb_s(&p->m, a->property); sb_s(&p->m, " actions on "); sb_s(&p->m, a->actor);
            return ferr(p, L, C);
        }
    }
    return 1;
}

static int check_impl(P *p, mdgl_scene_t *sc) {
    static const char *const SKEYS[] = {"width", "height", "period", "repeat", "fallback", "fps"};
    int L = sc->line, C = sc->col;
    const mdgl_value_t *v;
    if (!keys_ok(p, sc->attrs, sc->nattrs, SKEYS, 6, "scene attribute")) return ferr(p, L, C);
    for (int i = 0; i < 3; i++) {
        static const char *const REQ[] = {"width", "height", "fallback"};
        if (!mdgl_i_argv_find(sc->attrs, sc->nattrs, REQ[i])) { m_reset(p); sb_s(&p->m, "missing scene attribute "); sb_s(&p->m, REQ[i]); return ferr(p, L, C); }
    }
    if (!integer_v(p, mdgl_i_argv_get(sc->attrs, sc->nattrs, "width"), 1, 200, "width")) return ferr(p, L, C);
    sc->width = (int)num_or0(mdgl_i_argv_get(sc->attrs, sc->nattrs, "width"));
    if (!integer_v(p, mdgl_i_argv_get(sc->attrs, sc->nattrs, "height"), 1, 60, "height")) return ferr(p, L, C);
    sc->height = (int)num_or0(mdgl_i_argv_get(sc->attrs, sc->nattrs, "height"));
    sc->fps = 30;
    if ((v = mdgl_i_argv_find(sc->attrs, sc->nattrs, "fps"))) {
        if (!integer_v(p, v, 1, 30, "fps")) return ferr(p, L, C);
        sc->fps = (int)num_or0(v);
    }
    sc->period = 0; sc->explicit_period = 0; sc->repeat = 1;
    if ((v = mdgl_i_argv_find(sc->attrs, sc->nattrs, "period"))) {
        sc->explicit_period = 1;
        if (!mdgl_i_number(v, &sc->period) || sc->period <= 0 || sc->period > 60) return ferr_s(p, L, C, "period must be positive and <=60");
        sc->period = mdgl_i_gotime(sc->period);
        if (sc->period == 0) return ferr_s(p, L, C, "period rounds to zero at nanosecond precision");
    }
    if ((v = mdgl_i_argv_find(sc->attrs, sc->nattrs, "repeat"))) {
        if (!v->quoted && v->len == 8 && !memcmp(v->text, "infinite", 8)) sc->repeat = 0;
        else {
            if (!integer_v(p, v, 1, 1000, "repeat")) return ferr(p, L, C);
            sc->repeat = (int)num_or0(v);
        }
        if (sc->repeat != 1 && !sc->explicit_period) return ferr_s(p, L, C, "repeat requires explicit period");
    }
    v = mdgl_i_argv_get(sc->attrs, sc->nattrs, "fallback");
    sc->fallback = v->text;
    if (v->quoted || v->npair) return ferr_s(p, L, C, "fallback must be start, end or @time");
    for (int i = 0; i < sc->nactors; i++)
        if (!check_actor(p, sc, &sc->actors[i], i)) return 0;
    for (int i = 0; i < sc->nactors; i++) {
        const mdgl_actor_t *a = &sc->actors[i];
        if (a->parent[0] && mdgl_i_find_actor(sc, a->parent) < 0) {
            const char *names[MAX_ACTORS];
            for (int j = 0; j < sc->nactors; j++) names[j] = sc->actors[j].name;
            unknown(p, "parent", a->parent, names, sc->nactors);
            return ferr(p, a->line, a->col);
        }
    }
    for (int i = 0; i < sc->nactors; i++) {
        const mdgl_actor_t *cur = &sc->actors[i];
        for (int steps = 0; cur->parent[0]; steps++) {
            if (steps > sc->nactors) { m_reset(p); sb_s(&p->m, "parent cycle involving "); sb_s(&p->m, sc->actors[i].name); return ferr(p, sc->actors[i].line, sc->actors[i].col); }
            cur = &sc->actors[mdgl_i_find_actor(sc, cur->parent)];
        }
    }
    for (int i = 0; i < sc->nactions; i++)
        if (!check_action(p, sc, &sc->actions[i], i)) return 0;
    if (strcmp(sc->fallback, "start") && strcmp(sc->fallback, "end")) {
        double t;
        if (sc->fallback[0] != '@') return ferr_s(p, L, C, "fallback must be start, end or @time");
        if (!mdgl_i_number_t(sc->fallback + 1, v->len - 1, &t) || t < 0 || t > sc->period) return ferr_s(p, L, C, "fallback time must be within period");
    }
    sc->checked = 1;
    return 1;
}

/* ---------- public API ---------- */

mdgl_scene_t *mdgl_parse_n(const char *source, size_t len, mdgl_diag_t *diag) {
    P *p = calloc(1, sizeof *p);
    mdgl_diag_t local;
    if (!p) {
        if (diag) { diag->line = diag->col = 1; strcpy(diag->message, "out of memory"); }
        return NULL;
    }
    p->diag = diag ? diag : &local;
    if (!source) { source = ""; len = 0; }
    mdgl_scene_t *sc = NULL;
    p->can_jump = 1;
    if (setjmp(p->jb) == 0) sc = parse_impl(p, source, len);
    else { free(p->toks); p->toks = NULL; ferr_s(p, 1, 1, "out of memory"); sc = NULL; }
    p->can_jump = 0;
    if (sc) { P *keep = p; sc->arena_ = keep; return sc; }
    ar_free(p->chunks);
    free(p);
    return NULL;
}

int mdgl_scene_check(mdgl_scene_t *sc, mdgl_diag_t *diag) {
    P q;
    memset(&q, 0, sizeof q);
    q.diag = diag;
    if (!sc) return ferr_s(&q, 1, 1, "missing scene") ? 0 : 1;
    return check_impl(&q, sc) ? 0 : 1;
}

void mdgl_scene_free(mdgl_scene_t *sc) {
    if (!sc) return;
    P *p = sc->arena_;
    ar_free(p->chunks);
    free(p);
}

int mdgl_check_n(const char *source, size_t len, mdgl_diag_t *out, int ndiags) {
    if (!out || ndiags <= 0) return -1;
    mdgl_scene_t *sc = mdgl_parse_n(source, len, out);
    if (!sc) return 1;
    int bad = mdgl_scene_check(sc, out);
    mdgl_scene_free(sc);
    return bad;
}

int mdgl_check(const char *source, mdgl_diag_t *out, int ndiags) {
    return mdgl_check_n(source, source ? strlen(source) : 0, out, ndiags);
}

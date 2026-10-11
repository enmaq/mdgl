/* MDGL 0.1 evaluator and terminal-cell renderer, ported from the Go reference (eval, render/cells,
 * internal/geometry). Pure: no I/O, no globals; every call allocates and frees its own scratch. */
#include "mdgl.h"
#include "mdgl_int.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef double mat4[16];

static void m_ident(double *m) { memset(m, 0, sizeof(mat4)); m[0] = m[5] = m[10] = m[15] = 1; }
static void m_mul(const double *l, const double *r, double *out) {
    double p[16] = {0};
    for (int c = 0; c < 4; c++) for (int w = 0; w < 4; w++) for (int i = 0; i < 4; i++) p[c * 4 + w] += l[i * 4 + w] * r[c * 4 + i];
    memcpy(out, p, sizeof p);
}
static void m_xform(const double *m, const double *v, double *out) {
    double r[4] = {0};
    for (int w = 0; w < 4; w++) for (int c = 0; c < 4; c++) r[w] += m[c * 4 + w] * v[c];
    memcpy(out, r, sizeof r);
}
static void m_trans(double x, double y, double z, double *m) { m_ident(m); m[12] = x; m[13] = y; m[14] = z; }
static void m_scale(double x, double y, double z, double *m) { m_ident(m); m[0] = x; m[5] = y; m[10] = z; }
static void m_rot(const double *a, double *out) {
    double xs = sin(a[0] * M_PI / 180), xc = cos(a[0] * M_PI / 180), ys = sin(a[1] * M_PI / 180), yc = cos(a[1] * M_PI / 180),
           zs = sin(a[2] * M_PI / 180), zc = cos(a[2] * M_PI / 180);
    mat4 x = {1, 0, 0, 0, 0, xc, xs, 0, 0, -xs, xc, 0, 0, 0, 0, 1}, y = {yc, 0, -ys, 0, 0, 1, 0, 0, ys, 0, yc, 0, 0, 0, 0, 1},
         z = {zc, zs, 0, 0, -zs, zc, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}, t;
    m_mul(x, y, t);
    m_mul(t, z, out);
}
static void m_compose(const double *pos, const double *ang, const double *sc, double *out) {
    mat4 t, r, s, tr;
    m_trans(pos[0], pos[1], pos[2], t); m_rot(ang, r); m_scale(sc[0], sc[1], sc[2], s);
    m_mul(t, r, tr); m_mul(tr, s, out);
}
static void m_persp(double fov, double aspect, double near, double far, double *m) {
    double f = 1 / tan(fov * M_PI / 360);
    memset(m, 0, sizeof(mat4));
    m[0] = f / aspect; m[5] = f; m[10] = -(far + near) / (far - near); m[11] = -1; m[14] = -2 * far * near / (far - near);
}
static void m_ortho(double l, double r, double b, double t, double n, double f, double *m) {
    memset(m, 0, sizeof(mat4));
    m[0] = 2 / (r - l); m[5] = 2 / (t - b); m[10] = -2 / (f - n); m[12] = -(r + l) / (r - l); m[13] = -(t + b) / (t - b); m[14] = -(f + n) / (f - n); m[15] = 1;
}
static int v_clip(const double *s, const double *e, double *cs, double *ce) {
    double lo = 0, hi = 1;
    for (int axis = 0; axis < 3; axis++)
        for (int k = 0; k < 2; k++) {
            double sign = k ? 1 : -1, first = s[3] + sign * s[axis], last = e[3] + sign * e[axis];
            if (first < 0 && last < 0) return 0;
            if (first < 0) lo = fmax(lo, first / (first - last));
            else if (last < 0) hi = fmin(hi, first / (first - last));
        }
    if (lo > hi) return 0;
    for (int a = 0; a < 4; a++) { cs[a] = s[a] + lo * (e[a] - s[a]); ce[a] = s[a] + hi * (e[a] - s[a]); }
    return cs[3] > 0 && ce[3] > 0;
}
static void v_port(const double *p, double w, double h, double *x, double *y) { *x = (p[0] / p[3] + 1) * w / 2; *y = (1 - p[1] / p[3]) * h / 2; }

/* ---------- evaluator ---------- */

typedef struct { double x, y, z, scale, opacity, reveal, rot[3]; mat4 t; const char *color; int has_t; } astate_t;

static double mix(double a, double b, double p) { return a + (b - a) * p; }
static double num0(const mdgl_value_t *v) { double d = 0; mdgl_i_number(v, &d); return d; }

static double resolve(const mdgl_value_t *v, double extent, double size) {
    static const char *const AN[] = {"center", "left", "right", "top", "bottom"};
    size_t n = v->len;
    double remaining = extent - size;
    if (n && v->text[n - 1] == '%') { double d = 0; mdgl_i_number_t(v->text, n - 1, &d); return d * remaining / 100; }
    for (int i = 0; i < 5; i++) {
        size_t al = strlen(AN[i]);
        if (n >= al && !memcmp(v->text, AN[i], al)) {
            double base = i == 0 ? remaining / 2 : (i == 2 || i == 4) ? remaining : 0;
            if (n > al) { double d = 0; mdgl_i_number_t(v->text + al, n - al, &d); base += d; }
            return base;
        }
    }
    return num0(v);
}

static double cbez(double p, double x1, double y1, double x2, double y2) {
    if (p == 0 || p == 1) return p;
    double lo = 0, hi = 1, m;
    for (int i = 0; i < 60; i++) {
        m = (lo + hi) / 2;
        double inv = 1 - m, sx = 3 * inv * inv * m * x1 + 3 * inv * m * m * x2 + m * m * m;
        if (sx < p) lo = m; else hi = m;
    }
    m = (lo + hi) / 2;
    double inv = 1 - m;
    return 3 * inv * inv * m * y1 + 3 * inv * m * m * y2 + m * m * m;
}
static double ease(const char *name, double p) {
    p = fmax(0, fmin(1, p));
    if (!strcmp(name, "ease")) return cbez(p, 0.25, 0.1, 0.25, 1);
    if (!strcmp(name, "ease-in")) return cbez(p, 0.42, 0, 1, 1);
    if (!strcmp(name, "ease-out")) return cbez(p, 0, 0, 0.58, 1);
    if (!strcmp(name, "ease-in-out")) return cbez(p, 0.42, 0, 0.58, 1);
    if (!strcmp(name, "bounce")) {
        double d = 2.75;
        if (p < 1 / d) return 7.5625 * p * p;
        if (p < 2 / d) { p -= 1.5 / d; return 7.5625 * p * p + 0.75; }
        if (p < 2.5 / d) { p -= 2.25 / d; return 7.5625 * p * p + 0.9375; }
        p -= 2.625 / d;
        return 7.5625 * p * p + 0.984375;
    }
    return p;
}

static int prop_id(const char *p) {
    static const char *const P[] = {"opacity", "reveal", "position", "scale", "color", "rotation"};
    for (int i = 0; i < 6; i++) if (!strcmp(p, P[i])) return i;
    return 0;
}
static void outside(const mdgl_scene_t *sc, const astate_t *st, const mdgl_actor_t *a, const char *dir, double *hx, double *vy) {
    double w = sc->width, h = sc->height;
    *hx = st->x; *vy = st->y;
    if (a->parent[0]) { const mdgl_actor_t *p = &sc->actors[mdgl_i_find_actor(sc, a->parent)]; w = p->width; h = p->height; }
    if (!strcmp(dir, "left")) *hx = -a->width * st->scale;
    else if (!strcmp(dir, "right")) *hx = w;
    else if (!strcmp(dir, "top")) *vy = -a->height * st->scale;
    else if (!strcmp(dir, "bottom")) *vy = h;
}

static long long ns_of(double s) { return (long long)llround(s * 1e9); }

static int compose_one(const mdgl_scene_t *sc, astate_t *st, char *done, int i) {
    if (done[i]) return 1;
    astate_t *a = &st[i];
    const mdgl_actor_t *ac = &sc->actors[i];
    double ax = ac->width / 2, ay = ac->height / 2;
    const mdgl_value_t *an = mdgl_i_argv_find(ac->attrs, ac->nattrs, "anchor");
    if (an) { ax = resolve(&an->pair[0], ac->width, 0); ay = resolve(&an->pair[1], ac->height, 0); }
    double pos[3] = {a->x + ax, -2 * (a->y + ay), 0}, scl[3] = {a->scale, a->scale, a->scale};
    mat4 c, t;
    m_compose(pos, a->rot, scl, c);
    m_trans(-ax, 2 * ay, 0, t);
    m_mul(c, t, a->t);
    if (ac->parent[0]) {
        int pi = mdgl_i_find_actor(sc, ac->parent);
        compose_one(sc, st, done, pi);
        m_mul(st[pi].t, a->t, a->t);
        a->scale *= st[pi].scale; a->opacity *= st[pi].opacity; a->reveal *= st[pi].reveal;
    }
    double o[4] = {0, 0, 0, 1}, r[4];
    m_xform(a->t, o, r);
    a->x = r[0]; a->y = -r[1] / 2;
    a->has_t = 1;
    done[i] = 1;
    return 1;
}

static astate_t *eval_at(const mdgl_scene_t *sc, double time) {
    int na = sc->nactors;
    astate_t *st = calloc((size_t)(na ? na : 1), sizeof *st);
    char *composed = calloc((size_t)(na ? na : 1), 1);
    int *order = malloc((size_t)(sc->nactions ? sc->nactions : 1) * sizeof *order);
    char *inited = calloc((size_t)(na ? na : 1) * 6, 1);
    if (!st || !composed || !order || !inited) { free(st); free(composed); free(order); free(inited); return NULL; }
    time = fmax(0, fmin(sc->period, time));
    long long tns = ns_of(time);
    for (int i = 0; i < na; i++) {
        const mdgl_actor_t *a = &sc->actors[i];
        double w = sc->width, h = sc->height;
        if (a->parent[0]) { const mdgl_actor_t *p = &sc->actors[mdgl_i_find_actor(sc, a->parent)]; w = p->width; h = p->height; }
        st[i].x = resolve(&a->x, w, a->width); st[i].y = resolve(&a->y, h, a->height);
        st[i].z = a->z; st[i].scale = 1; st[i].opacity = 1; st[i].reveal = 1; st[i].color = a->color;
    }
    for (int i = 0; i < sc->nactions; i++) {  /* stable insertion sort by begin */
        int j = i;
        while (j > 0 && sc->actions[order[j - 1]].begin > sc->actions[i].begin) { order[j] = order[j - 1]; j--; }
        order[j] = i;
    }
    for (int k = 0; k < sc->nactions; k++) {
        const mdgl_action_t *ac = &sc->actions[order[k]];
        int ai = mdgl_i_find_actor(sc, ac->actor);
        astate_t *tg = &st[ai];
        const mdgl_actor_t *actor = &sc->actors[ai];
        const char *dir0 = mdgl_i_argv_get(ac->args, ac->nargs, "0")->text;
        int is_in = !strcmp(dir0, "in");
        long long bns = ns_of(ac->begin), dns = ns_of(ac->duration);
        char *flag = &inited[ai * 6 + prop_id(ac->property)];
        if (!*flag) {
            *flag = 1;
            if (!strcmp(ac->verb, "fade") && is_in) tg->opacity = 0;
            if (!strcmp(ac->verb, "type") || (!strcmp(ac->verb, "wipe") && is_in)) tg->reveal = 0;
            if (!strcmp(ac->verb, "slide") && is_in && tns < bns) outside(sc, tg, actor, mdgl_i_argv_get(ac->args, ac->nargs, "to")->text, &tg->x, &tg->y);
        }
        if (tns < bns) continue;
        /* nanosecond-first: begin and duration are integer ns, the elapsed subtraction and the end test are
         * exact integers, then ONE float ratio feeds the easing (no epsilon, no float-seconds drift). */
        double progress = 1;
        if (dns > 0) progress = fmin(1, (double)(tns - bns) / (double)dns);
        if (tns >= bns + dns) progress = 1;
        double e = ease(ac->ease, progress);
        const char *v = ac->verb;
        if (!strcmp(v, "fade")) tg->opacity = is_in ? e : 1 - e;
        else if (!strcmp(v, "move")) {
            double w = sc->width, h = sc->height;
            if (actor->parent[0]) { const mdgl_actor_t *p = &sc->actors[mdgl_i_find_actor(sc, actor->parent)]; w = p->width; h = p->height; }
            const mdgl_value_t *pt = mdgl_i_argv_get(ac->args, ac->nargs, "to");
            tg->x = mix(tg->x, resolve(&pt->pair[0], w, actor->width), e);
            tg->y = mix(tg->y, resolve(&pt->pair[1], h, actor->height), e);
        } else if (!strcmp(v, "slide")) {
            double ex, ey;
            outside(sc, tg, actor, mdgl_i_argv_get(ac->args, ac->nargs, "to")->text, &ex, &ey);
            if (is_in) { tg->x = mix(ex, tg->x, e); tg->y = mix(ey, tg->y, e); }
            else { tg->x = mix(tg->x, ex, e); tg->y = mix(tg->y, ey, e); }
        } else if (!strcmp(v, "scale")) tg->scale = mix(tg->scale, num0(mdgl_i_argv_get(ac->args, ac->nargs, "to")), e);
        else if (!strcmp(v, "color")) { if (e >= 0.5) tg->color = mdgl_i_argv_get(ac->args, ac->nargs, "to")->text; }
        else if (!strcmp(v, "type")) {
            double count = (double)mdgl_i_glyph_count(actor->text, strlen(actor->text));
            if (count == 0) tg->reveal = 1;
            else {
                /* exact integer floor of elapsed/per_char on nanoseconds: no epsilon */
                long long per = ns_of(mdgl_i_gotime(num0(mdgl_i_argv_get(ac->args, ac->nargs, "per_char")))), el = tns - bns;
                double n = per > 0 ? (double)(el / per) : count;
                tg->reveal = fmin(count, n) / count;
            }
        } else if (!strcmp(v, "wipe")) tg->reveal = is_in ? e : 1 - e;
        else if (!strcmp(v, "blink")) {
            tg->opacity = 1;
            if (progress < 1 && ((long)floor(progress * num0(mdgl_i_argv_get(ac->args, ac->nargs, "times")) * 2)) % 2 == 1) tg->opacity = 0;
        } else if (!strcmp(v, "rotate")) {
            static const char *const AX[] = {"x", "y", "z"};
            for (int a = 0; a < 3; a++) {
                const mdgl_value_t *val = mdgl_i_argv_find(ac->args, ac->nargs, AX[a]);
                double deg;
                if (val && mdgl_i_angle_deg(val, &deg)) tg->rot[a] = mix(tg->rot[a], deg, e);
            }
        }
    }
    for (int i = 0; i < na; i++) compose_one(sc, st, composed, i);
    free(composed); free(order); free(inited);
    return st;
}

/* ---------- renderer ---------- */

typedef struct { int cols, rows; mdgl_cell_t *g; } grid_t;

static void rgb_of(const char *c, int bg, double *o) {
    static const struct { const char *n; unsigned v; } P[] = {{"black", 0}, {"red", 0xff0000}, {"green", 0x00ff00}, {"yellow", 0xffff00}, {"blue", 0x0000ff},
        {"magenta", 0xff00ff}, {"cyan", 0x00ffff}, {"accent", 0x00ffff}, {"white", 0xffffff}};
    unsigned v = 0;
    int found = 0;
    for (size_t i = 0; i < sizeof P / sizeof P[0]; i++) if (!strcmp(c, P[i].n)) { v = P[i].v; found = 1; }
    if (strlen(c) == 7 && c[0] == '#') {
        char *e;
        unsigned long u = strtoul(c + 1, &e, 16);
        if (*e == 0) { v = (unsigned)u; found = 1; }
    }
    if (!found && !bg) v = 0xffffff;
    o[0] = (double)(v >> 16); o[1] = (double)(v >> 8 & 255); o[2] = (double)(v & 255);
}
static void over_cell(mdgl_cell_t *d, uint32_t glyph, const char *color, double opacity) {
    opacity = fmax(0, fmin(1, opacity));
    if (opacity == 0) return;
    if (opacity == 1) { d->rune = glyph; snprintf(d->fg, sizeof d->fg, "%s", color); return; }
    double below[3], fg[3];
    if (d->rune == ' ') rgb_of(d->bg, 1, below); else rgb_of(d->fg, 0, below);
    rgb_of(color, 0, fg);
    for (int i = 0; i < 3; i++) fg[i] = round(fg[i] * opacity + below[i] * (1 - opacity));
    d->rune = glyph;
    snprintf(d->fg, sizeof d->fg, "#%02x%02x%02x", (int)fg[0], (int)fg[1], (int)fg[2]);
}

static const double *actor_t(const astate_t *a, const mdgl_actor_t *ac, double *tmp) {
    if (a->has_t) return a->t;
    double ax = ac->width / 2, ay = ac->height, pos[3] = {a->x + ax, -2 * a->y - ay, 0}, scl[3] = {a->scale, a->scale, a->scale};
    mat4 c, t;
    m_compose(pos, a->rot, scl, c);
    m_trans(-ax, ay, 0, t);
    m_mul(c, t, tmp);
    return tmp;
}

typedef struct { unsigned char *d; int w, h; } dots_t;

static void dline(dots_t *dt, double sx, double sy, double ex, double ey) {
    sx = round(sx * 1e9) / 1e9; sy = round(sy * 1e9) / 1e9; ex = round(ex * 1e9) / 1e9; ey = round(ey * 1e9) / 1e9;
    double width = dt->w - 1, height = dt->h - 1, dx = ex - sx, dy = ey - sy, lo = 0, hi = 1;
    double b[4][2] = {{-dx, sx}, {dx, width - sx}, {-dy, sy}, {dy, height - sy}};
    for (int i = 0; i < 4; i++) {
        double dir = b[i][0], dist = b[i][1];
        if (dir == 0) { if (dist < 0) return; continue; }
        double ratio = dist / dir;
        if (dir < 0) lo = fmax(lo, ratio); else hi = fmin(hi, ratio);
        if (lo > hi) return;
    }
    double cx = sx + lo * dx, cy = sy + lo * dy;
    ex = sx + hi * dx; ey = sy + hi * dy;
    int steps = (int)fmin(800, ceil(fmax(fabs(ex - cx), fabs(ey - cy))));
    if (steps <= 0) steps = 1;
    for (int s = 0; s <= steps; s++) {
        double p = (double)s / steps;
        int h = (int)round(cx + (ex - cx) * p), v = (int)round(cy + (ey - cy) * p);
        if (v >= 0 && v < dt->h && h >= 0 && h < dt->w) dt->d[v * dt->w + h] = 1;
    }
}

static void paint_text(grid_t *g, const astate_t *a, const mdgl_actor_t *ac, const char *text, double ox, double oy, double maxw) {
    size_t n = strlen(text);
    long count = mdgl_i_glyph_count(text, n);
    uint32_t *gl = malloc((size_t)(count ? count : 1) * sizeof *gl);
    if (!gl) return;
    int st = -1, w;
    long gi = 0;
    for (size_t off = 0; off < n && gi < count;) {
        size_t c = mdgl_grapheme_step(text + off, n - off, &st, &w);
        uint32_t glyph = ' ';
        if (w > 1) glyph = 0xFFFD;
        else
            for (size_t k = 0; k < c;) {
                uint32_t r;
                k += (size_t)mdgl_i_u8dec((const unsigned char *)text + off + k, c - k, &r);
                if (!mdgl_i_is_mark(r) && r != 0x200D) { glyph = r; break; }
            }
        gl[gi++] = glyph;
        off += c;
    }
    long limit = (long)floor(maxw * a->reveal + 1e-9);
    if (limit > count) limit = count;
    double tmp[16];
    const double *T = actor_t(a, ac, tmp);
    for (long i = 0; i < limit; i++) {
        double p[4] = {ox + (double)i, -2 * oy, 0, 1}, q[4];
        m_xform(T, p, q);
        double h = round(q[0]), v = round(-q[1] / 2);
        if (h < 0 || v < 0 || v >= g->rows || h >= g->cols) continue;
        if (gl[i] != ' ') over_cell(&g->g[(int)v * g->cols + (int)h], gl[i], a->color, a->opacity);
    }
    free(gl);
}

static void cube_lines(dots_t *dt, const astate_t *a, const mdgl_actor_t *ac) {
    double size = ac->width, tmp[16];
    const double *world = actor_t(a, ac, tmp);
    double c0[4] = {size / 2, -ac->height, 0, 1}, center[4];
    m_xform(world, c0, center);
    mat4 view, proj, pv, matrix;
    m_trans(-center[0], -center[1], -3 * ac->width, view);
    m_persp(50, ac->width / (2 * ac->height), 0.1, 1000, proj);
    m_mul(proj, view, pv);
    m_mul(pv, world, matrix);
    double corners[8][4];
    for (int i = 0; i < 8; i++) {
        double hx = i & 1 ? 0.5 : -0.5, vy = i & 2 ? 0.5 : -0.5, dz = i & 4 ? 0.5 : -0.5;
        double p[4] = {size / 2 + hx * size, -ac->height + vy * size, dz * size, 1};
        m_xform(matrix, p, corners[i]);
    }
    for (int i = 0; i < 8; i++)
        for (int bi = 0; bi < 3; bi++) {
            int other = i ^ (1 << bi);
            if (other > i) {
                double cs[4], ce[4], sx, sy, ex, ey;
                if (!v_clip(corners[i], corners[other], cs, ce)) continue;
                v_port(cs, size, ac->height, &sx, &sy);
                v_port(ce, size, ac->height, &ex, &ey);
                double ox = center[0] - size / 2, oy = -center[1] / 2 - ac->height / 2;
                dline(dt, (ox + sx) * 2 - 0.5, (oy + sy) * 4 - 0.5, (ox + ex) * 2 - 0.5, (oy + ey) * 4 - 0.5);
            }
        }
}

static int render(const mdgl_scene_t *sc, const astate_t *st, int cols, int rows, mdgl_frame_t *out) {
    cols = cols < 0 ? 0 : cols > 200 ? 200 : cols;
    rows = rows < 0 ? 0 : rows > 60 ? 60 : rows;
    out->width = cols; out->height = rows;
    out->cells = calloc((size_t)((cols && rows) ? cols * rows : 1), sizeof *out->cells);
    if (!out->cells) return -1;
    grid_t g = {cols, rows, out->cells};
    for (int i = 0; i < cols * rows; i++) { out->cells[i].rune = ' '; strcpy(out->cells[i].fg, "normal"); }
    if (!rows || !cols) return 0;
    int na = sc->nactors;
    int *order = malloc((size_t)(na ? na : 1) * sizeof *order);
    dots_t dt = {calloc((size_t)rows * 4 * (size_t)cols * 2, 1), cols * 2, rows * 4};
    if (!order || !dt.d) { free(order); free(dt.d); free(out->cells); out->cells = NULL; return -1; }
    for (int i = 0; i < na; i++) {
        int j = i;
        while (j > 0 && st[order[j - 1]].z > st[i].z) { order[j] = order[j - 1]; j--; }
        order[j] = i;
    }
    for (int k = 0; k < na; k++) {
        const astate_t *a = &st[order[k]];
        const mdgl_actor_t *ac = &sc->actors[order[k]];
        if (a->opacity <= 0 || a->reveal <= 0) continue;
        if (!strcmp(ac->kind, "text")) { paint_text(&g, a, ac, ac->text, 0, 0, ac->width); continue; }
        memset(dt.d, 0, (size_t)dt.w * (size_t)dt.h);
        double w = ac->width, h = ac->height, lastX = fmax(0, w * 2 - 1), lastY = fmax(0, h * 4 - 1);
        double tmp[16];
        const double *T = actor_t(a, ac, tmp);
        mat4 ortho, M;
        m_ortho(0, cols, -2.0 * rows, 0, -1000, 1000, ortho);
        m_mul(ortho, T, M);
#define SEG(X0, Y0, X1, Y1) do { double p0[4] = {(X0) / 2, -(Y0) / 2, 0, 1}, p1[4] = {(X1) / 2, -(Y1) / 2, 0, 1}, q0[4], q1[4], c0[4], c1[4], ax, ay, bx, by; \
            m_xform(M, p0, q0); m_xform(M, p1, q1); \
            if (v_clip(q0, q1, c0, c1)) { v_port(c0, cols * 2.0, rows * 4.0, &ax, &ay); v_port(c1, cols * 2.0, rows * 4.0, &bx, &by); dline(&dt, ax, ay, bx, by); } } while (0)
        if (!strcmp(ac->kind, "rect")) { SEG(0, 0, lastX, 0); SEG(lastX, 0, lastX, lastY); SEG(lastX, lastY, 0, lastY); SEG(0, lastY, 0, 0); }
        else if (!strcmp(ac->kind, "circle")) {
            double cx = lastX / 2, cy = lastY / 2, rx = lastX / 2, ry = lastY / 2, px = cx + rx, py = cy;
            for (int s = 1; s <= 720; s++) {
                double ang = (double)s * M_PI / 360, nx = cx + rx * cos(ang), ny = cy + ry * sin(ang);
                SEG(px, py, nx, ny);
                px = nx; py = ny;
            }
        } else if (!strcmp(ac->kind, "cube")) cube_lines(&dt, a, ac);
        static const int BIT[4][2] = {{0, 3}, {1, 4}, {2, 5}, {6, 7}};
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++) {
                int mask = 0;
                for (int v = 0; v < 4; v++) for (int hh = 0; hh < 2; hh++) if (dt.d[(r * 4 + v) * dt.w + c * 2 + hh]) mask |= 1 << BIT[v][hh];
                if (mask && (a->reveal >= 1 || (double)c + 0.5 <= a->x + w * a->scale * a->reveal))
                    over_cell(&out->cells[r * cols + c], 0x2800u + (unsigned)mask, a->color, a->opacity);
            }
        if (!strcmp(ac->kind, "rect") && ac->text[0]) paint_text(&g, a, ac, ac->text, 1, 0, fmax(0, ac->width - 2));
    }
    free(order); free(dt.d);
    return 0;
}

/* ---------- public API ---------- */

int mdgl_scene_active(const mdgl_scene_t *sc, double t) {
    return sc && sc->checked && isfinite(t) && sc->period > 0 &&
           (sc->repeat == 0 || mdgl_i_gotime(t) < mdgl_i_gotime(sc->period * (double)sc->repeat));
}

static int clampdim(int v, int m) { return v < m ? v : m; }

int mdgl_frame(const mdgl_scene_t *sc, double t, int cols, int rows, mdgl_frame_t *out, int *done) {
    if (!sc || !sc->checked || !out) return -1;
    if (!isfinite(t) || t < 0) t = 0;
    t = mdgl_i_gotime(t);
    int d = !mdgl_scene_active(sc, t);
    if (sc->period > 0) {
        if (d) t = sc->period;
        else { t = mdgl_i_gotime(fmod(t, sc->period)); if (t == sc->period) t = 0; }
    }
    astate_t *st = eval_at(sc, t);
    if (!st) return -1;
    int rc = render(sc, st, clampdim(cols, sc->width), clampdim(rows, sc->height), out);
    free(st);
    if (done) *done = d;
    return rc;
}
int mdgl_frame_ns(const mdgl_scene_t *sc, long long ns, int cols, int rows, mdgl_frame_t *out, int *done) {
    return mdgl_frame(sc, (double)ns / 1e9, cols, rows, out, done);
}
int mdgl_fallback_frame(const mdgl_scene_t *sc, int cols, int rows, mdgl_frame_t *out) {
    if (!sc || !sc->checked || !out) return -1;
    double t = 0;
    if (!strcmp(sc->fallback, "end")) t = sc->period;
    else if (sc->fallback[0] == '@') mdgl_i_number_t(sc->fallback + 1, strlen(sc->fallback + 1), &t);
    astate_t *st = eval_at(sc, t);
    if (!st) return -1;
    int rc = render(sc, st, clampdim(cols, sc->width), clampdim(rows, sc->height), out);
    free(st);
    return rc;
}
void mdgl_frame_free(mdgl_frame_t *f) { if (f) { free(f->cells); f->cells = NULL; } }

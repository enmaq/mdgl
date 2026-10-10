#include "mdgl.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE "scene width=8 height=1 fallback=end\n"
static int failures;

static void expect(const char *name, const char *src, size_t len, int ok) {
    mdgl_diag_t d[MDGL_MAX_DIAGS];
    int n = mdgl_check_n(src, len, d, MDGL_MAX_DIAGS);
    if ((n == 0) != ok) { printf("FAIL %s: got %d diags (%s)\n", name, n, n > 0 ? d[0].message : ""); failures++; }
}
static void lit(const char *name, const char *src, int ok) { expect(name, src, strlen(src), ok); }

static void built(const char *name, const char *prefix, const char *unit, size_t count, size_t padto, int ok) {
    size_t pl = strlen(prefix), ul = strlen(unit);
    size_t total = padto ? padto : pl + ul * count;
    char *b = malloc(total + 1);
    memcpy(b, prefix, pl);
    if (padto) memset(b + pl, '\n', total - pl);
    else for (size_t i = 0; i < count; i++) memcpy(b + pl + i * ul, unit, ul);
    expect(name, b, total, ok);
    free(b);
}

static void line_case(const char *name, size_t n, int ok) {
    size_t pl = strlen(BASE), total = pl + n + 1;
    char *b = malloc(total);
    memcpy(b, BASE, pl);
    b[pl] = '#';
    memset(b + pl + 1, 'x', n - 1);
    b[total - 1] = '\n';
    expect(name, b, total, ok);
    free(b);
}

static void actions_case(const char *name, int n, int ok) {
    const char *pre = BASE "actor a = text(\"AB\") at (0, 0)\n";
    char *b = malloc(strlen(pre) + (size_t)n * 48 + 1), *w;
    strcpy(b, pre);
    w = b + strlen(b);
    for (int i = 0; i < n; i++) w += sprintf(w, "@%.2f: a.move(to=(%d, 0), dur=0.01)\n", i * 0.05, i % 2);
    expect(name, b, (size_t)(w - b), ok);
    free(b);
}

int main(void) {
    lit("minimal", BASE, 1);
    lit("version", "mdgl 0.1\n" BASE, 1);
    lit("order", "scene fallback=start height=60 width=200\n", 1);
    lit("comments", "# hi\n\n" BASE, 1);
    lit("empty", "\n", 0);
    lit("no width", "scene height=1 fallback=end\n", 0);
    lit("no height", "scene width=8 fallback=end\n", 0);
    lit("no fallback", "scene width=8 height=1 period=4\n", 0);
    lit("width 0", "scene width=0 height=1 fallback=end\n", 0);
    lit("width 201", "scene width=201 height=1 fallback=end\n", 0);
    lit("height 61", "scene width=8 height=61 fallback=end\n", 0);
    lit("dup key", "scene width=8 width=9 height=1 fallback=end\n", 0);
    lit("unknown key", "scene width=8 height=1 fallback=end bogus=1\n", 0);
    lit("dup scene", BASE BASE, 0);
    lit("actor first", "actor a = circle(1) at (0, 0)\n" BASE, 0);
    lit("actor after action", BASE "@0: a.fade(in, dur=1)\nactor a = circle(1) at (0, 0)\n", 0);
    lit("unknown stmt", BASE "bogus\n", 0);
    built("size 256KiB", BASE, "", 0, 262144, 1);
    built("size +1", BASE, "", 0, 262145, 0);
    line_case("line 16384", 16384, 1);
    line_case("line 16385", 16385, 0);
    built("64 actors", BASE, "actor a = circle(1) at (0, 0)\n", 64, 0, 1);
    built("65 actors", BASE, "actor a = circle(1) at (0, 0)\n", 65, 0, 0);
    actions_case("1024 actions", 1024, 1);
    actions_case("1025 actions", 1025, 0);
    if (mdgl_check(NULL, NULL, 0) != -1) { puts("FAIL null out"); failures++; }
    if (strcmp(MDGL_VERSION, "0.2.0") != 0) { puts("FAIL version"); failures++; }
    if (failures) { printf("c check: %d FAILED\n", failures); return 1; }
    printf("c check: OK (mdgl %s, subset)\n", MDGL_VERSION);
    return 0;
}

# mdgl (C - subset, NOT conformant)

A tiny **subset** checker for [MDGL](https://github.com/enmaq/mdgl), not an MDGL
parser; it does not pass the conformance suite. The Go module is the reference.
C has no central registry: this is distributed as a **source tarball only**
(a `mdgl-c-<VERSION>` source tarball: `mdgl.h`, `mdgl.c`, `test_check.c`, `CMakeLists.txt`,
README and licenses).

## Scope

Checked (mirrors the Go reference on these rules only): input <= 256 KiB, each
line <= 16 KiB, a single `scene` header with `width` (1..200), `height` (1..60)
and `fallback`, no unknown/duplicate scene keys, optional leading `mdgl 0.1`,
scene before actors before actions, <= 64 actors, <= 1024 actions.

NOT checked: full grammar, actor/action bodies, references, timing, arguments,
`period`/`repeat`/`fps`/`fallback` values, string limits, rendering, frames,
and raw-byte UTF-8 validity (unlike the Go reference).

`mdgl_check(src, out, n)` / `mdgl_check_n(src, len, out, n)` return the number
of diagnostics; `0` means "no limit/header problems found", **not** "valid MDGL".

```
cmake -B build && cmake --build build && ./build/mdgl_check_test
```

## Install and versions

There is no registry: unpack the source tarball (recorded in the release record) and add `mdgl.c` to your build, or use the bundled `CMakeLists.txt`.

```c
#include "mdgl.h"

mdgl_diag_t diags[MDGL_MAX_DIAGS];
int n = mdgl_check("scene width=8 height=1 fallback=end\n", diags, MDGL_MAX_DIAGS);
/* n == 0: no limit/header problems; n > 0: diags[i].line, .col, .message; n == -1: bad arguments */
```

Versions track the shared MDGL release (`VERSION`). The package will be published with the 0.2.0 cohort; see [RELEASING.md](../RELEASING.md).

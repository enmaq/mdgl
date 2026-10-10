# mdgl (Python - subset, NOT conformant)

A tiny **subset** checker for [MDGL](https://github.com/enmaq/mdgl), not an MDGL
parser; it does not pass the conformance suite. The Go module is the reference.

## Scope

Checked (mirrors the Go reference on these rules only): input <= 256 KiB (UTF-8
bytes), each line <= 16 KiB, a single `scene` header with `width` (1..200),
`height` (1..60) and `fallback`, no unknown/duplicate scene keys, optional
leading `mdgl 0.1`, scene before actors before actions, <= 64 actors,
<= 1024 actions.

NOT checked: full grammar, actor/action bodies, references, timing, arguments,
`period`/`repeat`/`fps`/`fallback` values, string limits, rendering, frames.
`str` only (bytes are not accepted, so raw invalid-UTF-8 input is not tested).

`check(source)` returns a list of `{"line", "col", "message"}`. `[]` means
"no limit/header problems found", **not** "valid MDGL".

```python
from mdgl import check
assert check("scene width=8 height=1 fallback=end\n") == []
```

## Install and versions

```
pip install mdgl
```

```python
import mdgl
problems = mdgl.check(source)  # list of {"line","col","message"}; [] = no limit/header problems
print(mdgl.__version__)
```

Versions track the shared MDGL release (`VERSION`). The package will be published with the 0.2.0 cohort; see [RELEASING.md](../RELEASING.md).

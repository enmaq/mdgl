# @enmaq/mdgl (npm - subset, NOT conformant)

One npm package for JavaScript and TypeScript. The TypeScript source is
`src/index.ts`; `npm run build` (`tsc`, also run by `prepack` and `npm test`)
compiles it to `dist/index.js` (CommonJS) plus `dist/index.d.ts`. `dist/` is a
build artifact and is not committed.

This is a **SUBSET** check, not full MDGL: a tiny limit/header checker, not an
MDGL parser. It does not pass the conformance suite. The Go module is the
reference.

## Scope

Checked (mirrors the Go reference on these rules only): input <= 256 KiB (UTF-8
bytes), each line <= 16 KiB, a single `scene` header with `width` (1..200),
`height` (1..60) and `fallback`, no unknown/duplicate scene keys, optional
leading `mdgl 0.1`, scene before actors before actions, <= 64 actors,
<= 1024 actions.

NOT checked: full grammar, actor/action bodies, references, timing, arguments,
`period`/`repeat`/`fps`/`fallback` values, string limits, rendering, frames.
JS strings cannot hold invalid UTF-8, so that rule is not applicable.

`check(source)` returns `Diag[]` (`{line, col, message}`; also exported as
`Problem`, with `CheckResult = Diag[]`). An empty array means
"no limit/header problems found", **not** "valid MDGL". Non-strings throw `TypeError`.

```ts
import { check } from '@enmaq/mdgl';
console.log(check('scene width=8 height=1 fallback=end\n')); // []
```

## Development

`npm test` builds, type-checks `test/consumer/consumer.ts` (strict typed
consumer) and runs the shared 25-case table against `dist/`.

## Install and versions

```
npm install @enmaq/mdgl
```

```ts
import { check } from '@enmaq/mdgl';   // CommonJS: const { check } = require('@enmaq/mdgl');
const diags = check(source);    // Diag[] of {line, col, message}; [] = no limit/header problems
```

Versions track the shared MDGL release (`VERSION`). The package will be published with the 0.2.0 cohort; see [RELEASING.md](../RELEASING.md).

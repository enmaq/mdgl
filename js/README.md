# mdgl for JavaScript

JavaScript and TypeScript share ONE npm package, `@enmaq/mdgl`, built from [`../ts`](../ts):
TypeScript source in `ts/src`, compiled to JavaScript plus `.d.ts`. This folder
holds no separate implementation.

```js
const { check } = require('@enmaq/mdgl');
console.log(check('scene width=8 height=1 fallback=end\n')); // []
```

In this development tree (unreleased) the same package also has an evaluator, terminal-cell renderer and
protocol adapter, compiled from TypeScript; see the [`ts` README](../ts/README.md). Published 0.2.0 is only
the earlier limit/header subset checker.

## Example

A runnable JavaScript example is in [`../ts/examples/render.mjs`](../ts/examples/render.mjs); see the
[`ts` README](../ts/README.md#examples) for the commands.

## Install and versions

```
npm install @enmaq/mdgl
```

Use `require('@enmaq/mdgl')` as above; TypeScript types ship in the same package.

Versions track the shared MDGL release (`VERSION`); `npm install @enmaq/mdgl` gives the published 0.2.0 seed check. See [RELEASING.md](../RELEASING.md).

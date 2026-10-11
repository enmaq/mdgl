# mdgl for JavaScript

JavaScript and TypeScript share ONE npm package, `@enmaq/mdgl`, built from [`../ts`](../ts):
TypeScript source in `ts/src`, compiled to JavaScript plus `.d.ts`. This folder
holds no separate implementation.

```js
const { check } = require('@enmaq/mdgl');
console.log(check('scene width=8 height=1 fallback=end\n')); // []
```

In this source tree (0.3.0 release candidate, not yet published) the same package also has an evaluator, terminal-cell renderer and
protocol adapter, compiled from TypeScript; see the [`ts` README](../ts/README.md). Published 0.2.0 is only
the earlier limit/header subset checker.

## Example

A runnable JavaScript example is in [`../ts/examples/render.mjs`](../ts/examples/render.mjs); see the
[`ts` README](../ts/README.md#examples) for the commands.

## Terminal player

`mdgl play FILE` is part of the 0.3.0 release candidate (not yet published; `npm install @enmaq/mdgl` currently gives the 0.2.0 seed check); see the [`ts` README](../ts/README.md#terminal-player-mdgl-play-file).

## Install and versions

```
npm install @enmaq/mdgl
```

Use `require('@enmaq/mdgl')` as above; TypeScript types ship in the same package.

Versions track the shared MDGL release (`VERSION`); `npm install @enmaq/mdgl` gives the published 0.2.0 seed check. See [RELEASING.md](../RELEASING.md).

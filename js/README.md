# mdgl for JavaScript

JavaScript and TypeScript share ONE npm package, `@enmaq/mdgl`, built from [`../ts`](../ts):
TypeScript source in `ts/src`, compiled to JavaScript plus `.d.ts`. This folder
holds no separate implementation.

```js
const { check } = require('@enmaq/mdgl');
console.log(check('scene width=8 height=1 fallback=end\n')); // []
```

The same package has a full parser, checker, evaluator, terminal-cell renderer and
protocol adapter, compiled from TypeScript; see the [`ts` README](../ts/README.md).

## Example

A runnable JavaScript example is in [`../ts/examples/render.mjs`](../ts/examples/render.mjs); see the
[`ts` README](../ts/README.md#examples) for the commands.

## Terminal player

`mdgl play FILE` animates a scene in the terminal (`npx -p @enmaq/mdgl@0.3.0 mdgl play scene.mdgl`); see the [`ts` README](../ts/README.md#terminal-player-mdgl-play-file).

## Install and versions

```
npm install @enmaq/mdgl@0.3.0
```

Use `require('@enmaq/mdgl')` as above; TypeScript types ship in the same package.

Versions track the shared MDGL release (`VERSION`); `npm install @enmaq/mdgl@0.3.0` pins 0.3.0. See [RELEASING.md](../RELEASING.md).

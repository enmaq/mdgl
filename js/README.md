# mdgl for JavaScript

JavaScript and TypeScript share ONE npm package, `@enmaq/mdgl`, built from [`../ts`](../ts):
TypeScript source in `ts/src`, compiled to JavaScript plus `.d.ts`. This folder
holds no separate implementation.

```js
const { check } = require('@enmaq/mdgl');
console.log(check('scene width=8 height=1 fallback=end\n')); // []
```

It is a **SUBSET** check (limits and scene header), not full MDGL; see the
[`ts` README](../ts/README.md) for scope.

## Install and versions

```
npm install @enmaq/mdgl
```

Use `require('@enmaq/mdgl')` as above; TypeScript types ship in the same package.

Versions track the shared MDGL release (`VERSION`). The package will be published with the 0.2.0 cohort; see [RELEASING.md](../RELEASING.md).

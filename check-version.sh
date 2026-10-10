#!/bin/sh
# Verify every package version matches the root VERSION file.
cd "$(dirname "$0")" || exit 2
rc=0
v=$(sed -n '1p' VERSION 2>/dev/null)
case $v in
  ''|*[!0-9A-Za-z.+-]*) echo "VERSION: invalid '$v'"; exit 1;;
esac
echo "$v" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$' \
  || { echo "VERSION: '$v' is not strict semver"; exit 1; }
chk() { # file found
  if [ "$2" != "$v" ]; then echo "MISMATCH $1: '$2' != VERSION '$v'"; rc=1; fi
}
chk ts/package.json "$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' ts/package.json | sed -n 1p)"
chk rust/Cargo.toml "$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' rust/Cargo.toml | sed -n 1p)"
chk python/pyproject.toml "$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' python/pyproject.toml | sed -n 1p)"
chk c/mdgl.h "$(sed -n 's/^#define MDGL_VERSION *"\([^"]*\)".*/\1/p' c/mdgl.h | sed -n 1p)"
chk c/CMakeLists.txt "$(sed -n 's/^project(mdgl VERSION \([^ )]*\).*/\1/p' c/CMakeLists.txt | sed -n 1p)"
chk python/mdgl/__init__.py "$(sed -n 's/^__version__ *= *["'"'"']\([^"'"'"']*\)["'"'"'].*/\1/p' python/mdgl/__init__.py 2>/dev/null | sed -n 1p)"
chk ts/src/index.ts "$(sed -n "s/^export const VERSION *\(: *string\)\{0,1\} *= *['\"]\([^'\"]*\)['\"].*/\2/p" ts/src/index.ts 2>/dev/null | sed -n 1p)"
chk CHANGELOG.md "$(sed -n 's/^## \[\([0-9][^]]*\)\].*/\1/p' CHANGELOG.md | sed -n 1p)"
[ $rc -eq 0 ] && echo "versions OK: $v"
exit $rc

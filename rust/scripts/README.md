# Width-table and glyph-corpus provenance

`src/width_tables.rs` is generated, never hand-edited. Reference profile (compatibility, not the SPEC norm):
Go `github.com/rivo/uniseg` **v0.4.7**, Unicode **15.0.0**, plus the General_Category `M*` ranges of a Go
toolchain whose `unicode.Version` is `15.0.0` (Go 1.21 to 1.25).

SPEC.md only says "first non-mark rune; wide glyphs are U+FFFD"; the cluster-width rules used here are the
reference implementation's, documented as such. A different Unicode version can change results.

## Regenerate the tables

```sh
git clone --branch v0.4.7 https://github.com/rivo/uniseg "$UNISEG"
(cd scripts/marks && go run .) > "$WORK/marks.txt"          # first line: "//V 15.0.0"
python3 scripts/gen_width_tables.py "$UNISEG" "$WORK/marks.txt" > src/width_tables.rs
```

Licence of the derived data: `LICENSE-UNISEG` (MIT), shipped in the crate.

## Reproduce the 250112 reference cases

The corpus is the output of the Go reference `model.Glyphs` over 47 curated sequences (flags, VS15/VS16,
keycaps, ZWJ, zero-width, leading marks, prepend, Hangul, Indic, tag flags) plus every scalar U+0020..U+2FFFF
(excluding surrogates and C0/C1 controls), each alone and every 7th also followed by U+FE0F and U+0301.

```sh
mkdir "$WORK/glyphref" && cp scripts/glyphref/main.go "$WORK/glyphref/"
cd "$WORK/glyphref"
cat > go.mod <<EOT
module glyphref
go 1.21
require github.com/enmaq/mdgl/go v0.0.0
require github.com/rivo/uniseg v0.4.7
replace github.com/enmaq/mdgl/go => $MDGL_GO_DIR
EOT
go run . > "$WORK/glyph-ref.tsv"              # expect 250112 lines
cd - && MDGL_GLYPH_REF="$WORK/glyph-ref.tsv" cargo test --test glyph_ref
```

Run on 2026-10-10 the file had sha256 `97c5f977f7945dc4…` (prefix) and the Rust implementation matched all
lines. Shared runner evidence for the same tree: 80 fixtures pass (63 normative, 17 assumption-based), report
sha256 prefix `710f277e36cf9a2d`. Full machine-specific logs stay outside the repository.

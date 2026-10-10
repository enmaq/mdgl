//! Differential check of `cell_glyphs` against a reference corpus (`MDGL_GLYPH_REF=file.tsv`,
//! lines `hex scalars<TAB>hex glyphs`, produced by the Go reference `model.Glyphs`, uniseg v0.4.7,
//! Unicode 15.0). Skipped when the variable is unset; the corpus is not part of the library tree.
use std::{env, fs};

#[test]
fn matches_reference_corpus() {
    let Ok(path) = env::var("MDGL_GLYPH_REF") else { return };
    let (mut n, mut bad) = (0, Vec::new());
    for line in fs::read_to_string(path).unwrap().lines() {
        let (seq, want) = line.split_once('\t').unwrap();
        let text: String = seq.split(' ').map(|h| char::from_u32(u32::from_str_radix(h, 16).unwrap()).unwrap()).collect();
        let got: Vec<String> = mdgl::cell_glyphs(&text).iter().map(|c| format!("{:X}", *c as u32)).collect();
        if got.join(" ") != want {
            bad.push(format!("{seq} => got {} want {want}", got.join(" ")));
        }
        n += 1;
    }
    assert!(bad.is_empty(), "{} of {n} differ, first: {:?}", bad.len(), &bad[..bad.len().min(25)]);
}

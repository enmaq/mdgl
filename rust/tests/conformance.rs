//! Shared corpus: every `.err` fixture's first diagnostic matches exactly; every `.expect` fixture checks clean.
use std::fs;

#[test]
fn corpus_diagnostics() {
    let dir = concat!(env!("CARGO_MANIFEST_DIR"), "/../conformance");
    let (mut errs, mut oks) = (0, 0);
    for e in fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        let (Some(stem), Some(ext)) = (p.file_stem(), p.extension()) else { continue };
        let src = || fs::read_to_string(p.with_extension("mdgl")).unwrap();
        match ext.to_str().unwrap() {
            "err" => {
                let d = mdgl::check(&src());
                let want = fs::read_to_string(&p).unwrap();
                assert_eq!(d.first().map(|d| d.to_string()).as_deref(), Some(want.trim_end()), "{stem:?}");
                errs += 1;
            }
            "expect" => {
                let d = mdgl::check(&src());
                assert!(d.is_empty(), "{stem:?}: {d:?}");
                oks += 1;
            }
            _ => {}
        }
    }
    assert!(errs >= 10 && oks > 0, "{errs} {oks}");
}

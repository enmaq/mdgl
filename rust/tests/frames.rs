//! Legacy `.expect` glyph rows and observable `.obs.json` fixtures (colours, done, fallback).
use std::fs;

fn dir() -> String {
    concat!(env!("CARGO_MANIFEST_DIR"), "/../conformance").into()
}

/// Canonical decimal seconds to nanoseconds, integer arithmetic.
fn ns(s: &str) -> u64 {
    let (w, f) = s.split_once('.').unwrap_or((s, ""));
    w.parse::<u64>().unwrap() * 1_000_000_000 + format!("{f:0<9}").parse::<u64>().unwrap()
}

#[test]
fn legacy_expect_rows() {
    let mut n = 0;
    for e in fs::read_dir(dir()).unwrap() {
        let p = e.unwrap().path();
        if p.extension().is_none_or(|x| x != "expect") {
            continue;
        }
        let scene = mdgl::parse_checked(&fs::read_to_string(p.with_extension("mdgl")).unwrap()).unwrap();
        let text = fs::read_to_string(&p).unwrap();
        let lines: Vec<&str> = text.trim_end_matches('\n').split('\n').collect();
        let mut i = 0;
        while i < lines.len() {
            let t: f64 = lines[i].trim_start_matches('@').parse().unwrap();
            let rows = scene.frame(t, scene.width as usize, scene.height as usize).lines();
            for (r, got) in rows.iter().enumerate() {
                let want = format!("{:<w$}", lines[i + 1 + r], w = scene.width as usize);
                assert_eq!(*got, want, "{:?} @{t} row {r}", p.file_name().unwrap());
            }
            i += 1 + scene.height as usize;
            n += 1;
        }
    }
    assert!(n > 20, "{n} frames");
}

#[test]
fn observable_fixtures() {
    let mut total = 0;
    for e in fs::read_dir(format!("{}/observable", dir())).unwrap() {
        let p = e.unwrap().path();
        if !p.to_string_lossy().ends_with(".obs.json") {
            continue;
        }
        let j: serde_json::Value = serde_json::from_str(&fs::read_to_string(&p).unwrap()).unwrap();
        let Some(frames) = j["frames"].as_array() else { continue };
        let src = fs::read_to_string(p.parent().unwrap().join(j["source_file"].as_str().unwrap())).unwrap();
        let Ok(scene) = mdgl::parse_checked(&src) else { continue };
        let (cols, rows) = (j["cols"].as_u64().unwrap() as usize, j["rows"].as_u64().unwrap() as usize);
        for f in frames {
            let fr = if f["fallback"].as_bool() == Some(true) { scene.fallback_frame(cols, rows) } else { scene.frame_ns(ns(f["time"].as_str().unwrap()), cols, rows) };
            let name = p.file_name().unwrap().to_string_lossy().to_string();
            for (r, row) in f["cells"].as_array().unwrap().iter().enumerate() {
                for (c, cell) in row.as_array().unwrap().iter().enumerate() {
                    let got = &fr.cells[r][c];
                    assert_eq!(got.rune.to_string(), cell["r"].as_str().unwrap(), "{name} {f} r{r} c{c}");
                    // Glyph-only fixtures (cube class) omit fg/bg: compare what is stated.
                    if let Some(fg) = cell["fg"].as_str() {
                        assert_eq!((got.fg.as_str(), got.bg.as_str()), (fg, cell["bg"].as_str().unwrap_or("")), "{name} {f} r{r} c{c}");
                    }
                }
            }
            if let Some(d) = f["done"].as_bool() {
                assert_eq!(fr.done, d, "{name} done {f}");
            }
            total += 1;
        }
    }
    assert!(total > 10, "{total}");
}

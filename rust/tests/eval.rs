//! Targeted evaluator/renderer discriminators derived from SPEC text.
use mdgl::{cell_glyphs, parse_checked};

fn scene(body: &str) -> mdgl::Scene {
    parse_checked(body).unwrap()
}

#[test]
fn repeat_boundaries_done_and_seek_purity() {
    let s = scene("scene width=4 height=1 period=2 repeat=2 fallback=start\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in, dur=2)\n");
    // interior boundary (t=2s) starts the next cycle: opacity back to 0 -> blank
    assert_eq!(s.frame_ns(1_999_999_999, 4, 1).lines()[0], "A   ");
    let at2 = s.frame_ns(2_000_000_000, 4, 1);
    assert_eq!((at2.lines()[0].as_str(), at2.done), ("    ", false));
    // at/after total duration the last cycle's end is held and done
    let end = s.frame_ns(4_000_000_000, 4, 1);
    assert_eq!((end.lines()[0].as_str(), end.done), ("A   ", true));
    // seeking is pure: any order gives the same frame
    let a = s.frame_ns(3_000_000_000, 4, 1);
    let _ = s.frame_ns(500_000_000, 4, 1);
    assert_eq!(a, s.frame_ns(3_000_000_000, 4, 1));
    // infinite never finishes; fallback end is the exact end state
    let inf = scene("scene width=4 height=1 period=1 repeat=infinite fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in, dur=1)\n");
    assert!(!inf.frame(1e6, 4, 1).done);
    assert_eq!(inf.fallback_frame(4, 1).lines()[0], "A   ");
}

#[test]
fn blend_and_paint_order() {
    let s = scene("scene width=2 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=red z=1\nactor b = text(\"B\") at (0,0) color=blue\n");
    let f = s.frame(0.0, 2, 1);
    assert_eq!((f.cells[0][0].rune, f.cells[0][0].fg.as_str()), ('A', "red")); // higher z on top
}

#[test]
fn type_uses_whole_clusters() {
    let s = scene("scene width=6 height=1 fallback=end\nactor a = text(\"e\u{301}x\") at (0,0)\n@0: a.type(per_char=1)\n");
    assert_eq!(s.frame_ns(999_999_999, 6, 1).lines()[0].trim(), "");
    assert_eq!(s.frame_ns(1_000_000_000, 6, 1).lines()[0].trim(), "e");
    assert_eq!(s.frame_ns(2_000_000_000, 6, 1).lines()[0].trim(), "ex");
}

#[test]
fn glyph_rule_marks_and_wide() {
    assert_eq!(cell_glyphs("e\u{301}"), vec!['e']);
    assert_eq!(cell_glyphs("\u{4e2d}"), vec!['\u{FFFD}']);
    assert_eq!(cell_glyphs("\u{1F1FA}\u{1F1F8}"), vec!['\u{FFFD}']);
    assert_eq!(cell_glyphs("a b"), vec!['a', ' ', 'b']);
}

#[test]
fn shapes_paint_braille_and_stay_in_stage() {
    let s = scene("scene width=6 height=3 fallback=end\nactor r = rect(6,3) at (0,0)\nactor c = circle(1) at (0,0) color=red\n");
    let f = s.frame(0.0, 6, 3);
    assert!(f.cells.iter().flatten().all(|c| c.rune == ' ' || ('\u{2800}'..='\u{28ff}').contains(&c.rune)));
    assert!(f.cells.iter().flatten().any(|c| c.fg == "red"));
}

#[test]
fn glyph_width_matches_reference_profile() {
    let g = |s: &str| cell_glyphs(s);
    assert_eq!(g("\u{1F1FA}"), vec!['\u{FFFD}']); // lone regional indicator is wide
    assert_eq!(g("\u{1F1FA}\u{1F1F8}\u{1F1E9}"), vec!['\u{FFFD}', '\u{FFFD}']);
    assert_eq!(g("1\u{FE0F}\u{20E3}"), vec!['1']); // keycap: narrow base, VS16 does not widen
    assert_eq!(g("#\u{FE0F}"), vec!['#']);
    assert_eq!(g("\u{2764}\u{FE0F}"), vec!['\u{FFFD}']); // pictographic + VS16 is wide
    assert_eq!(g("\u{2764}\u{FE0E}"), vec!['\u{2764}']);
    assert_eq!(g("a\u{200B}b"), vec!['a', '\u{200B}', 'b']); // zero-width format char kept as glyph
    assert_eq!(g("\u{0301}a"), vec![' ', 'a']); // a leading mark is its own cluster, glyph falls back to space
    assert_eq!(g("\u{0600}a"), vec!['\u{FFFD}']); // prepend + base = width 2
    assert_eq!(g("\u{0915}\u{093E}"), vec!['\u{FFFD}']); // spacing mark adds a cell
    assert_eq!(g("\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}"), vec!['\u{FFFD}']);
}

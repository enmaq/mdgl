//! Cluster count vs scalar count (Unicode 15.0 extended grapheme clusters).
use mdgl::{glyphs, parse_checked};

const S: &str = "scene width=8 height=2 fallback=end\n";

#[test]
fn clusters_not_scalars() {
    let cases: [(&str, usize, usize); 7] = [
        ("\u{1F1FA}\u{1F1F8}", 2, 1),                         // US flag
        ("\u{1100}\u{1161}\u{11A8}", 3, 1),                   // decomposed Hangul L V T
        ("\u{0915}\u{093E}", 2, 1),                           // Devanagari ka + spacing mark
        ("\u{0628}\u{064E}", 2, 1),                           // Arabic beh + fatha
        ("\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}", 7, 1), // England tag flag
        ("e\u{0301}", 2, 1),
        ("\u{1F1FA}\u{1F1F8}\u{1F1E9}\u{1F1EA}\u{1F1EB}", 5, 3), // RI pairing: 2 flags + lone
    ];
    for (t, scalars, clusters) in cases {
        assert_eq!((t.chars().count(), glyphs(t).len()), (scalars, clusters), "{t:?}");
    }
}

fn type_scene(text: &str, per_char: &str) -> mdgl::Scene {
    parse_checked(&format!("{S}actor a = text(\"{text}\") at (0,0)\n@0: a.type(per_char={per_char})\n")).unwrap()
}

#[test]
fn flag_and_hangul_limits_and_type_duration() {
    let flags = "\u{1F1FA}\u{1F1F8}".repeat(600);
    assert_eq!(flags.chars().count(), 1200); // over 1024 scalars, within 1024 clusters
    let s = type_scene(&flags, "0.1");
    assert_eq!(s.actors[0].width, 600.0);
    assert_eq!(s.actions[0].duration, 60.0);
    assert_eq!(s.period, 60.0);

    let hangul = "\u{1100}\u{1161}\u{11A8}".repeat(700);
    assert_eq!(hangul.chars().count(), 2100);
    let s = type_scene(&hangul, "0.05");
    assert_eq!(s.actors[0].width, 700.0);
    assert_eq!(s.actions[0].duration, 35.0);
}

#[test]
fn limit_counts_clusters() {
    let ok = "e\u{0301}".repeat(1024);
    assert!(mdgl::check(&format!("{S}actor a = text(\"{ok}\") at (0,0)\n")).is_empty());
    let bad = "e\u{0301}".repeat(1025);
    assert_eq!(mdgl::check(&format!("{S}actor a = text(\"{bad}\") at (0,0)\n"))[0].to_string(), "2:1: text exceeds 1024 graphemes");
}

//! Targeted parser/checker discriminators.
const S: &str = "scene width=8 height=2 fallback=end\n";
fn first(src: &str) -> String {
    mdgl::check(src).first().map(|d| d.to_string()).unwrap_or_default()
}

#[test]
fn byte_columns_and_escapes() {
    assert_eq!(first(&format!("{S}actor a = text(\"é\") $\n")), "2:22: unexpected character \"$\"");
    assert_eq!(first(&format!("{S}actor a = text(\"\\u00e9\\x41\\101\\t\") at (0,0)\n")), "2:1: text contains a control character");
    assert_eq!(first(&format!("{S}actor a = text(\"\\q\") at (0,0)\n")), "2:16: invalid string escape");
    assert_eq!(first(&format!("{S}actor a = text(\"x) at (0,0)\n")), "2:16: unterminated string");
}

#[test]
fn decimals_are_finite_non_exponent() {
    for t in ["1e3", "inf", "nan", "0x10", "1.2.3"] {
        assert_ne!(first(&format!("{S}actor a = text(\"A\") at (0,0)\n@0: a.fade(in, dur={t})\n")), "", "{t}");
    }
    assert_eq!(first(&format!("{S}actor a = text(\"A\") at (0,0)\n@.5s: a.fade(in, dur=+.5)\n")), "");
}

#[test]
fn references_and_order() {
    assert_eq!(first(&format!("{S}actor a = text(\"A\") at (0,0) parent=b\nactor b = text(\"B\") at (0,0)\n")), "");
    assert_eq!(first(&format!("{S}actor a = text(\"A\") at (0,0) parent=c\n")), "2:1: unknown parent \"c\"; did you mean \"a\"?");
    assert_eq!(first("actor a = text(\"A\") at (0,0)\n"), "1:1: scene must precede actors");
    assert_eq!(first(&format!("{S}@0: a.fade(in, dur=1)\nactor a = text(\"A\") at (0,0)\n")), "3:1: actors must precede actions");
}

#[test]
fn timing_constraints() {
    let t = |a: &str| format!("{S}actor a = text(\"AB\") at (0,0)\n{a}");
    assert_eq!(first(&t("@0: a.move(to=(1,0), dur=1)\n@1: a.move(to=(2,0), dur=1)\n")), "");
    assert_eq!(first(&t("@0: a.move(to=(1,0), dur=1)\n@0.5: a.move(to=(2,0), dur=1)\n")), "4:1: overlapping position actions on a");
    assert_eq!(first(&t("@0: a.move(to=(1,0), dur=1)\n@0: a.fade(in, dur=1)\n")), "");
    assert_eq!(first(&t("@0: a.fade(in, dur=0.0000000004)\n")), "3:1: dur rounds to zero at nanosecond precision");
    assert_eq!(first(&t("@59: a.fade(in, dur=2)\n")), "3:1: action end must be <=60");
    assert_eq!(first(&format!("scene width=8 height=1 fallback=@3 period=2\n")), "1:1: fallback time must be within period");
    assert_eq!(first(&t("@0: a.fade(in, dur=1, dur=2)\n")), "3:1: duplicate argument dur");
    assert_eq!(first(&t("@0: a.rotate(x=1, dur=1)\n")), "3:1: rotate requires a cube actor");
    assert_eq!(first(&format!("{S}actor c = cube(size=4) at (0,0)\n@0: c.rotate(x=1.5707963267948966rad, y=-90deg, dur=1)\n")), "");
}

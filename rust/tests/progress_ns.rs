//! Progress is computed from integer nanoseconds: quantize time, begin and duration first, subtract in
//! integers, then divide once. Float seconds must not push the exact midpoint below 0.5.

fn scene(body: &str) -> mdgl::Scene {
    mdgl::parse_checked(&format!("scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green\n{body}")).unwrap()
}
fn fg(s: &mdgl::Scene, ns: u64) -> String {
    s.frame_ns(ns, 4, 1).cells[0][0].fg.clone()
}

#[test]
fn linear_fade_midpoint_is_exactly_half() {
    // begin 2.4 + 0.8 s: at 2.8 s elapsed/duration = 0.4/0.8; float seconds give 0.49999999999999956.
    let s = scene("@2.4: a.fade(in, dur=0.8)\n");
    assert_eq!(fg(&s, 2_800_000_000), "#008000"); // 255 * 0.5 = 127.5 -> 128
    assert_eq!(fg(&s, 2_799_999_999), "#007f00");
    assert_eq!(fg(&s, 2_800_000_001), "#008000");
}

#[test]
fn color_switches_at_the_exact_half_instant() {
    let s = scene("@8: a.color(to=red, dur=0.4)\n");
    assert_eq!(fg(&s, 8_199_999_999), "green");
    assert_eq!(fg(&s, 8_200_000_000), "red"); // float seconds: progress 0.49999999999999956 -> still green
    assert_eq!(fg(&s, 8_200_000_001), "red");
    // shifted control: the same shape at begin 4 already switched correctly before the fix
    let c = scene("@4: a.color(to=red, dur=0.4)\n");
    assert_eq!((fg(&c, 4_199_999_999).as_str(), fg(&c, 4_200_000_000).as_str()), ("green", "red"));
}

#[test]
fn boundaries_clamp_and_freeze_are_unchanged() {
    let s = scene("@1: a.fade(in, dur=1)\n");
    assert_eq!(fg(&s, 999_999_999), "normal".replace("normal", &fg(&s, 0))); // before begin: invisible start, unchanged
    assert_eq!(fg(&s, 2_000_000_000), "green"); // at the end the final value is frozen at full opacity
    assert_eq!(fg(&s, 9_000_000_000), "green");
    assert_eq!(fg(&s, 1_500_000_000), "#008000");
}

#[test]
fn ease_in_out_color_switches_at_the_midpoint_too() {
    // CSS ease-in-out is symmetric: eased(0.5) is exactly 0.5 in Rust and in the TS reference.
    let s = scene("@8: a.color(to=red, dur=0.4, ease=ease-in-out)\n");
    assert_eq!((fg(&s, 8_199_999_999).as_str(), fg(&s, 8_200_000_000).as_str()), ("green", "red"));
}

/// Shared neon-cube showcase scene: the exact half instants of its fade and colour actions.
#[test]
fn neon_cube_half_instants() {
    let src = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../examples/neon-cube.mdgl")).unwrap();
    let s = mdgl::parse_checked(&src).unwrap();
    let count = |ns: u64, color: &str| s.frame_ns(ns, 90, 28).cells.iter().flatten().filter(|c| c.fg == color).count();
    // 2.8 s: `bl` (green) is half faded in: 255 * 0.5 = 127.5 -> #008000, never #007f00.
    assert!(count(2_800_000_000, "#008000") > 0 && count(2_800_000_000, "#007f00") == 0);
    // Each colour action flips at its half instant: more cells take the target colour than 1 ns before.
    for (ns, color) in [(8_200_000_000u64, "yellow"), (9_200_000_000, "red"), (10_200_000_000, "green"), (11_200_000_000, "blue")] {
        assert!(count(ns, color) > count(ns - 1, color), "{color} at {ns} ns");
    }
}

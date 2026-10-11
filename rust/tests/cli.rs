//! Real `mdgl` binary: exit codes, plain/redirected output and reduced motion. A live terminal
//! (SIGINT, finite run) is exercised by scripts/pty_proof.py, which needs a pty.
use std::process::{Command, Output};

const SCENE: &str = "scene width=6 height=2 period=1 fps=10 fallback=end\nactor a = text(\"Hi\") at (0,0)\n@0: a.move(to=(3,1), dur=1)\n";

fn tmp(name: &str, body: &str) -> String {
    let p = std::env::temp_dir().join(format!("mdgl-cli-{}-{name}", std::process::id()));
    std::fs::write(&p, body).unwrap();
    p.to_string_lossy().into()
}

fn mdgl(args: &[&str], env: &[(&str, &str)]) -> Output {
    let mut c = Command::new(env!("CARGO_BIN_EXE_mdgl"));
    c.args(args).env_remove("NO_COLOR").env_remove("MDGL_REDUCED_MOTION");
    for (k, v) in env {
        c.env(k, v);
    }
    c.output().unwrap()
}

#[test]
fn exit_codes() {
    let ok = tmp("ok.mdgl", SCENE);
    let bad = tmp("bad.mdgl", "scene width=4 height=1\n");
    let o = mdgl(&["check", &ok], &[]);
    assert_eq!((o.status.code(), String::from_utf8_lossy(&o.stdout).trim()), (Some(0), "OK MDGL 0.1"));
    let o = mdgl(&["check", &bad], &[]);
    assert_eq!(o.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&o.stderr).contains(":1:1: missing scene attribute fallback"));
    assert_eq!(mdgl(&["check", "/nonexistent/x.mdgl"], &[]).status.code(), Some(2));
    assert_eq!(mdgl(&["bogus", &ok], &[]).status.code(), Some(2));
    assert_eq!(mdgl(&["play"], &[]).status.code(), Some(2));
    assert_eq!(mdgl(&["play", &ok, "--extra"], &[]).status.code(), Some(2));
    assert_eq!(mdgl(&["frames", &ok, "--at", "x"], &[]).status.code(), Some(2));
    let h = mdgl(&["--help"], &[]);
    assert!(h.status.success() && String::from_utf8_lossy(&h.stdout).contains("mdgl play FILE"));
}

#[test]
fn play_off_a_terminal_prints_the_fallback_once_without_escapes() {
    let ok = tmp("play.mdgl", SCENE);
    let want = "      \n   Hi \n"; // fallback=end: text moved to (3,1)
    let o = mdgl(&["play", &ok], &[]);
    assert_eq!(o.status.code(), Some(0));
    assert_eq!(String::from_utf8_lossy(&o.stdout), want);
    assert!(!o.stdout.contains(&0x1b));
    // reduced motion / NO_COLOR give the same plain output (only matters on a tty, still must hold)
    for var in ["NO_COLOR", "MDGL_REDUCED_MOTION"] {
        let o = mdgl(&["play", &ok], &[(var, "1")]);
        assert_eq!(String::from_utf8_lossy(&o.stdout), want, "{var}");
    }
}

#[test]
fn frames_prints_labelled_plain_frames() {
    let ok = tmp("frames.mdgl", SCENE);
    let o = mdgl(&["frames", &ok, "--at", "0,1"], &[]);
    assert_eq!(String::from_utf8_lossy(&o.stdout), "@0\nHi    \n      \n@1\n      \n   Hi \n");
}

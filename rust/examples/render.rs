//! Render one MDGL frame as text.
//!
//! cargo run --example render -- [PATH] [--at SECONDS | --fallback]
//!
//! PATH defaults to the shared `../examples/text.mdgl` (run from the `rust/` directory).
//! Exit codes: 0 ok, 1 invalid scene (first diagnostic on stderr), 2 usage or unreadable file.
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut path = String::from("../examples/text.mdgl");
    let (mut at, mut fallback) = (5.0f64, false);
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--fallback" => fallback = true,
            "--at" => match args.next().and_then(|v| v.parse::<f64>().ok()).filter(|v| v.is_finite() && *v >= 0.0) {
                Some(v) => at = v,
                None => return usage("--at needs a non-negative number of seconds"),
            },
            s if s.starts_with("--") => return usage(&format!("unknown option {s}")),
            _ => path = a,
        }
    }
    let source = match std::fs::read_to_string(&path) {
        Ok(s) => s,
        Err(e) => return usage(&format!("cannot read {path}: {e}")),
    };
    // parse_checked = parse + semantic check; the scene is safe to evaluate afterwards.
    let scene = match mdgl::parse_checked(&source) {
        Ok(s) => s,
        Err(d) => {
            eprintln!("{path}:{d}");
            return ExitCode::from(1);
        }
    };
    let (w, h) = (scene.width as usize, scene.height as usize);
    let frame = if fallback { scene.fallback_frame(w, h) } else { scene.frame(at, w, h) };
    for row in frame.lines() {
        println!("{}", row.trim_end());
    }
    if !fallback {
        eprintln!("t={at}s done={}", frame.done);
    }
    ExitCode::SUCCESS
}

fn usage(msg: &str) -> ExitCode {
    eprintln!("render: {msg}\nusage: cargo run --example render -- [PATH] [--at SECONDS | --fallback]");
    ExitCode::from(2)
}

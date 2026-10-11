//! `mdgl` command line: check, frames and play (SPEC "Limits and API").
//! Exit codes: 0 ok, 1 invalid scene or output error, 2 usage or unreadable file, 130 interrupted.
use std::io::{self, IsTerminal, Read, Write};
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};

static INTERRUPTED: AtomicBool = AtomicBool::new(false);

const HELP: &str = "mdgl - MarkdownGL 0.1 checker and terminal player

usage:
  mdgl check FILE               validate a scene, print 'OK MDGL 0.1'
  mdgl frames FILE --at T1,T2   print plain frames at the given seconds (default 0)
  mdgl play FILE                animate in the terminal (Ctrl+C stops)
  mdgl --help | --version

play draws only changed cells with synchronized output. When stdout is not a terminal, or
NO_COLOR or MDGL_REDUCED_MOTION is set and non-empty, it prints the scene's fallback frame once,
with no timers and no escape sequences.

exit codes: 0 ok, 1 invalid scene or output error, 2 usage or unreadable file, 130 interrupted";

#[cfg(unix)]
fn install_sigint() {
    extern "C" fn on_sigint(_: i32) {
        INTERRUPTED.store(true, Ordering::SeqCst); // async-signal-safe: one atomic store
    }
    extern "C" {
        fn signal(signum: i32, handler: extern "C" fn(i32)) -> usize;
    }
    // SAFETY: `signal` is the C library function; the handler only performs an atomic store.
    unsafe {
        signal(2, on_sigint);
    }
}

#[cfg(not(unix))]
fn install_sigint() {} // Windows: the default Ctrl+C behaviour applies (cursor is not restored).

fn usage(msg: &str) -> ExitCode {
    eprintln!("mdgl: {msg}\nusage: mdgl check FILE | frames FILE --at T1,T2 | play FILE  (see mdgl --help)");
    ExitCode::from(2)
}

fn read_scene(path: &str) -> Result<mdgl::Scene, ExitCode> {
    let mut source = String::new();
    // Read one byte past the 256 KiB limit so oversize input is diagnosed, not truncated silently.
    let read = std::fs::File::open(path).and_then(|f| f.take(mdgl::MAX_INPUT as u64 + 1).read_to_string(&mut source));
    if let Err(e) = read {
        eprintln!("mdgl: cannot read {path}: {e}");
        return Err(ExitCode::from(2));
    }
    mdgl::parse_checked(&source).map_err(|d| {
        eprintln!("{path}:{d}");
        ExitCode::from(1)
    })
}

fn quiet(var: &str) -> bool {
    std::env::var_os(var).is_some_and(|v| !v.is_empty())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("--help" | "-h" | "help") => {
            println!("{HELP}");
            return ExitCode::SUCCESS;
        }
        Some("--version" | "-V") => {
            println!("mdgl {}", env!("CARGO_PKG_VERSION"));
            return ExitCode::SUCCESS;
        }
        _ => {}
    }
    let (Some(cmd), Some(file)) = (args.first(), args.get(1)) else { return usage("missing command or FILE") };
    if !["check", "frames", "play"].contains(&cmd.as_str()) {
        return usage(&format!("unknown command {cmd:?}"));
    }
    let mut times = String::from("0");
    let mut rest = args[2..].iter();
    while let Some(a) = rest.next() {
        match (a.as_str(), cmd.as_str()) {
            ("--at", "frames") => match rest.next() {
                Some(v) => times = v.clone(),
                None => return usage("--at needs a value"),
            },
            _ => return usage(&format!("unexpected argument {a:?}")),
        }
    }
    let scene = match read_scene(file) {
        Ok(s) => s,
        Err(code) => return code,
    };
    let (w, h) = (scene.width as usize, scene.height as usize);
    let mut out = io::stdout().lock();
    let result = match cmd.as_str() {
        "check" => writeln!(out, "OK MDGL 0.1"),
        "frames" => {
            let mut samples = Vec::new();
            for t in times.split(',') {
                match t.trim().trim_end_matches('s').parse::<f64>() {
                    Ok(v) if v.is_finite() && (0.0..=1e12).contains(&v) => samples.push(v),
                    _ => return usage(&format!("invalid frame time {t:?}")),
                }
            }
            samples.iter().try_for_each(|&t| write!(out, "@{t}\n{}", mdgl::plain(&scene.frame(t, w, h))))
        }
        _ => {
            if !out.is_terminal() || quiet("NO_COLOR") || quiet("MDGL_REDUCED_MOTION") {
                write!(out, "{}", mdgl::plain(&scene.fallback_frame(w, h)))
            } else {
                install_sigint();
                let mut clock = mdgl::SystemClock::start();
                match mdgl::play(&scene, &mut out, &mut clock, &|| INTERRUPTED.load(Ordering::SeqCst)) {
                    Ok(mdgl::Outcome::Interrupted) => return ExitCode::from(130),
                    Ok(mdgl::Outcome::Finished) => Ok(()),
                    Err(e) => Err(e),
                }
            }
        }
    };
    match result.and_then(|_| out.flush()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("mdgl: write error: {e}");
            ExitCode::from(1)
        }
    }
}

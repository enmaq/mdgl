//! Wire-level adapter behaviour (frozen protocol v1): exact integer time_ns, framing, EOF, size bound.
use std::io::Write;
use std::process::{Command, Stdio};

fn run(input: &[u8]) -> Vec<String> {
    let mut c = Command::new(env!("CARGO_BIN_EXE_mdgl-adapter")).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
    c.stdin.take().unwrap().write_all(input).unwrap();
    String::from_utf8(c.wait_with_output().unwrap().stdout).unwrap().lines().map(String::from).collect()
}

fn frame(t: &str) -> String {
    format!("{{\"v\":1,\"id\":\"x\",\"op\":\"frame\",\"source\":\"scene width=2 height=1 fallback=end\\n\",\"time_ns\":{t},\"width\":2,\"height\":1}}\n")
}

#[test]
fn time_ns_is_an_exact_mathematical_integer() {
    for ok in ["1.0", "1e9", "0", "9007199254740991", "1E3", "9007199254740991.0"] {
        assert!(run(frame(ok).as_bytes())[0].contains("\"ok\":true"), "{ok}");
    }
    for bad in ["9007199254740991.1", "9007199254740992", "-1", "1.5", "1e-1", "\"1\"", "null", "NaN", "01", "1e999"] {
        let r = &run(frame(bad).as_bytes())[0];
        assert!(r.contains("bad_request") || r.contains("\"id\":null"), "{bad}: {r}");
    }
}

#[test]
fn framing_and_branches() {
    // Final non-empty line without newline gets exactly one response; blank lines are bad_request.
    let r = run(b"{\"v\":1,\"id\":\"c\",\"op\":\"check\",\"source\":\"\"}");
    assert_eq!(r.len(), 1);
    assert!(r[0].contains("missing scene"));
    assert!(run(b"\n")[0].contains("bad_request"));
    // normal frame has done; fallback frame must not.
    assert!(run(frame("0").as_bytes())[0].contains("\"done\":true"));
    let fb = "{\"v\":1,\"id\":\"f\",\"op\":\"frame\",\"source\":\"scene width=2 height=1 fallback=end\\n\",\"fallback\":true,\"width\":9,\"height\":9}\n";
    let r = &run(fb.as_bytes())[0];
    assert!(!r.contains("done") && r.contains("\"width\":2"), "{r}");
    // invalid source on frame is MDGL-level, with diagnostics.
    assert!(run(b"{\"v\":1,\"id\":\"i\",\"op\":\"frame\",\"source\":\"\",\"time_ns\":0,\"width\":2,\"height\":1}\n")[0].contains("invalid_source"));
    assert!(run(b"{\"v\":2,\"id\":\"v\",\"op\":\"check\",\"source\":\"\"}\n")[0].contains("unsupported_version"));
    // lone surrogate escape is bad_request
    assert!(run(b"{\"v\":1,\"id\":\"s\",\"op\":\"check\",\"source\":\"\\ud800\"}\n")[0].contains("bad_request"));
}

#[test]
fn oversize_line_is_discarded_then_serving_continues() {
    let mut input = b"{\"v\":1,\"id\":\"l\",\"op\":\"check\",\"source\":\"".to_vec();
    input.extend(std::iter::repeat(b'a').take(2_097_200));
    input.extend_from_slice(b"\"}\n{\"v\":1,\"id\":\"n\",\"op\":\"check\",\"source\":\"\"}\n");
    let r = run(&input);
    assert_eq!(r.len(), 2);
    assert!(r[0].contains("bad_request") && r[1].contains("\"id\":\"n\""));
}

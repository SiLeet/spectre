//! Event stream (rust-port-plan §4.1), the same schema as the Python goldens:
//! `{"ev": "shot", "name", "frame"}`, `{"ev": "tap", "x", "y", "mode", "wait"}`, `seq`, `key`,
//! `hold`, `swipe`, `sleep`, `now`, `adb {argv, rc}`. `AFK_TRACE=<file>` appends every
//! event live as one JSON line (Hermes' live smoke compares it with the Python recorder).

use serde_json::{Value, json};
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::Path;

#[derive(Debug, Default)]
pub struct Trace {
    pub events: Vec<Value>,
    live: Option<File>,
}

impl Trace {
    /// In-memory only.
    pub fn new() -> Self {
        Self::default()
    }

    /// In-memory plus `AFK_TRACE` (appended) when that variable is set.
    pub fn from_env() -> std::io::Result<Self> {
        match std::env::var_os("AFK_TRACE") {
            Some(p) if !p.is_empty() => Self::to_file(Path::new(&p)),
            _ => Ok(Self::new()),
        }
    }

    pub fn to_file(path: &Path) -> std::io::Result<Self> {
        let f = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self { events: Vec::new(), live: Some(f) })
    }

    pub fn push(&mut self, ev: Value) {
        if let Some(f) = self.live.as_mut() {
            // best-effort like the Python recorder: a full disk must not stop a tap
            let _ = writeln!(f, "{ev}").and_then(|_| f.flush());
        }
        self.events.push(ev);
    }
}

pub fn ev_shot(name: &str, frame: &str) -> Value {
    json!({"ev": "shot", "name": name, "frame": frame})
}

pub fn ev_tap(x: i64, y: i64, mode: &str, wait: f64) -> Value {
    json!({"ev": "tap", "x": x, "y": y, "mode": mode, "wait": wait})
}

pub fn ev_seq(steps: &[(i64, i64, f64)]) -> Value {
    json!({"ev": "seq", "steps": steps.iter().map(|&(x, y, w)| json!([x, y, w])).collect::<Vec<_>>()})
}

pub fn ev_key(code: i64, w: f64) -> Value {
    json!({"ev": "key", "code": code, "w": w})
}

pub fn ev_hold(x: i64, y: i64, ms: i64, wait: f64) -> Value {
    json!({"ev": "hold", "x": x, "y": y, "ms": ms, "wait": wait})
}

pub fn ev_swipe(args: [i64; 4], millis: i64, wait: f64) -> Value {
    json!({"ev": "swipe", "args": args, "kwargs": {"millis": millis, "wait": wait}})
}

pub fn ev_sleep(s: f64) -> Value {
    json!({"ev": "sleep", "s": s})
}

pub fn ev_now(src: &str, val: f64) -> Value {
    json!({"ev": "now", "src": src, "val": val})
}

/// One adb process, in the recorder's shape: `adb {fn, argv: args, kwargs: {timeout}}` for
/// `adb()`, `run {argv: [ADB, -s, SERIAL, ...], kwargs: {timeout}}` for shot()'s direct
/// `subprocess.run`; `rc` on completion, `raise` (TimeoutExpired/OSError) otherwise.
/// shortcut: stdout/stderr are not traced (screencaps are MBs); the live diff compares argv/rc.
pub fn ev_io(kind: &str, argv: &[String], timeout_s: u64, res: &Result<Option<i32>, &spectre_mcp::RunError>) -> Value {
    let mut ev = if kind == "run" {
        json!({"ev": "run", "argv": argv, "kwargs": {"timeout": timeout_s}})
    } else {
        json!({"ev": "adb", "fn": "adb", "argv": argv, "kwargs": {"timeout": timeout_s}})
    };
    match res {
        Ok(rc) => ev["rc"] = json!(rc),
        Err(spectre_mcp::RunError::Timeout) => ev["raise"] = json!("TimeoutExpired"),
        Err(spectre_mcp::RunError::Spawn(_)) => ev["raise"] = json!("OSError"),
    }
    ev
}

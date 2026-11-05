//! `spectre-afk` CLI. E1 ships only the live-smoke commands for Hermes (rust-port-plan §E1):
//!
//!   spectre-afk tap <x> <y> [--mode tap|touchscreen|sendevent]
//!   spectre-afk key <code>
//!   spectre-afk shot <name>
//!   spectre-afk decode-raw <file>      (offline: raw `exec-out screencap` bytes -> w, h, key, crc32)
//!
//! They run only with `SPECTRE_AFK_LIVE=1` AND the `afk-bot.lock` of the real checkout taken
//! (released on exit, panic and Ctrl-C; PID-guarded); otherwise rc 2. `SPECTRE_REPO` must be
//! the bot checkout (`.spectre/` + `scripts/_bot_lock.py`). `AFK_TRACE=<file>` appends the
//! §4.1 event stream; `AFK_TAP_MODE` sets the start mode. Not a general adb client.

use spectre_afk::env::{self, repo_root, shots_dir, validate_repo};
use spectre_afk::infra::clock::SystemClock;
use spectre_afk::infra::device::{AdbDevice, Device};
use spectre_afk::infra::tap::{Discovery, TapMode};
use spectre_afk::infra::trace::Trace;
use spectre_afk::state::lock;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const USAGE: &str =
    "usage: spectre-afk tap <x> <y> [--mode tap|touchscreen|sendevent] | key <code> | shot <name> | decode-raw <file>";

#[derive(Debug)]
enum Cmd {
    Tap(i64, i64, Option<TapMode>),
    Key(i64),
    Shot(String),
    DecodeRaw(PathBuf),
}

fn parse(args: &[String]) -> Result<Cmd, String> {
    let n = |s: Option<&String>| s.and_then(|v| v.parse::<i64>().ok()).ok_or_else(|| USAGE.to_owned());
    match args.first().map(String::as_str) {
        Some("tap") => {
            let mode = match args.get(3).map(String::as_str) {
                None => None,
                Some("--mode") => Some(args.get(4).and_then(|m| TapMode::parse(m)).ok_or_else(|| USAGE.to_owned())?),
                Some(_) => return Err(USAGE.into()),
            };
            Ok(Cmd::Tap(n(args.get(1))?, n(args.get(2))?, mode))
        }
        Some("key") => Ok(Cmd::Key(n(args.get(1))?)),
        Some("decode-raw") => args.get(1).map(|f| Cmd::DecodeRaw(PathBuf::from(f))).ok_or_else(|| USAGE.into()),
        Some("shot") => match args.get(1) {
            // the name becomes shots-<pid>/<name>.png: no path components
            Some(s) if !s.is_empty() && !s.contains(['/', '\\', ':']) && !s.contains("..") => Ok(Cmd::Shot(s.clone())),
            _ => Err(format!("{USAGE}\n  (shot name: no '/', '\\', ':' or '..')")),
        },
        _ => Err(USAGE.into()),
    }
}

/// Releases our lock when dropped (normal return and panic unwinding), PID-guarded.
struct LockGuard {
    path: PathBuf,
    pid: u32,
}

impl Drop for LockGuard {
    fn drop(&mut self) {
        if let Err(e) = lock::release(&self.path, &lock::os_env, self.pid) {
            eprintln!("lock release: {e}");
        }
    }
}

/// Ctrl-C / Ctrl-Break / console close: release the lock, then let Windows end the process
/// (Python gets the same through atexit on KeyboardInterrupt). std FFI only, no crate.
#[cfg(windows)]
mod ctrl {
    use std::path::PathBuf;
    use std::sync::OnceLock;

    static HELD: OnceLock<(PathBuf, u32)> = OnceLock::new();
    type Handler = unsafe extern "system" fn(u32) -> i32;

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn SetConsoleCtrlHandler(handler: Option<Handler>, add: i32) -> i32;
    }

    unsafe extern "system" fn on_ctrl(_kind: u32) -> i32 {
        if let Some((path, pid)) = HELD.get() {
            let _ = spectre_afk::state::lock::release(path, &|_| None, *pid);
        }
        0 // FALSE: continue with the default handler (terminate)
    }

    pub fn install(path: PathBuf, pid: u32) {
        let _ = HELD.set((path, pid));
        // SAFETY: registers a plain extern "system" fn that only reads a OnceLock
        unsafe {
            SetConsoleCtrlHandler(Some(on_ctrl), 1);
        }
    }
}

#[cfg(not(windows))]
mod ctrl {
    pub fn install(_path: std::path::PathBuf, _pid: u32) {}
}

fn refuse(msg: &str) -> ExitCode {
    eprintln!("refused: {msg}");
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let cmd = match parse(&args) {
        Ok(c) => c,
        Err(u) => {
            eprintln!("{u}");
            return ExitCode::from(2);
        }
    };
    if let Cmd::DecodeRaw(path) = &cmd {
        return decode_raw(path); // offline: no device, no lock
    }
    if std::env::var("SPECTRE_AFK_LIVE").as_deref() != Ok("1") {
        return refuse("live commands need SPECTRE_AFK_LIVE=1 (the device belongs to the live lane)");
    }
    let repo = match repo_root().and_then(|r| validate_repo(&r)) {
        Ok(r) => r,
        Err(e) => return refuse(&e.to_string()),
    };
    let lock_path = lock::default_lock(&repo);
    let pid = std::process::id();
    let inherited = lock::os_env(lock::HELD_ENV).as_deref() == Some("1");
    if inherited && !lock_path.is_file() {
        // the wrapper that exported AFK_BOT_LOCK_HELD=1 must still hold its lock file
        return refuse(&format!("AFK_BOT_LOCK_HELD=1 but no lock file at {}", lock_path.display()));
    }
    match lock::acquire(&lock_path, &lock::os_env, None, None, pid) {
        Ok(true) => {}
        Ok(false) => {
            let who = lock::describe(&lock_path, None).unwrap_or_else(|e| e.to_string());
            return refuse(&format!("{} held ({who})", lock_path.display()));
        }
        Err(e) => return refuse(&format!("lock {}: {e}", lock_path.display())),
    }
    eprintln!("lock {} ({})", lock_path.display(), if inherited { "inherited" } else { "taken" });
    let _guard = (!inherited).then(|| {
        ctrl::install(lock_path.clone(), pid);
        LockGuard { path: lock_path.clone(), pid }
    });
    run(cmd, &repo, pid)
}

/// Live-smoke step (plan §E1 exit 4): the captured raw bytes through `raw_to_frame`; compare
/// with Python's `_raw_to_image` on the same file (see docs/reports/rust-port-E1.md).
fn decode_raw(path: &Path) -> ExitCode {
    let data = match std::fs::read(path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("{}: {e}", path.display());
            return ExitCode::from(2);
        }
    };
    match spectre_afk::infra::screencap::raw_to_frame(&data) {
        Some(f) => {
            let hdr = data.len() - f.rgb.len() / 3 * 4;
            println!("raw {} bytes, header {hdr}: {}x{} key {} crc32 {}", data.len(), f.w, f.h, f.key(), f.crc32());
            ExitCode::SUCCESS
        }
        None => {
            println!("raw {} bytes: not a raw RGBA_8888 screencap (None)", data.len());
            ExitCode::from(1)
        }
    }
}

fn run(cmd: Cmd, repo: &Path, pid: u32) -> ExitCode {
    let trace = match Trace::from_env() {
        Ok(t) => t,
        Err(e) => {
            eprintln!("AFK_TRACE: {e}");
            return ExitCode::from(2);
        }
    };
    let mut dev = AdbDevice::new(spectre_mcp::SystemRunner, Box::new(SystemClock), trace, shots_dir(repo, pid));
    dev.echo = true;
    let (mode, warn) = env::tap_mode_env(std::env::var("AFK_TAP_MODE").ok().as_deref());
    if let Some(w) = warn {
        dev.print(&w);
    }
    dev.state.mode = mode;
    let res = match cmd {
        Cmd::Tap(x, y, m) => dev.tap((x, y), 0.0, m).map(|used| {
            // sendevent without a discovered device falls back to `input tap` (like Python):
            // say so, the live smoke must not count it as a sendevent tap
            let real = if used == TapMode::Sendevent && !matches!(dev.state.sendevent, Discovery::Found(_)) {
                "tap (sendevent unavailable)".to_owned()
            } else {
                used.to_string()
            };
            println!("tap ({x}, {y}) via {real}");
        }),
        Cmd::Key(code) => dev.key_seq(&[(code, 0.0)], false, false).map(|_| println!("keyevent {code}")),
        Cmd::Shot(name) => dev.shot(&name).map(|f| {
            println!("{} {}x{} key {}", dev.shots.join(format!("{name}.png")).display(), f.w, f.h, f.key())
        }),
        Cmd::DecodeRaw(_) => unreachable!("handled before the live gate"),
    };
    match res {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{}: {e}", e.py_type());
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn a(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn parses_the_three_commands() {
        assert!(matches!(parse(&a(&["tap", "1", "2"])), Ok(Cmd::Tap(1, 2, None))));
        assert!(matches!(parse(&a(&["tap", "1", "2", "--mode", "sendevent"])), Ok(Cmd::Tap(1, 2, Some(TapMode::Sendevent)))));
        assert!(matches!(parse(&a(&["key", "4"])), Ok(Cmd::Key(4))));
        assert!(matches!(parse(&a(&["shot", "x_1"])), Ok(Cmd::Shot(_))));
        assert!(matches!(parse(&a(&["decode-raw", "C:/x/raw.bin"])), Ok(Cmd::DecodeRaw(_))));
        for bad in [&["tap", "1"][..], &["tap", "1", "2", "--mode", "bogus"], &["devices"], &["shot", "../x"], &["shot", "C:x"], &["shot", "a/b"]] {
            assert!(parse(&a(bad)).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn guard_releases_own_lock_on_drop() {
        let dir = std::env::temp_dir().join(format!("spectre-afk-guard-{}", std::process::id()));
        let path = dir.join("afk-bot.lock");
        let pid = std::process::id();
        assert!(lock::acquire(&path, &|_| None, None, None, pid).unwrap());
        drop(LockGuard { path: path.clone(), pid });
        assert!(!path.exists());
        let _ = std::fs::remove_dir_all(&dir);
    }
}

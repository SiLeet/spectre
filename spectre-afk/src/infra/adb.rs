//! `adb()` (afk_claim_vision L486): `subprocess.run([ADB, '-s', SERIAL, *args],
//! capture_output=True, timeout=timeout)`. Process handling (pipes, kill on timeout) is
//! spectre-mcp's `CommandRunner`, used as a library - not moved, MCP untouched.

use crate::env;
use spectre_mcp::{CommandRunner, Output, RunError};
use std::time::Duration;

/// `adb(..., timeout=30)` default.
pub const ADB_TIMEOUT: u64 = 30;
/// `shot()`: both screencap calls use 60 s.
pub const SCREENCAP_TIMEOUT: u64 = 60;
/// `sendevent_device()`: `getevent -pl` and `su -c id` use 10 s.
pub const DISCOVERY_TIMEOUT: u64 = 10;

pub struct Adb<R> {
    pub runner: R,
    pub bin: String,
    pub serial: String,
}

impl<R: CommandRunner> Adb<R> {
    /// `adb -s 127.0.0.1:5555` at the SDK path - never `adb connect` / `adb devices`.
    pub fn new(runner: R) -> Self {
        Self { runner, bin: env::adb_bin(), serial: env::SERIAL.to_owned() }
    }

    /// The argv after the program: `-s SERIAL *args`.
    pub fn argv(&self, args: &[String]) -> Vec<String> {
        let mut v = vec!["-s".to_owned(), self.serial.clone()];
        v.extend_from_slice(args);
        v
    }

    pub fn run(&mut self, args: &[String], timeout_s: u64) -> Result<Output, RunError> {
        let argv = self.argv(args);
        self.runner.run(&self.bin, &argv, Duration::from_secs(timeout_s))
    }
}

/// `p.stderr[:120]`.
pub fn head120(b: &[u8]) -> &[u8] {
    &b[..b.len().min(120)]
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Rec(Vec<(String, Vec<String>, Duration)>, Result<Output, RunError>);

    impl CommandRunner for Rec {
        fn run(&mut self, p: &str, a: &[String], t: Duration) -> Result<Output, RunError> {
            self.0.push((p.into(), a.to_vec(), t));
            self.1.clone()
        }
    }

    #[test]
    fn argv_always_names_the_serial() {
        let mut adb = Adb::new(Rec(vec![], Ok(Output { code: Some(0), ..Default::default() })));
        adb.run(&["shell".into(), "input tap 1 2".into()], 30).unwrap();
        let (p, a, t) = &adb.runner.0[0];
        assert!(p.ends_with("adb.exe"));
        assert_eq!(a, &["-s", "127.0.0.1:5555", "shell", "input tap 1 2"]);
        assert_eq!(*t, Duration::from_secs(30));
    }

    #[test]
    fn timeout_and_spawn_errors_pass_through() {
        let mut adb = Adb::new(Rec(vec![], Err(RunError::Timeout)));
        assert_eq!(adb.run(&[], 1).unwrap_err(), RunError::Timeout);
        assert_eq!(head120(&[7u8; 300]).len(), 120);
    }

    #[test]
    #[cfg(windows)]
    fn system_runner_kills_a_hung_process() {
        // Exec timeout/kill (plan §E1 tests): a process that would run 30 s is cut at 1 s
        let mut r = spectre_mcp::SystemRunner;
        let t0 = std::time::Instant::now();
        let res = r.run("powershell", &["-NoProfile".into(), "-Command".into(), "Start-Sleep 30".into()],
                        Duration::from_secs(1));
        assert_eq!(res.unwrap_err(), RunError::Timeout);
        assert!(t0.elapsed() < Duration::from_secs(15));
    }
}

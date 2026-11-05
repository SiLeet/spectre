//! `trait Device` (rust-port-plan §E1): the module globals of `afk_claim_vision` as one
//! object. Low-level hooks (`adb`, `exec`, `sleep`, `print`, tap state) are what an
//! implementation must provide; the high-level methods default to the 1:1 Python ports in
//! `seq`/`tap`/`screencap` and may be overridden - the seams the Python tests patch
//! (`v.tap`, `v.key_seq`, `v.sendevent_device`, ...). Internal calls go through `self`, so an
//! override is seen by every caller, like a patched module global.

use super::adb::Adb;
use super::clock::Clock;
use super::seq::SeqOut;
use super::tap::{TapMode, TapState, TouchDev};
use super::trace::{Trace, ev_io, ev_now, ev_sleep};
use super::{Result, screencap, seq, tap};
use crate::img::Frame;
use serde_json::Value;
use spectre_mcp::{CommandRunner, Output, RunError};
use std::path::PathBuf;

pub trait Device {
    // ---- low level ------------------------------------------------------------------
    /// `TAP_MODE`, `_TAP_DEAD`, `_SENDEVENT`.
    fn tap_state(&mut self) -> &mut TapState;
    /// `adb(*args, timeout=...)` -> `[ADB, -s, SERIAL, *args]`.
    fn adb(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError>;
    /// The same argv run by `shot()` via `subprocess.run` directly (tests patch the two apart).
    fn exec(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError> {
        self.adb(args, timeout_s)
    }
    /// `TMP` (`.spectre/shots-<pid>`).
    fn shots_dir(&self) -> PathBuf;
    /// `print(..., flush=True)`.
    fn print(&mut self, line: &str);
    /// An event of the §4.1 stream (no-op where nobody listens).
    fn trace(&mut self, _ev: Value) {}
    /// `time.sleep(s)` through the injected clock.
    fn sleep(&mut self, s: f64);
    /// `time.time()` through the injected clock.
    fn now(&mut self) -> f64;

    // ---- high level: the Python functions -------------------------------------------
    fn sendevent_device(&mut self) -> Option<TouchDev> {
        tap::sendevent_device(self)
    }
    /// `tap(xy, wait=1.0, mode=None)`; returns the mode used.
    fn tap(&mut self, xy: (i64, i64), wait: f64, mode: Option<TapMode>) -> Result<TapMode> {
        seq::tap(self, xy, wait, mode)
    }
    /// `tap_hold(xy, ms=120, wait=1.0)`.
    fn tap_hold(&mut self, xy: (i64, i64), ms: i64, wait: f64) -> Result<()> {
        seq::tap_hold(self, xy, ms, wait)
    }
    /// `tap_seq(steps, tolerate=True, dry=False)`.
    fn tap_seq(&mut self, steps: &[(i64, i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        seq::tap_seq(self, steps, tolerate, dry)
    }
    /// `key_seq(steps, tolerate=True, dry=False)`.
    fn key_seq(&mut self, steps: &[(i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        seq::key_seq(self, steps, tolerate, dry)
    }
    /// `back(wait=1.5)`.
    fn back(&mut self, wait: f64) -> Result<()> {
        seq::back(self, wait)
    }
    /// `swipe(x1, y1, x2, y2, millis=400, wait=1.0)`.
    fn swipe(&mut self, from: (i64, i64), to: (i64, i64), millis: i64, wait: f64) -> Result<()> {
        seq::swipe(self, from, to, millis, wait)
    }
    /// `shot(name)`.
    fn shot(&mut self, name: &str) -> Result<Frame> {
        screencap::shot(self, name)
    }
}

/// The real device: adb through a `CommandRunner`, an injected clock, a trace.
pub struct AdbDevice<R> {
    pub adb: Adb<R>,
    pub state: TapState,
    pub clock: Box<dyn Clock>,
    pub trace: Trace,
    pub shots: PathBuf,
    /// Printed lines (also echoed to stdout when `echo`).
    pub log: Vec<String>,
    pub echo: bool,
}

impl<R: CommandRunner> AdbDevice<R> {
    pub fn new(runner: R, clock: Box<dyn Clock>, trace: Trace, shots: PathBuf) -> Self {
        Self { adb: Adb::new(runner), state: TapState::default(), clock, trace, shots, log: Vec::new(), echo: false }
    }
}

impl<R: CommandRunner> Device for AdbDevice<R> {
    fn tap_state(&mut self) -> &mut TapState {
        &mut self.state
    }

    fn adb(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError> {
        let res = self.adb.run(args, timeout_s);
        self.trace.push(ev_io("adb", args, timeout_s, &res.as_ref().map(|o| o.code)));
        res
    }

    fn exec(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError> {
        let res = self.adb.run(args, timeout_s);
        let mut full = vec![self.adb.bin.clone()];
        full.extend(self.adb.argv(args));
        self.trace.push(ev_io("run", &full, timeout_s, &res.as_ref().map(|o| o.code)));
        res
    }

    fn shots_dir(&self) -> PathBuf {
        self.shots.clone()
    }

    fn print(&mut self, line: &str) {
        if self.echo {
            println!("{line}");
        }
        self.log.push(line.to_owned());
    }

    fn trace(&mut self, ev: Value) {
        self.trace.push(ev);
    }

    fn sleep(&mut self, s: f64) {
        self.trace.push(ev_sleep(s));
        self.clock.sleep(s);
    }

    fn now(&mut self) -> f64 {
        let v = self.clock.now();
        self.trace.push(ev_now("time.time", v));
        v
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::infra::clock::FakeClock;
    use serde_json::json;
    use std::time::Duration;

    struct Scripted(Vec<std::result::Result<Output, RunError>>, Vec<Vec<String>>);

    impl CommandRunner for Scripted {
        fn run(&mut self, _p: &str, a: &[String], _t: Duration) -> std::result::Result<Output, RunError> {
            self.1.push(a.to_vec());
            self.0.remove(0)
        }
    }

    #[test]
    fn trace_follows_the_recorder_schema() {
        let ok = Output { code: Some(0), ..Default::default() };
        let runner = Scripted(vec![Ok(ok), Err(RunError::Timeout)], vec![]);
        let mut d = AdbDevice::new(runner, Box::new(FakeClock::default()), Trace::new(), std::env::temp_dir());
        assert_eq!(d.tap((1, 2), 0.5, None).unwrap(), TapMode::Tap);
        assert_eq!(d.adb.runner.1[0], ["-s", "127.0.0.1:5555", "shell", "input", "tap", "1", "2"]);
        assert_eq!(d.swipe((1, 2), (3, 4), 400, 1.0).unwrap_err(), crate::infra::InfraError::Timeout);
        let ev = &d.trace.events;
        assert_eq!(ev[0], json!({"ev": "tap", "x": 1, "y": 2, "mode": "tap", "wait": 0.5}));
        assert_eq!(ev[1], json!({"ev": "adb", "fn": "adb", "argv": ["shell", "input", "tap", "1", "2"],
                                 "kwargs": {"timeout": 30}, "rc": 0}));
        assert_eq!(ev[2], json!({"ev": "sleep", "s": 0.5}));
        assert_eq!(ev[3]["ev"], "swipe");
        assert_eq!(ev[4]["raise"], "TimeoutExpired");
        assert_eq!(ev.len(), 5); // no sleep after the failed swipe
    }
}

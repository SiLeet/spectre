//! Taps and input sequences (afk_claim_vision L589-L691): `_press`, `tap`, `tap_hold`,
//! `_run_seq`, `tap_seq`, `key_seq`, `back`, `swipe`.
//!
//! argv form exactly as Python: `_press` passes the device line split on whitespace
//! (`*line.split()`), `_run_seq` passes ONE argument (`cmd && sleep W && cmd ...`, steps
//! `&&`-joined since the wave-6 review - the plan text says `;`, the code is the reference).

use super::adb::{ADB_TIMEOUT, head120};
use super::device::Device;
use super::tap::{TapMode, tap_cmd};
use super::trace::{ev_hold, ev_key, ev_seq, ev_swipe, ev_tap};
use super::{InfraError, Result};
use crate::pystr::{fmt_g, repr_bytes, split_ws};

/// `_run_seq` result: success flag, or the shell line for `dry=True`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SeqOut {
    Done(bool),
    Line(String),
}

/// `_press(xy, ms, wait, mode, what)`: one `adb shell` with the split tap line;
/// rc != 0 -> RuntimeError; then `time.sleep(wait)`.
pub fn press<D: Device + ?Sized>(dev: &mut D, xy: (i64, i64), ms: i64, wait: f64, mode: Option<TapMode>, what: &str) -> Result<()> {
    let line = tap_cmd(dev, xy.0, xy.1, ms, mode);
    let mut args = vec!["shell".to_owned()];
    args.extend(split_ws(&line));
    let p = dev.adb(&args, ADB_TIMEOUT)?;
    if p.code != Some(0) {
        return Err(InfraError::Runtime(format!(
            "adb {what} failed at ({}, {}): {}",
            xy.0,
            xy.1,
            repr_bytes(head120(&p.stderr))
        )));
    }
    dev.sleep(wait);
    Ok(())
}

/// `tap(xy, wait=1.0, mode=None)`. Returns the mode used (Python returns None; the mode is
/// what FakeDevice reports and what the trace carries).
pub fn tap<D: Device + ?Sized>(dev: &mut D, xy: (i64, i64), wait: f64, mode: Option<TapMode>) -> Result<TapMode> {
    let used = mode.unwrap_or(dev.tap_state().mode);
    dev.trace(ev_tap(xy.0, xy.1, used.as_str(), wait));
    press(dev, xy, 0, wait, mode, "tap")?;
    Ok(used)
}

/// `tap_hold(xy, ms=120, wait=1.0)`: a short press in TAP_MODE.
pub fn tap_hold<D: Device + ?Sized>(dev: &mut D, xy: (i64, i64), ms: i64, wait: f64) -> Result<()> {
    dev.trace(ev_hold(xy.0, xy.1, ms, wait));
    press(dev, xy, ms, wait, None, "hold-tap")
}

/// `_run_seq(cmds, waits, tolerate, dry)`: one `adb shell` for several input commands,
/// `&&`-joined with `sleep W` after every step whose wait > 0; timeout = int(sum(waits)) + 15.
pub fn run_seq<D: Device + ?Sized>(dev: &mut D, cmds: &[String], waits: &[f64], tolerate: bool, dry: bool) -> Result<SeqOut> {
    let mut parts = Vec::new();
    for (cmd, &wait) in cmds.iter().zip(waits) {
        parts.push(cmd.clone());
        if wait > 0.0 {
            parts.push(format!("sleep {}", fmt_g(wait)));
        }
    }
    let line = parts.join(" && ");
    if dry {
        return Ok(SeqOut::Line(line));
    }
    let timeout = (waits.iter().sum::<f64>().trunc() as i64 + 15).max(0) as u64;
    let p = dev.adb(&["shell".to_owned(), line], timeout)?;
    if p.code != Some(0) && !tolerate {
        return Err(InfraError::Runtime(format!(
            "adb input sequence failed: {}",
            repr_bytes(head120(&p.stderr))
        )));
    }
    Ok(SeqOut::Done(p.code == Some(0)))
}

/// `tap_seq(steps)`: several taps in ONE adb round trip (each built by `_tap_cmd` in TAP_MODE).
pub fn tap_seq<D: Device + ?Sized>(dev: &mut D, steps: &[(i64, i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
    if !dry {
        dev.trace(ev_seq(steps));
    }
    let cmds: Vec<String> = steps.iter().map(|&(x, y, _)| tap_cmd(dev, x, y, 0, None)).collect();
    let waits: Vec<f64> = steps.iter().map(|s| s.2).collect();
    run_seq(dev, &cmds, &waits, tolerate, dry)
}

/// `key_seq(steps)`: several keyevents in ONE adb round trip.
pub fn key_seq<D: Device + ?Sized>(dev: &mut D, steps: &[(i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
    if !dry {
        for &(k, w) in steps {
            dev.trace(ev_key(k, w));
        }
    }
    let cmds: Vec<String> = steps.iter().map(|&(k, _)| format!("input keyevent {k}")).collect();
    let waits: Vec<f64> = steps.iter().map(|s| s.1).collect();
    run_seq(dev, &cmds, &waits, tolerate, dry)
}

/// `back(wait=1.5)`: Android BACK (keyevent 4), not tolerated. NEVER on the world view.
pub fn back<D: Device + ?Sized>(dev: &mut D, wait: f64) -> Result<()> {
    dev.key_seq(&[(4, wait)], false, false).map(|_| ())
}

/// `swipe(x1, y1, x2, y2, millis=400, wait=1.0)`.
pub fn swipe<D: Device + ?Sized>(dev: &mut D, from: (i64, i64), to: (i64, i64), millis: i64, wait: f64) -> Result<()> {
    dev.trace(ev_swipe([from.0, from.1, to.0, to.1], millis, wait));
    let args: Vec<String> = ["shell", "input", "swipe"]
        .into_iter()
        .map(str::to_owned)
        .chain([from.0, from.1, to.0, to.1, millis].map(|v| v.to_string()))
        .collect();
    let p = dev.adb(&args, ADB_TIMEOUT)?;
    if p.code != Some(0) {
        return Err(InfraError::Runtime(format!(
            "adb swipe failed ({}, {})->({}, {}): {}",
            from.0,
            from.1,
            to.0,
            to.1,
            repr_bytes(head120(&p.stderr))
        )));
    }
    dev.sleep(wait);
    Ok(())
}

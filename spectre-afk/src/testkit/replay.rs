//! Golden replay of the E1 infra records (`parity/goldens/infra/*.jsonl`, written by
//! `export_goldens.py`'s infra recorder): every direct call a Python test made into the
//! adb/tap/screencap/lock layer, with its arguments, the tap state before/after, the I/O
//! events in between (what the patched `adb`/`subprocess.run`/`time.sleep`/... saw and
//! answered) and the result or exception.
//!
//! [`ReplayDevice`] runs the Rust port of the same function against that script: every adb
//! call must consume the next recorded `adb`/`run` event with the same argv and timeout and
//! gets the recorded answer; device-level events (`tap`, `key`, `shot`, a test `stub`) are
//! answered at the method - exactly where the Python test had patched. Afterwards: result,
//! exception, tap state and "no event left over" must match.

use super::{frame_by_key, parity_dir};
use crate::env;
use crate::img::Frame;
use crate::infra::device::Device;
use crate::infra::screencap::raw_to_frame;
use crate::infra::seq::{self, SeqOut};
use crate::infra::tap::{self, Discovery, TapMode, TapState, TouchDev};
use crate::infra::{InfraError, Result, screencap};
use crate::state::lock;
use serde_json::{Value, json};
use spectre_mcp::{Output, RunError};
use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;

/// Outcome of one record.
#[derive(Debug, Clone, PartialEq)]
pub enum Outcome {
    Pass,
    /// Parity broken: what differs.
    Diff(Vec<String>),
    /// The record needs something the replay cannot model (named).
    Unsupported(String),
}

// ---------------------------------------------------------------- value helpers

fn num(v: &Value) -> Option<f64> {
    v.as_f64()
}

/// Python `int(x)` of a JSON number (truncation toward zero).
fn int(v: &Value) -> Option<i64> {
    v.as_i64().or_else(|| v.as_f64().map(|f| f.trunc() as i64))
}

fn xy(v: &Value) -> Option<(i64, i64)> {
    Some((int(v.get(0)?)?, int(v.get(1)?)?))
}

fn bytes_of(v: &Value) -> Option<Vec<u8>> {
    if let Some(h) = v.get("bytes").and_then(Value::as_str) {
        return (0..h.len()).step_by(2).map(|i| u8::from_str_radix(h.get(i..i + 2)?, 16).ok()).collect();
    }
    if let Some(k) = v.get("blob").and_then(Value::as_str) {
        return std::fs::read(parity_dir().join("blobs").join(format!("{k}.bin"))).ok();
    }
    v.as_str().map(|s| s.as_bytes().to_vec())
}

/// Blobs (`{"blob": k}`) referenced anywhere in `v` that are missing from the corpus dir.
fn missing_blobs(v: &Value, out: &mut Vec<String>) {
    match v {
        Value::Object(m) => {
            if let Some(k) = m.get("blob").and_then(Value::as_str)
                && !parity_dir().join("blobs").join(format!("{k}.bin")).is_file()
            {
                out.push(k.to_owned());
            }
            m.values().for_each(|x| missing_blobs(x, out));
        }
        Value::Array(a) => a.iter().for_each(|x| missing_blobs(x, out)),
        _ => {}
    }
}

/// Bind a recorded call (`args` positional + `kwargs`) to a Python signature with defaults.
fn bind(ev: &Value, params: &[(&str, Value)]) -> Vec<Value> {
    params
        .iter()
        .enumerate()
        .map(|(i, (name, default))| {
            ev["args"].get(i).or_else(|| ev["kwargs"].get(*name)).cloned().unwrap_or_else(|| default.clone())
        })
        .collect()
}

fn mode_of(v: &Value) -> Option<TapMode> {
    v.as_str().and_then(TapMode::parse)
}

fn touch_dev(v: &Value) -> Option<TouchDev> {
    let pair = |k: &str| xy(v.get(k)?);
    Some(TouchDev {
        path: v.get("path")?.as_str()?.to_owned(),
        x: pair("x")?,
        y: pair("y")?,
        tid: v.get("tid").and_then(Value::as_bool).unwrap_or(false),
        btn: v.get("btn").and_then(Value::as_bool).unwrap_or(false),
        slot: v.get("slot").and_then(Value::as_bool).unwrap_or(false),
        root: v.get("root").and_then(Value::as_bool).unwrap_or(false),
    })
}

fn dev_json(d: &TouchDev, with_root: bool) -> Value {
    let mut v = json!({"path": d.path, "x": [d.x.0, d.x.1], "y": [d.y.0, d.y.1], "tid": d.tid, "btn": d.btn, "slot": d.slot});
    if with_root {
        v["root"] = json!(d.root);
    }
    v
}

fn state_of(before: &Value) -> Option<TapState> {
    let sendevent = match &before["SENDEVENT"] {
        Value::Null => Discovery::Untried,
        Value::Bool(false) => Discovery::Unavailable,
        d => Discovery::Found(touch_dev(d)?),
    };
    let dead = before["TAP_DEAD"].as_array()?.iter().map(mode_of).collect::<Option<_>>()?;
    Some(TapState { mode: mode_of(&before["TAP_MODE"])?, dead, sendevent })
}

fn state_json(s: &TapState) -> Value {
    let mut dead: Vec<&str> = s.dead.iter().map(|m| m.as_str()).collect();
    dead.sort_unstable();
    json!({
        "TAP_MODE": s.mode.as_str(),
        "TAP_DEAD": dead,
        "SENDEVENT": match &s.sendevent {
            Discovery::Untried => Value::Null,
            Discovery::Unavailable => json!(false),
            Discovery::Found(d) => dev_json(d, true),
        },
    })
}

/// JSON equality with numbers compared by value (Python `1` == Rust `1.0`).
pub fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) => x.as_f64() == y.as_f64(),
        (Value::Array(x), Value::Array(y)) => x.len() == y.len() && x.iter().zip(y).all(|(p, q)| same(p, q)),
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| same(v, w)))
        }
        _ => a == b,
    }
}

fn frame_json(f: &Frame) -> Value {
    json!({"img": f.key(), "w": f.w, "h": f.h, "mode": "RGB", "crc32": f.crc32()})
}

// ---------------------------------------------------------------- script

struct Script {
    events: Vec<Value>,
    pos: usize,
    sleeps: bool,
    diffs: Vec<String>,
}

type Shared = Rc<RefCell<Script>>;

/// The Rust infra against a recorded script.
pub struct ReplayDevice {
    script: Shared,
    pub state: TapState,
    pub shots: PathBuf,
    pub log: Vec<String>,
    /// `str(ADB)` the recorded full argv (`run` events) starts with.
    adb_bin: String,
}

impl ReplayDevice {
    fn peek(&self) -> Option<Value> {
        let s = self.script.borrow();
        s.events.get(s.pos).cloned()
    }

    fn take(&self) -> Option<Value> {
        let mut s = self.script.borrow_mut();
        let ev = s.events.get(s.pos).cloned();
        if ev.is_some() {
            s.pos += 1;
        }
        ev
    }

    fn diff(&self, msg: String) {
        self.script.borrow_mut().diffs.push(msg);
    }

    /// Next event is a device-level event (or a test stub) for this method -> answer it here.
    fn intercept(&self, ev_type: &str, method: &str) -> Option<Value> {
        let ev = self.peek()?;
        let t = ev["ev"].as_str().unwrap_or("");
        let hit = t == ev_type || (t == "stub" && ev["fn"].as_str() == Some(&format!("afk_claim_vision.{method}")));
        hit.then(|| self.take()).flatten()
    }

    fn raised(ev: &Value) -> Option<InfraError> {
        ev["raise"].as_str().map(|n| InfraError::from_py_type(n, "replayed"))
    }

    fn answer(&mut self, args: &[String], timeout_s: u64, direct: bool) -> std::result::Result<Output, RunError> {
        let Some(ev) = self.take() else {
            self.diff(format!("extra adb call {args:?}"));
            return Err(RunError::Spawn("replay: no event left".into()));
        };
        let argv: Option<Vec<String>> = ev["argv"].as_array().and_then(|a| a.iter().map(|x| x.as_str().map(str::to_owned)).collect());
        let want_timeout = ev["kwargs"]["timeout"].as_u64();
        match (ev["ev"].as_str(), argv) {
            (Some("adb"), Some(a)) if ev["fn"].as_str().unwrap_or("adb") == "adb" && !direct => {
                if a != args {
                    self.diff(format!("adb argv {args:?} != recorded {a:?}"));
                }
                if want_timeout.unwrap_or(crate::infra::adb::ADB_TIMEOUT) != timeout_s {
                    self.diff(format!("adb timeout {timeout_s} != recorded {want_timeout:?}"));
                }
            }
            (Some("run"), Some(a)) => {
                let mut mine = vec![self.adb_bin.clone(), "-s".into(), env::SERIAL.into()];
                mine.extend_from_slice(args);
                if a != mine {
                    self.diff(format!("run argv {mine:?} != recorded {a:?}"));
                }
                if want_timeout != Some(timeout_s) {
                    self.diff(format!("run timeout {timeout_s} != recorded {want_timeout:?}"));
                }
            }
            _ => {
                self.diff(format!("adb call {args:?} met event {ev}"));
                return Err(RunError::Spawn("replay: wrong event".into()));
            }
        }
        if let Some(name) = ev["raise"].as_str() {
            return Err(if name == "TimeoutExpired" { RunError::Timeout } else { RunError::Spawn(name.into()) });
        }
        let out = &ev["out"];
        let code = ev["rc"].as_i64().or_else(|| out["rc"].as_i64()).map(|c| c as i32);
        if code.is_none() {
            self.diff(format!("adb answer not a CompletedProcess: {out}"));
        }
        let stdout = ev.get("stdout_file").and_then(bytes_of).or_else(|| bytes_of(&out["stdout"])).unwrap_or_default();
        let stderr = bytes_of(&out["stderr"]).unwrap_or_default();
        Ok(Output { code, stdout, stderr })
    }
}

impl Device for ReplayDevice {
    fn tap_state(&mut self) -> &mut TapState {
        &mut self.state
    }

    fn adb(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError> {
        self.answer(args, timeout_s, false)
    }

    fn exec(&mut self, args: &[String], timeout_s: u64) -> std::result::Result<Output, RunError> {
        self.answer(args, timeout_s, true)
    }

    fn shots_dir(&self) -> PathBuf {
        self.shots.clone()
    }

    fn print(&mut self, line: &str) {
        self.log.push(line.to_owned());
    }

    fn sleep(&mut self, s: f64) {
        if !self.script.borrow().sleeps {
            return; // the test did not patch time.sleep: Python slept for real, nothing recorded
        }
        match self.take() {
            Some(ev) if ev["ev"] == "sleep" && num(&ev["s"]) == Some(s) => {}
            other => self.diff(format!("sleep({s}) met {other:?}")),
        }
    }

    fn now(&mut self) -> f64 {
        0.0
    }

    fn sendevent_device(&mut self) -> Option<TouchDev> {
        match self.intercept("-", "sendevent_device") {
            Some(ev) => {
                self.check_stub_args(&ev, &[], &[]);
                touch_dev(&ev["out"])
            }
            None => tap::sendevent_device(self),
        }
    }

    fn tap(&mut self, xy_: (i64, i64), wait: f64, mode: Option<TapMode>) -> Result<TapMode> {
        let used = mode.unwrap_or(self.state.mode);
        let Some(ev) = self.intercept("tap", "tap") else { return seq::tap(self, xy_, wait, mode) };
        if ev["ev"] == "tap" {
            if (int(&ev["x"]), int(&ev["y"]), num(&ev["wait"])) != (Some(xy_.0), Some(xy_.1), Some(wait)) {
                self.diff(format!("tap {xy_:?} wait {wait} != recorded {ev}"));
            }
            // mode_arg = what the caller passed, mode = what the (fake) tap used
            if ev.get("mode_arg").is_some() && ev["mode_arg"].as_str() != mode.map(TapMode::as_str) {
                self.diff(format!("tap mode arg {mode:?} != recorded {}", ev["mode_arg"]));
            }
            if let Some(m) = ev["mode"].as_str()
                && m != used.as_str()
            {
                self.diff(format!("tap used mode {used} != recorded {m}"));
            }
        } else {
            self.check_stub_args(
                &ev,
                &[("xy", Value::Null), ("wait", json!(1.0)), ("mode", Value::Null)],
                &[json!([xy_.0, xy_.1]), json!(wait), json!(mode.map(TapMode::as_str))],
            );
        }
        match Self::raised(&ev) {
            Some(e) => Err(e),
            None => Ok(mode_of(&ev["mode"]).unwrap_or(used)),
        }
    }

    fn tap_hold(&mut self, xy_: (i64, i64), ms: i64, wait: f64) -> Result<()> {
        let Some(ev) = self.intercept("hold", "tap_hold") else { return seq::tap_hold(self, xy_, ms, wait) };
        if ev["ev"] == "hold" {
            if (int(&ev["x"]), int(&ev["y"]), int(&ev["ms"]), num(&ev["wait"])) != (Some(xy_.0), Some(xy_.1), Some(ms), Some(wait)) {
                self.diff(format!("hold {xy_:?} {ms} {wait} != recorded {ev}"));
            }
        } else {
            self.check_stub_args(
                &ev,
                &[("xy", Value::Null), ("ms", json!(120)), ("wait", json!(1.0))],
                &[json!([xy_.0, xy_.1]), json!(ms), json!(wait)],
            );
        }
        Self::raised(&ev).map_or(Ok(()), Err)
    }

    fn tap_seq(&mut self, steps: &[(i64, i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        let Some(ev) = self.intercept("seq", "tap_seq") else { return seq::tap_seq(self, steps, tolerate, dry) };
        let mine = json!(steps.iter().map(|&(x, y, w)| json!([x, y, w])).collect::<Vec<_>>());
        if ev["ev"] == "seq" {
            if !same(&ev["steps"], &mine) {
                self.diff(format!("tap_seq {mine} != recorded {}", ev["steps"]));
            }
            self.check_flags(&ev, tolerate, dry);
        } else {
            self.check_stub_args(
                &ev,
                &[("steps", Value::Null), ("tolerate", json!(true)), ("dry", json!(false))],
                &[mine, json!(tolerate), json!(dry)],
            );
        }
        Self::raised(&ev).map_or_else(|| Ok(seq_out(&ev["out"])), Err)
    }

    fn key_seq(&mut self, steps: &[(i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        if let Some(ev) = self.intercept("-", "key_seq") {
            let mine = json!(steps.iter().map(|&(k, w)| json!([k, w])).collect::<Vec<_>>());
            self.check_stub_args(
                &ev,
                &[("steps", Value::Null), ("tolerate", json!(true)), ("dry", json!(false))],
                &[mine, json!(tolerate), json!(dry)],
            );
            return Self::raised(&ev).map_or_else(|| Ok(seq_out(&ev["out"])), Err);
        }
        if self.peek().is_none_or(|e| e["ev"] != "key") {
            return seq::key_seq(self, steps, tolerate, dry);
        }
        let mut raised = None;
        for &(k, w) in steps {
            match self.take() {
                Some(ev) if ev["ev"] == "key" && int(&ev["code"]) == Some(k) && num(&ev["w"]) == Some(w) => {
                    self.check_flags(&ev, tolerate, dry);
                    raised = raised.or_else(|| Self::raised(&ev));
                }
                other => self.diff(format!("key ({k}, {w}) met {other:?}")),
            }
        }
        raised.map_or(Ok(SeqOut::Done(true)), Err)
    }

    fn back(&mut self, wait: f64) -> Result<()> {
        match self.intercept("-", "back") {
            Some(ev) => {
                self.check_stub_args(&ev, &[("wait", json!(1.5))], &[json!(wait)]);
                Self::raised(&ev).map_or(Ok(()), Err)
            }
            None => seq::back(self, wait),
        }
    }

    fn swipe(&mut self, from: (i64, i64), to: (i64, i64), millis: i64, wait: f64) -> Result<()> {
        let Some(ev) = self.intercept("swipe", "swipe") else { return seq::swipe(self, from, to, millis, wait) };
        self.check_stub_args(
            &ev,
            &[
                ("x1", Value::Null),
                ("y1", Value::Null),
                ("x2", Value::Null),
                ("y2", Value::Null),
                ("millis", json!(400)),
                ("wait", json!(1.0)),
            ],
            &[json!(from.0), json!(from.1), json!(to.0), json!(to.1), json!(millis), json!(wait)],
        );
        Self::raised(&ev).map_or(Ok(()), Err)
    }

    fn shot(&mut self, name: &str) -> Result<Frame> {
        let Some(ev) = self.intercept("shot", "shot") else { return screencap::shot(self, name) };
        if ev["ev"] == "shot" {
            if ev["name"].as_str() != Some(name) {
                self.diff(format!("shot {name:?} != recorded {}", ev["name"]));
            }
        } else {
            self.check_stub_args(&ev, &[("name", Value::Null)], &[json!(name)]);
        }
        if let Some(e) = Self::raised(&ev) {
            return Err(e);
        }
        let key = ev["frame"].as_str().or_else(|| ev["out"]["img"].as_str()).unwrap_or("");
        frame_by_key(key).map_err(|e| InfraError::Fail(format!("{e:#}")))
    }
}

/// A stub's / fake's recorded return value of tap_seq/key_seq (`True`, `False` or the dry line).
fn seq_out(out: &Value) -> SeqOut {
    match out {
        Value::String(s) => SeqOut::Line(s.clone()),
        Value::Bool(b) => SeqOut::Done(*b),
        _ => SeqOut::Done(true), // FakeDevice returns True; a MagicMock is truthy
    }
}

impl ReplayDevice {
    /// A device-level `stub`/`swipe` event: bind its recorded args to the Python signature and
    /// compare with what the Rust caller passed.
    fn check_stub_args(&self, ev: &Value, params: &[(&str, Value)], mine: &[Value]) {
        if ev.get("args").is_none() && ev.get("kwargs").is_none() {
            return;
        }
        let rec = bind(ev, params);
        for (((name, _), r), m) in params.iter().zip(&rec).zip(mine) {
            if !same(r, m) {
                self.diff(format!("{}: arg {name} {m} != recorded {r}", ev["fn"].as_str().unwrap_or("swipe")));
            }
        }
    }

    /// `tolerate`/`dry` the fake recorded for tap_seq/key_seq.
    fn check_flags(&self, ev: &Value, tolerate: bool, dry: bool) {
        for (k, v) in [("tolerate", tolerate), ("dry", dry)] {
            if let Some(r) = ev.get(k)
                && r.as_bool() != Some(v)
            {
                self.diff(format!("{} {k}={v} != recorded {r}", ev["ev"]));
            }
        }
    }
}

// ---------------------------------------------------------------- records

fn arg<'a>(rec: &'a Value, i: usize, name: &str) -> Option<&'a Value> {
    rec["args"].get(i).or_else(|| rec["kwargs"].get(name))
}

fn arg_f(rec: &Value, i: usize, name: &str, default: f64) -> f64 {
    arg(rec, i, name).and_then(num).unwrap_or(default)
}

fn arg_i(rec: &Value, i: usize, name: &str, default: i64) -> i64 {
    arg(rec, i, name).and_then(int).unwrap_or(default)
}

fn arg_b(rec: &Value, i: usize, name: &str, default: bool) -> bool {
    arg(rec, i, name).and_then(Value::as_bool).unwrap_or(default)
}

fn arg_mode(rec: &Value, i: usize, name: &str) -> Option<TapMode> {
    arg(rec, i, name).and_then(mode_of)
}

const SUPPORTED_EVENTS: [&str; 10] = ["adb", "run", "sleep", "tap", "hold", "seq", "key", "swipe", "shot", "stub"];

fn shots_tmp() -> PathBuf {
    std::env::temp_dir().join(format!("spectre-afk-replay-{}", std::process::id()))
}

/// Replay one `afk_claim_vision.*` infra record; `log` receives the lines the port printed.
pub fn replay_vision(rec: &Value, log: &mut Vec<String>) -> Outcome {
    let fname = rec["fn"].as_str().unwrap_or("").trim_start_matches("afk_claim_vision.");
    let events = rec["events"].as_array().cloned().unwrap_or_default();
    for ev in &events {
        let t = ev["ev"].as_str().unwrap_or("?");
        if !SUPPORTED_EVENTS.contains(&t) {
            return Outcome::Unsupported(format!("event '{t}' inside {fname}"));
        }
        if t == "stub" && !ev["fn"].as_str().unwrap_or("").starts_with("afk_claim_vision.") {
            return Outcome::Unsupported(format!("stub {} inside {fname}", ev["fn"]));
        }
        if t == "adb" && ev["fn"].as_str().is_some_and(|f| f != "adb") {
            return Outcome::Unsupported(format!("{} inside {fname}", ev["fn"]));
        }
    }
    let Some(state) = state_of(&rec["before"]) else {
        return Outcome::Unsupported(format!("before state {}", rec["before"]));
    };
    // patched time.sleep -> every Rust sleep must meet a recorded one; unpatched -> Python
    // really slept and nothing could be recorded
    let Some(sleeps) = rec["before"]["sleep_patched"].as_bool() else {
        return Outcome::Unsupported("record without sleep_patched (re-export the goldens)".into());
    };
    let mut blobs = Vec::new();
    missing_blobs(rec, &mut blobs);
    if !blobs.is_empty() {
        return Outcome::Unsupported(format!("blob(s) missing in $SPECTRE_PARITY_DIR/blobs: {blobs:?}"));
    }
    let script = Rc::new(RefCell::new(Script { events, pos: 0, sleeps, diffs: Vec::new() }));
    let shots = shots_tmp();
    let mut dev = ReplayDevice { script: script.clone(), state, shots: shots.clone(), log: Vec::new(), adb_bin: env::adb_bin() };
    let shot_name = (fname == "shot").then(|| arg(rec, 0, "name").and_then(Value::as_str).unwrap_or("shot").to_owned());
    if let Some(n) = &shot_name {
        let _ = std::fs::remove_file(shots.join(format!("{n}.png")));
    }

    // run the Rust port; `out` is the Python-shaped return value
    let res: std::result::Result<Value, InfraError> = (|| -> std::result::Result<Value, InfraError> {
        Ok(match fname {
            "_env_tap_mode" => {
                let (mode, warn) = env::tap_mode_env(rec["before"]["env"]["AFK_TAP_MODE"].as_str());
                if let Some(w) = warn {
                    dev.print(&w); // Python prints the WARN inside _env_tap_mode
                }
                json!(mode.as_str())
            }
            "parse_getevent" => {
                let text = arg(rec, 0, "text").and_then(Value::as_str).unwrap_or("");
                tap::parse_getevent(text).map_or(Value::Null, |d| dev_json(&d, false))
            }
            "sendevent_cmds" => {
                let d = arg(rec, 0, "dev").and_then(touch_dev).ok_or_else(|| InfraError::Fail("dev arg".into()))?;
                json!(tap::sendevent_cmds(&d, arg_i(rec, 1, "x", 0), arg_i(rec, 2, "y", 0), arg_i(rec, 3, "ms", 0)))
            }
            "sendevent_device" => tap::sendevent_device(&mut dev).map_or(Value::Null, |d| dev_json(&d, true)),
            "_tap_cmd" => {
                let (x, y) = (arg_i(rec, 0, "x", 0), arg_i(rec, 1, "y", 0));
                json!(tap::tap_cmd(&mut dev, x, y, arg_i(rec, 2, "ms", 0), arg_mode(rec, 3, "mode")))
            }
            "_press" => {
                let p = arg(rec, 0, "xy").and_then(xy).ok_or_else(|| InfraError::Fail("xy".into()))?;
                let what = arg(rec, 4, "what").and_then(Value::as_str).unwrap_or("tap").to_owned();
                seq::press(&mut dev, p, arg_i(rec, 1, "ms", 0), arg_f(rec, 2, "wait", 1.0), arg_mode(rec, 3, "mode"), &what)?;
                Value::Null
            }
            "tap" => {
                let p = arg(rec, 0, "xy").and_then(xy).ok_or_else(|| InfraError::Fail("xy".into()))?;
                seq::tap(&mut dev, p, arg_f(rec, 1, "wait", 1.0), arg_mode(rec, 2, "mode"))?;
                Value::Null
            }
            "tap_retry" => {
                let p = arg(rec, 0, "xy").and_then(xy).ok_or_else(|| InfraError::Fail("xy".into()))?;
                tap::tap_retry(&mut dev, p, arg_f(rec, 1, "wait", 1.0))?.map_or(Value::Null, |m| json!(m.as_str()))
            }
            "tap_result" => {
                tap::tap_result(&mut dev, arg_mode(rec, 0, "mode"), arg_b(rec, 1, "changed", false));
                Value::Null
            }
            "_run_seq" | "tap_seq" | "key_seq" => {
                let tol_i = if fname == "_run_seq" { 2 } else { 1 };
                let (tolerate, dry) = (arg_b(rec, tol_i, "tolerate", true), arg_b(rec, tol_i + 1, "dry", false));
                let out = match fname {
                    "_run_seq" => {
                        let cmds: Vec<String> = arg(rec, 0, "cmds").and_then(Value::as_array).into_iter().flatten()
                            .filter_map(|c| c.as_str().map(str::to_owned)).collect();
                        let waits: Vec<f64> = arg(rec, 1, "waits").and_then(Value::as_array).into_iter().flatten().filter_map(num).collect();
                        seq::run_seq(&mut dev, &cmds, &waits, tolerate, dry)?
                    }
                    "tap_seq" => {
                        let steps: Vec<(i64, i64, f64)> = arg(rec, 0, "steps").and_then(Value::as_array).into_iter().flatten()
                            .filter_map(|s| Some((int(s.get(0)?)?, int(s.get(1)?)?, num(s.get(2)?)?))).collect();
                        seq::tap_seq(&mut dev, &steps, tolerate, dry)?
                    }
                    _ => {
                        let steps: Vec<(i64, f64)> = arg(rec, 0, "steps").and_then(Value::as_array).into_iter().flatten()
                            .filter_map(|s| Some((int(s.get(0)?)?, num(s.get(1)?)?))).collect();
                        seq::key_seq(&mut dev, &steps, tolerate, dry)?
                    }
                };
                match out {
                    SeqOut::Done(b) => json!(b),
                    SeqOut::Line(l) => json!(l),
                }
            }
            "back" => {
                seq::back(&mut dev, arg_f(rec, 0, "wait", 1.5))?;
                Value::Null
            }
            "tap_hold" => {
                let p = arg(rec, 0, "xy").and_then(xy).ok_or_else(|| InfraError::Fail("xy".into()))?;
                seq::tap_hold(&mut dev, p, arg_i(rec, 1, "ms", 120), arg_f(rec, 2, "wait", 1.0))?;
                Value::Null
            }
            "swipe" => {
                let (a, b) = ((arg_i(rec, 0, "x1", 0), arg_i(rec, 1, "y1", 0)), (arg_i(rec, 2, "x2", 0), arg_i(rec, 3, "y2", 0)));
                seq::swipe(&mut dev, a, b, arg_i(rec, 4, "millis", 400), arg_f(rec, 5, "wait", 1.0))?;
                Value::Null
            }
            "_raw_to_image" => {
                let data = arg(rec, 0, "data").and_then(bytes_of).ok_or_else(|| InfraError::Fail("data arg".into()))?;
                raw_to_frame(&data).map_or(Value::Null, |f| frame_json(&f))
            }
            "shot" => {
                let name = arg(rec, 0, "name").and_then(Value::as_str).unwrap_or("shot").to_owned();
                frame_json(&screencap::shot(&mut dev, &name)?)
            }
            "adb" => {
                let args: Vec<String> = rec["args"].as_array().into_iter().flatten().filter_map(|a| a.as_str().map(str::to_owned)).collect();
                let t = rec["kwargs"]["timeout"].as_u64().unwrap_or(crate::infra::adb::ADB_TIMEOUT);
                let o = dev.adb(&args, t)?;
                let hex = |b: &[u8]| b.iter().map(|x| format!("{x:02x}")).collect::<String>();
                json!({"rc": o.code, "stdout": {"bytes": hex(&o.stdout)}, "stderr": {"bytes": hex(&o.stderr)}})
            }
            other => return Err(InfraError::Fail(format!("no Rust port for {other}"))),
        })
    })();

    let mut diffs = std::mem::take(&mut script.borrow_mut().diffs);
    match (&res, rec["raise"].as_str()) {
        (Ok(out), None) => {
            let want = &rec["out"];
            let ok = match fname {
                "adb" => {
                    out["rc"] == want["rc"]
                        && bytes_of(&out["stdout"]) == bytes_of(&want["stdout"])
                        && bytes_of(&out["stderr"]) == bytes_of(&want["stderr"])
                }
                "shot" | "_raw_to_image" if !want.is_null() => {
                    ["img", "w", "h", "crc32"].iter().all(|k| same(&out[*k], &want[*k]))
                }
                _ => same(out, want),
            };
            if !ok {
                diffs.push(format!("out {out} != recorded {want}"));
            }
        }
        (Err(e), Some(name)) => {
            fn fam(n: &str) -> &str {
                if matches!(n, "FileNotFoundError" | "PermissionError") { "OSError" } else { n }
            }
            if fam(e.py_type()) != fam(name) {
                diffs.push(format!("raised {} != recorded {name}", e.py_type()));
            }
        }
        (Ok(out), Some(name)) => diffs.push(format!("returned {out}, recorded raise {name}")),
        (Err(e), None) => {
            if let InfraError::Fail(m) = e
                && m.starts_with("no Rust port")
            {
                return Outcome::Unsupported(m.clone());
            }
            diffs.push(format!("raised {e:?}, recorded out {}", rec["out"]));
        }
    }
    let s = script.borrow();
    if s.pos != s.events.len() {
        diffs.push(format!("{} recorded event(s) not consumed, next {}", s.events.len() - s.pos, s.events[s.pos]));
    }
    let after = state_json(&dev.state);
    for k in ["TAP_MODE", "TAP_DEAD", "SENDEVENT"] {
        if !same(&after[k], &rec["after"][k]) {
            diffs.push(format!("after.{k} {} != recorded {}", after[k], rec["after"][k]));
        }
    }
    if let Some(n) = &shot_name {
        diffs.extend(check_shot_file(&shots.join(format!("{n}.png")), &rec["after"]["file"], res.as_ref().ok()));
    }
    drop(s);
    *log = std::mem::take(&mut dev.log);
    if diffs.is_empty() { Outcome::Pass } else { Outcome::Diff(diffs) }
}

/// `shot()` persists TMP/<name>.png (OCR and region crops read it): it must exist exactly when
/// Python's did, hold the returned pixels and carry only IHDR/IDAT/IEND (plan §E1).
fn check_shot_file(path: &std::path::Path, want: &Value, out: Option<&Value>) -> Vec<String> {
    let mut d = Vec::new();
    let exists = path.is_file();
    if want.get("exists").and_then(Value::as_bool) != Some(exists) {
        d.push(format!("shot file exists={exists} != recorded {want}"));
        return d;
    }
    if let (true, Some(out)) = (exists, out) {
        let bytes = std::fs::read(path).unwrap_or_default();
        let chunks = crate::img::png_chunks(&bytes);
        if !chunks.iter().all(|c| matches!(c.as_str(), "IHDR" | "IDAT" | "IEND")) {
            d.push(format!("shot file chunks {chunks:?}: only IHDR/IDAT/IEND allowed"));
        }
        match crate::img::load_rgb(path) {
            Ok(f) if same(&frame_json(&f)["crc32"], &out["crc32"]) => {}
            Ok(f) => d.push(format!("shot file pixels crc {} != returned {}", f.crc32(), out["crc32"])),
            Err(e) => d.push(format!("shot file unreadable: {e}")),
        }
    }
    d
}

/// The lines the Python call printed vs the Rust port's `print` lines (plan §4.3: stdout is a
/// contract only for contract lines, which E0b-2 still has to list; reported, not failed).
pub fn stdout_diff(rec: &Value, rust_lines: &[String]) -> Option<String> {
    let py = rec["stdout"].as_str()?;
    let py_lines: Vec<&str> = crate::pystr::splitlines(py);
    (py_lines != rust_lines.iter().map(String::as_str).collect::<Vec<_>>())
        .then(|| format!("python {py_lines:?} / rust {rust_lines:?}"))
}

/// Replay one `_bot_lock.*` record against a temp lock file with the recorded state.
pub fn replay_lock(rec: &Value) -> Outcome {
    let fname = rec["fn"].as_str().unwrap_or("").trim_start_matches("_bot_lock.");
    let before = &rec["before"];
    let dir = shots_tmp().join(format!("lock-{}", rec["test"].as_str().unwrap_or("").len()));
    let _ = std::fs::remove_dir_all(&dir);
    let path = dir.join("afk-bot.lock");
    let pid = std::process::id();
    let pid_text = |t: &str| if t == "<PID>" { pid.to_string() } else { t.to_owned() };
    let unpid = |t: String| if crate::pystr::strip(&t) == pid.to_string() { "<PID>".to_owned() } else { t };
    let now_arg = arg(rec, 3, "now").and_then(num);
    let wall = std::time::SystemTime::now();
    let now_s = now_arg.unwrap_or_else(|| wall.duration_since(std::time::UNIX_EPOCH).map_or(0.0, |d| d.as_secs_f64()));
    if before["exists"] == true {
        std::fs::create_dir_all(&dir).expect("temp dir");
        std::fs::write(&path, pid_text(before["text"].as_str().unwrap_or(""))).expect("lock write");
        // recorded age is int(now - mtime): put mtime in the middle of that second
        let age = before["age"].as_f64().unwrap_or(0.0) + 0.5;
        let mtime = std::time::UNIX_EPOCH + std::time::Duration::from_secs_f64((now_s - age).max(0.0));
        std::fs::File::options().write(true).open(&path).and_then(|f| f.set_modified(mtime)).expect("set mtime");
    }
    // env: the explicit dict the test passed, else the recorded os.environ subset
    let env_v = arg(rec, 1, "env").cloned().unwrap_or_else(|| before["env"].clone());
    let env_get = move |k: &str| env_v.get(k).and_then(Value::as_str).map(str::to_owned);
    let res: std::result::Result<Value, lock::LockError> = match fname {
        "acquire" => lock::acquire(&path, &env_get, arg(rec, 2, "stale").and_then(int), now_arg, pid).map(|b| json!(b)),
        "release" => lock::release(&path, &env_get, pid).map(|_| Value::Null),
        "describe" => lock::describe(&path, None).map(|s| json!(s.replace(&format!("pid {pid},"), "pid <PID>,"))),
        other => return Outcome::Unsupported(format!("no Rust port for _bot_lock.{other}")),
    };
    let mut diffs = Vec::new();
    match (res, rec["raise"].as_str()) {
        (Ok(out), None) => {
            if !same(&out, &rec["out"]) {
                diffs.push(format!("out {out} != recorded {}", rec["out"]));
            }
        }
        (Err(e), Some(name)) => {
            let mine = match e {
                lock::LockError::BadStale(_) => "ValueError",
                lock::LockError::Io(_) => "OSError",
            };
            let fam = if matches!(name, "FileNotFoundError" | "PermissionError" | "IsADirectoryError") { "OSError" } else { name };
            if mine != fam {
                diffs.push(format!("raised {mine} != recorded {name}"));
            }
        }
        (Ok(out), Some(n)) => diffs.push(format!("returned {out}, recorded raise {n}")),
        (Err(e), None) => diffs.push(format!("raised {e}, recorded out {}", rec["out"])),
    }
    let after = &rec["after"];
    let exists = path.exists();
    if json!(exists) != after["exists"] {
        diffs.push(format!("after.exists {exists} != recorded {}", after["exists"]));
    } else if exists {
        let text = unpid(std::fs::read_to_string(&path).unwrap_or_default());
        if json!(text) != after["text"] {
            diffs.push(format!("after.text {text:?} != recorded {}", after["text"]));
        }
    }
    let _ = std::fs::remove_dir_all(&dir);
    if diffs.is_empty() { Outcome::Pass } else { Outcome::Diff(diffs) }
}

//! Test doubles of `scripts/tests/fake_vision.py`: [`FakeDevice`] (scripted frames, tap/shot
//! log) and [`DeadTapDevice`] (taps change nothing, only keyevent 4 advances), same guards:
//! an unscripted shot fails, keyevent 4 on a WORLD frame fails, a real adb call fails.
//! The synthetic `_SPEC` renderer is not ported: the corpus PNGs are the fixtures.

use crate::img::Frame;
use crate::infra::clock::{Clock, FakeClock};
use crate::infra::device::Device;
use crate::infra::seq::SeqOut;
use crate::infra::tap::{Discovery, TapMode, TapState};
use crate::infra::trace::{Trace, ev_hold, ev_key, ev_seq, ev_shot, ev_sleep, ev_swipe, ev_tap};
use crate::infra::{InfraError, Result};
use serde_json::Value;
use spectre_mcp::{Output, RunError};
use std::collections::VecDeque;
use std::path::PathBuf;

/// One entry of `dev.taps` (Python: `(x, y)`, `(mode, x, y)`, `('key', k)`, `('hold', x, y)`,
/// `('swipe', ...)`).
#[derive(Debug, Clone, PartialEq)]
pub enum TapLog {
    At(i64, i64),
    Mode(TapMode, i64, i64),
    Key(i64),
    Hold(i64, i64),
    Swipe((i64, i64), (i64, i64), i64, f64),
}

/// Reads a frame as the world view (the keyevent-4 guard). E2 plugs `classify(img) == 'WORLD'`.
pub type WorldCheck = Box<dyn Fn(&Frame) -> bool>;

pub struct FakeDevice {
    pub frames: VecDeque<Frame>,
    pub taps: Vec<TapLog>,
    pub shots: Vec<String>,
    /// Frame of the latest shot (T97 world-BACK guard).
    pub last: Option<Frame>,
    pub state: TapState,
    pub trace: Trace,
    pub clock: FakeClock,
    pub log: Vec<String>,
    pub world: Option<WorldCheck>,
    pub shots_dir: PathBuf,
}

impl FakeDevice {
    /// Like `FakeDevice(test, frames)`: TAP_MODE 'tap', no dead modes, sendevent unavailable.
    pub fn new(frames: Vec<Frame>) -> Self {
        Self {
            frames: frames.into(),
            taps: Vec::new(),
            shots: Vec::new(),
            last: None,
            state: TapState { mode: TapMode::Tap, dead: Default::default(), sendevent: Discovery::Unavailable },
            trace: Trace::new(),
            clock: FakeClock::default(),
            log: Vec::new(),
            world: None,
            shots_dir: std::env::temp_dir().join(format!("spectre-afk-fake-{}", std::process::id())),
        }
    }

    pub fn with_world(mut self, check: WorldCheck) -> Self {
        self.world = Some(check);
        self
    }
}

impl Device for FakeDevice {
    fn tap_state(&mut self) -> &mut TapState {
        &mut self.state
    }

    fn adb(&mut self, args: &[String], _timeout_s: u64) -> std::result::Result<Output, RunError> {
        panic!("real adb call: {args:?}") // test.fail(...) in Python
    }

    fn shots_dir(&self) -> PathBuf {
        self.shots_dir.clone()
    }

    fn print(&mut self, line: &str) {
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
        self.clock.now()
    }

    fn tap(&mut self, xy: (i64, i64), wait: f64, mode: Option<TapMode>) -> Result<TapMode> {
        let mode = mode.unwrap_or(self.state.mode); // non-default modes are logged as (mode, x, y)
        self.taps.push(if mode == TapMode::Tap { TapLog::At(xy.0, xy.1) } else { TapLog::Mode(mode, xy.0, xy.1) });
        self.trace.push(ev_tap(xy.0, xy.1, mode.as_str(), wait));
        Ok(mode)
    }

    fn tap_seq(&mut self, steps: &[(i64, i64, f64)], _tolerate: bool, _dry: bool) -> Result<SeqOut> {
        self.taps.extend(steps.iter().map(|&(x, y, _)| TapLog::At(x, y)));
        self.trace.push(ev_seq(steps));
        Ok(SeqOut::Done(true))
    }

    fn key_seq(&mut self, steps: &[(i64, f64)], _tolerate: bool, _dry: bool) -> Result<SeqOut> {
        // T97: keyevent BACK on the world view opens the exit confirm
        if steps.iter().any(|&(k, _)| k == 4)
            && let (Some(last), Some(world)) = (self.last.as_ref(), self.world.as_ref())
            && world(last)
        {
            return Err(InfraError::Fail(format!("keyevent BACK on the world view (shots: {:?})", self.shots)));
        }
        for &(k, w) in steps {
            self.taps.push(TapLog::Key(k));
            self.trace.push(ev_key(k, w));
        }
        Ok(SeqOut::Done(true))
    }

    fn tap_hold(&mut self, xy: (i64, i64), ms: i64, wait: f64) -> Result<()> {
        self.taps.push(TapLog::Hold(xy.0, xy.1));
        self.trace.push(ev_hold(xy.0, xy.1, ms, wait));
        Ok(())
    }

    fn swipe(&mut self, from: (i64, i64), to: (i64, i64), millis: i64, wait: f64) -> Result<()> {
        self.taps.push(TapLog::Swipe(from, to, millis, wait));
        self.trace.push(ev_swipe([from.0, from.1, to.0, to.1], millis, wait));
        Ok(())
    }

    fn shot(&mut self, name: &str) -> Result<Frame> {
        self.shots.push(name.to_owned());
        let Some(f) = self.frames.pop_front() else {
            return Err(InfraError::Fail(format!("unscripted shot {name:?} (shots so far: {:?})", self.shots)));
        };
        self.trace.push(ev_shot(name, &f.key()));
        self.last = Some(f.clone());
        Ok(f)
    }
}

/// T97 (live 2026-11-04): taps change nothing; only keyevent 4 advances `screens` by one.
/// Every shot shows the current screen; more than `max_shots` shots fails (unbounded loop).
pub struct DeadTapDevice {
    pub base: FakeDevice,
    pub screens: Vec<Frame>,
    pub pos: usize,
    pub max_shots: usize,
    /// T97b: tap modes that DO advance the screen.
    pub live_modes: Vec<TapMode>,
}

impl DeadTapDevice {
    pub fn new(screens: Vec<Frame>, max_shots: usize, live_modes: Vec<TapMode>) -> Self {
        Self { base: FakeDevice::new(Vec::new()), screens, pos: 0, max_shots, live_modes }
    }

    fn advance(&mut self, n: usize) {
        self.pos = (self.pos + n).min(self.screens.len().saturating_sub(1));
    }
}

impl Device for DeadTapDevice {
    fn tap_state(&mut self) -> &mut TapState {
        self.base.tap_state()
    }
    fn adb(&mut self, args: &[String], t: u64) -> std::result::Result<Output, RunError> {
        self.base.adb(args, t)
    }
    fn shots_dir(&self) -> PathBuf {
        self.base.shots_dir()
    }
    fn print(&mut self, line: &str) {
        self.base.print(line)
    }
    fn trace(&mut self, ev: Value) {
        self.base.trace.push(ev)
    }
    fn sleep(&mut self, s: f64) {
        self.base.sleep(s)
    }
    fn now(&mut self) -> f64 {
        self.base.now()
    }

    fn tap(&mut self, xy: (i64, i64), wait: f64, mode: Option<TapMode>) -> Result<TapMode> {
        let used = self.base.tap(xy, wait, mode)?;
        if self.live_modes.contains(&used) {
            self.advance(1);
        }
        Ok(used)
    }

    fn tap_seq(&mut self, steps: &[(i64, i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        self.base.tap_seq(steps, tolerate, dry)
    }

    fn key_seq(&mut self, steps: &[(i64, f64)], tolerate: bool, dry: bool) -> Result<SeqOut> {
        let out = self.base.key_seq(steps, tolerate, dry)?;
        self.advance(steps.iter().filter(|&&(k, _)| k == 4).count());
        Ok(out)
    }

    fn tap_hold(&mut self, xy: (i64, i64), ms: i64, wait: f64) -> Result<()> {
        self.base.tap_hold(xy, ms, wait)
    }

    fn swipe(&mut self, from: (i64, i64), to: (i64, i64), millis: i64, wait: f64) -> Result<()> {
        self.base.swipe(from, to, millis, wait)
    }

    fn shot(&mut self, name: &str) -> Result<Frame> {
        self.base.shots.push(name.to_owned());
        if self.base.shots.len() > self.max_shots {
            return Err(InfraError::Fail(format!("more than {} shots: {:?}", self.max_shots, self.base.shots)));
        }
        let f = self.screens.get(self.pos).cloned().ok_or_else(|| InfraError::Fail("no screens".into()))?;
        self.base.trace.push(ev_shot(name, &f.key()));
        self.base.last = Some(f.clone());
        Ok(f)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::infra::tap::{tap_result, tap_retry};

    fn solid(v: u8) -> Frame {
        Frame::new(2, 2, vec![v; 12])
    }

    #[test]
    fn fake_device_guards() {
        let mut d = FakeDevice::new(vec![solid(1)]).with_world(Box::new(|f: &Frame| f.rgb[0] == 1));
        d.shot("a").unwrap();
        assert!(matches!(d.shot("b"), Err(InfraError::Fail(m)) if m.contains("unscripted shot")));
        assert!(matches!(d.back(1.5), Err(InfraError::Fail(m)) if m.contains("world view")));
        assert_eq!(d.tap((1, 2), 1.0, None).unwrap(), TapMode::Tap);
        assert_eq!(d.tap((3, 4), 1.0, Some(TapMode::Touchscreen)).unwrap(), TapMode::Touchscreen);
        assert_eq!(d.taps, [TapLog::At(1, 2), TapLog::Mode(TapMode::Touchscreen, 3, 4)]);
    }

    #[test]
    fn dead_tap_device_retry_chain() {
        // T97b: taps dead; touchscreen is live -> retry advances and sticks
        let mut d = DeadTapDevice::new(vec![solid(1), solid(2)], 40, vec![TapMode::Touchscreen]);
        d.tap((5, 5), 1.0, None).unwrap();
        assert_eq!(d.pos, 0);
        let m = tap_retry(&mut d, (5, 5), 1.0).unwrap();
        assert_eq!(m, Some(TapMode::Touchscreen));
        assert_eq!(d.pos, 1);
        tap_result(&mut d, m, true);
        assert_eq!(d.base.state.mode, TapMode::Touchscreen);
        // chain exhausted (sendevent unavailable) -> hold-tap, None
        assert_eq!(tap_retry(&mut d, (5, 5), 1.0).unwrap(), None);
        assert_eq!(d.base.taps.last(), Some(&TapLog::Hold(5, 5)));
    }
}

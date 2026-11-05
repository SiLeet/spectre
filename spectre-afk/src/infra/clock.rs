//! Injected clock: `time.sleep` / `time.time` go through it, so tests and the golden
//! replay run without real waiting (rust-port-plan §E0b virtual clock, §E1 `sleep`/`now`).

use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub trait Clock {
    fn sleep(&mut self, s: f64);
    fn now(&mut self) -> f64;
}

/// The real clock.
#[derive(Debug, Default, Clone, Copy)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn sleep(&mut self, s: f64) {
        if s > 0.0 && s.is_finite() {
            std::thread::sleep(Duration::from_secs_f64(s));
        }
    }

    fn now(&mut self) -> f64 {
        SystemTime::now().duration_since(UNIX_EPOCH).map_or(0.0, |d| d.as_secs_f64())
    }
}

/// Virtual clock: `sleep` advances `t` and is logged; nothing waits.
#[derive(Debug, Default, Clone)]
pub struct FakeClock {
    pub t: f64,
    pub sleeps: Vec<f64>,
}

impl Clock for FakeClock {
    fn sleep(&mut self, s: f64) {
        self.sleeps.push(s);
        self.t += s;
    }

    fn now(&mut self) -> f64 {
        self.t
    }
}

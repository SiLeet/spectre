//! Tap modes (T97b, afk_claim_vision L490-L635): `TAP_CHAIN`, the module state
//! (`TAP_MODE`, `_TAP_DEAD`, `_SENDEVENT`), `parse_getevent`, `sendevent_cmds`,
//! `sendevent_device`, `_tap_cmd`, `tap_retry`, `tap_result`.

use super::adb::DISCOVERY_TIMEOUT;
use super::device::Device;
use super::{InfraError, Result};
use crate::pystr::{decode_replace, fmt_g, splitlines};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum TapMode {
    Tap,
    Touchscreen,
    Sendevent,
}

impl TapMode {
    pub fn as_str(self) -> &'static str {
        match self {
            TapMode::Tap => "tap",
            TapMode::Touchscreen => "touchscreen",
            TapMode::Sendevent => "sendevent",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        TAP_CHAIN.into_iter().find(|m| m.as_str() == s)
    }
}

impl std::fmt::Display for TapMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// `TAP_CHAIN = ('tap', 'touchscreen', 'sendevent')`.
pub const TAP_CHAIN: [TapMode; 3] = [TapMode::Tap, TapMode::Touchscreen, TapMode::Sendevent];

/// `screencap` geometry the tap coordinates refer to (`SCREEN_W`, `SCREEN_H`).
pub const SCREEN_W: i64 = 1920;
pub const SCREEN_H: i64 = 1080;

/// The touch device `getevent -pl` reports (`parse_getevent` dict, plus `root` from discovery).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TouchDev {
    pub path: String,
    pub x: (i64, i64),
    pub y: (i64, i64),
    pub tid: bool,
    pub btn: bool,
    pub slot: bool,
    pub root: bool,
}

impl TouchDev {
    /// Python's dict repr, for the discovery log line.
    pub fn py_repr(&self) -> String {
        let b = |v: bool| if v { "True" } else { "False" };
        format!(
            "{{'path': '{}', 'tid': {}, 'btn': {}, 'slot': {}, 'x': ({}, {}), 'y': ({}, {}), 'root': {}}}",
            self.path, b(self.tid), b(self.btn), b(self.slot), self.x.0, self.x.1, self.y.0, self.y.1, b(self.root)
        )
    }
}

/// `_SENDEVENT`: None (untried), False (unavailable), or the device.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub enum Discovery {
    #[default]
    Untried,
    Unavailable,
    Found(TouchDev),
}

/// The per-process tap state Python keeps in module globals.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TapState {
    /// `TAP_MODE`
    pub mode: TapMode,
    /// `_TAP_DEAD`: modes whose stall retry changed nothing
    pub dead: BTreeSet<TapMode>,
    /// `_SENDEVENT`
    pub sendevent: Discovery,
}

impl Default for TapState {
    fn default() -> Self {
        Self { mode: TapMode::Tap, dead: BTreeSet::new(), sendevent: Discovery::Untried }
    }
}

/// `add device N: <path>` at the line start (`re.match(r'add device \d+: (\S+)', line)`).
fn add_device(line: &str) -> Option<&str> {
    let rest = line.strip_prefix("add device ")?;
    let digits = rest.chars().take_while(|c| c.is_ascii_digit()).count();
    if digits == 0 {
        return None;
    }
    let rest = rest[digits..].strip_prefix(": ")?;
    let end = rest.find(crate::pystr::is_space).unwrap_or(rest.len());
    (end > 0).then(|| &rest[..end])
}

/// `-?\d+` at the start of `s`: (value, bytes consumed).
fn int_prefix(s: &str) -> Option<(i64, usize)> {
    let neg = s.starts_with('-');
    let body = &s[usize::from(neg)..];
    let n = body.bytes().take_while(u8::is_ascii_digit).count();
    if n == 0 {
        return None;
    }
    let v: i64 = body[..n].parse().ok()?;
    Some((if neg { -v } else { v }, n + usize::from(neg)))
}

/// `min (-?\d+), max (-?\d+)` anchored at `s`.
fn min_max(s: &str) -> Option<(i64, i64)> {
    let (lo, n) = int_prefix(s.strip_prefix("min ")?)?;
    let rest = s["min ".len() + n..].strip_prefix(", max ")?;
    let (hi, _) = int_prefix(rest)?;
    Some((lo, hi))
}

/// `re.search(r'ABS_MT_POSITION_([XY])\s*:.*?min (-?\d+), max (-?\d+)', line)`.
fn position(line: &str) -> Option<(char, (i64, i64))> {
    const TAG: &str = "ABS_MT_POSITION_";
    let mut from = 0;
    while let Some(off) = line[from..].find(TAG) {
        let at = from + off + TAG.len();
        from = from + off + 1;
        let axis = match line[at..].chars().next() {
            Some(c @ ('X' | 'Y')) => c,
            _ => continue,
        };
        let after = line[at + 1..].trim_start_matches(crate::pystr::is_space);
        let Some(body) = after.strip_prefix(':') else { continue };
        // lazy `.*?`: the first position from which `min .., max ..` matches
        for (i, _) in body.char_indices().chain(std::iter::once((body.len(), ' '))) {
            if let Some(mm) = min_max(&body[i..]) {
                return Some((axis, mm));
            }
        }
    }
    None
}

/// `parse_getevent(text)`: the first touch device (ABS_MT_POSITION_X and _Y) in
/// `getevent -pl` output, else None. `root` is set by discovery, not here.
pub fn parse_getevent(text: &str) -> Option<TouchDev> {
    struct Cand {
        path: String,
        x: Option<(i64, i64)>,
        y: Option<(i64, i64)>,
        tid: bool,
        btn: bool,
        slot: bool,
    }
    let done = |d: &Cand| -> Option<TouchDev> {
        Some(TouchDev { path: d.path.clone(), x: d.x?, y: d.y?, tid: d.tid, btn: d.btn, slot: d.slot, root: false })
    };
    let mut dev: Option<Cand> = None;
    for line in splitlines(text) {
        if let Some(path) = add_device(line) {
            if let Some(found) = dev.as_ref().and_then(done) {
                return Some(found);
            }
            dev = Some(Cand { path: path.to_owned(), x: None, y: None, tid: false, btn: false, slot: false });
        } else if let Some(d) = dev.as_mut() {
            if let Some((axis, mm)) = position(line) {
                if axis == 'X' { d.x = Some(mm) } else { d.y = Some(mm) }
            }
            d.tid |= line.contains("ABS_MT_TRACKING_ID");
            d.btn |= line.contains("BTN_TOUCH");
            d.slot |= line.contains("ABS_MT_SLOT");
        }
    }
    dev.as_ref().and_then(done)
}

/// `rng[0] + round(c * (rng[1] - rng[0]) / (n - 1))` - true division, banker's rounding.
fn scale(c: i64, n: i64, rng: (i64, i64)) -> i64 {
    rng.0 + ((c * (rng.1 - rng.0)) as f64 / (n - 1) as f64).round_ties_even() as i64
}

/// `sendevent_cmds(dev, x, y, ms)`: a tap (ms != 0: a press of ms) as raw sendevent
/// commands; MT protocol B with ABS_MT_TRACKING_ID, else protocol A (SYN_MT_REPORT).
pub fn sendevent_cmds(dev: &TouchDev, x: i64, y: i64, ms: i64) -> Vec<String> {
    let ev = |typ: i64, code: i64, val: i64| format!("sendevent {} {typ} {code} {val}", dev.path);
    let pos = [ev(3, 53, scale(x, SCREEN_W, dev.x)), ev(3, 54, scale(y, SCREEN_H, dev.y))];
    let btn: Vec<String> = if dev.btn { vec![ev(1, 330, 1)] } else { vec![] };
    let btn_up: Vec<String> = if dev.btn { vec![ev(1, 330, 0)] } else { vec![] };
    let (down, up): (Vec<String>, Vec<String>) = if dev.tid {
        let slot: Vec<String> = if dev.slot { vec![ev(3, 47, 0)] } else { vec![] };
        (
            [slot.clone(), vec![ev(3, 57, 1)], pos.to_vec(), btn, vec![ev(0, 0, 0)]].concat(),
            [slot, vec![ev(3, 57, -1)], btn_up, vec![ev(0, 0, 0)]].concat(),
        )
    } else {
        ([pos.to_vec(), vec![ev(0, 2, 0)], btn, vec![ev(0, 0, 0)]].concat(), [vec![ev(0, 2, 0)], btn_up, vec![ev(0, 0, 0)]].concat())
    };
    let sleep = if ms != 0 { vec![format!("sleep {}", fmt_g(ms as f64 / 1000.0))] } else { vec![] };
    [down, sleep, up].concat()
}

/// `sendevent_device()`: one-time discovery (`getevent -pl` -> touch device, `su -c id` ->
/// root). None = unavailable (logged once): the tap chain stops before 'sendevent'.
pub fn sendevent_device<D: Device + ?Sized>(dev: &mut D) -> Option<TouchDev> {
    if dev.tap_state().sendevent == Discovery::Untried {
        dev.tap_state().sendevent = Discovery::Unavailable;
        if let Err(e) = discover(dev) {
            dev.print(&format!("    sendevent discovery failed: {e}"));
        }
        let desc = match &dev.tap_state().sendevent {
            Discovery::Found(d) => d.py_repr(),
            _ => "unavailable (tap chain stops here)".to_owned(),
        };
        dev.print(&format!("    sendevent device: {desc}"));
    }
    match &dev.tap_state().sendevent {
        Discovery::Found(d) => Some(d.clone()),
        _ => None,
    }
}

fn discover<D: Device + ?Sized>(dev: &mut D) -> std::result::Result<(), InfraError> {
    let p = dev.adb(&["shell".into(), "getevent -pl".into()], DISCOVERY_TIMEOUT)?;
    let found = if p.code == Some(0) { parse_getevent(&decode_replace(&p.stdout)) } else { None };
    if let Some(mut d) = found {
        let q = dev.adb(&["shell".into(), "su -c id".into()], DISCOVERY_TIMEOUT)?;
        d.root = decode_replace(&q.stdout).contains("uid=0");
        dev.tap_state().sendevent = Discovery::Found(d);
    }
    Ok(())
}

/// `_tap_cmd(x, y, ms, mode)`: the ONE place that builds a tap's device command line.
pub fn tap_cmd<D: Device + ?Sized>(dev: &mut D, x: i64, y: i64, ms: i64, mode: Option<TapMode>) -> String {
    let mode = mode.unwrap_or(dev.tap_state().mode);
    if mode == TapMode::Sendevent
        && let Some(d) = dev.sendevent_device()
    {
        let line = sendevent_cmds(&d, x, y, ms).join(" && ");
        return if d.root { format!("su -c \"{line}\"") } else { line };
    }
    let src = if mode == TapMode::Touchscreen { "input touchscreen" } else { "input" };
    if ms != 0 { format!("{src} swipe {x} {y} {x} {y} {ms}") } else { format!("{src} tap {x} {y}") }
}

/// `tap_retry(xy, wait)`: the ONE retry of a tap that left the screen unchanged, in the next
/// chain mode after TAP_MODE not yet dead ('sendevent' only if discovery finds a device).
/// Returns that mode; chain exhausted or the mode raised: hold-tap and None.
pub fn tap_retry<D: Device + ?Sized>(dev: &mut D, xy: (i64, i64), wait: f64) -> Result<Option<TapMode>> {
    let cur = dev.tap_state().mode;
    let start = TAP_CHAIN.iter().position(|&m| m == cur).map_or(TAP_CHAIN.len(), |i| i + 1);
    let mut nxt = None;
    for &m in &TAP_CHAIN[start..] {
        if dev.tap_state().dead.contains(&m) {
            continue;
        }
        if m == TapMode::Sendevent && dev.sendevent_device().is_none() {
            continue;
        }
        nxt = Some(m);
        break;
    }
    let Some(nxt) = nxt else {
        dev.tap_hold(xy, 120, wait)?;
        return Ok(None);
    };
    dev.print(&format!("    tap retry at ({}, {}) via {nxt}", xy.0, xy.1));
    match dev.tap(xy, wait, Some(nxt)) {
        Ok(_) => Ok(Some(nxt)),
        Err(InfraError::Runtime(msg)) => {
            dev.tap_state().dead.insert(nxt);
            dev.print(&format!("    tap mode {nxt} failed: {msg} -> hold-tap"));
            dev.tap_hold(xy, 120, wait)?;
            Ok(None)
        }
        Err(e) => Err(e),
    }
}

/// `tap_result(mode, changed)`: screen changed -> `mode` sticks for the process,
/// else it is dead and the next stall tries the one after.
pub fn tap_result<D: Device + ?Sized>(dev: &mut D, mode: Option<TapMode>, changed: bool) {
    let Some(mode) = mode else { return };
    if changed {
        dev.tap_state().mode = mode;
        dev.print(&format!("    TAP_MODE -> {mode} (taps were dead)"));
    } else {
        dev.tap_state().dead.insert(mode);
        dev.print(&format!("    tap mode {mode}: no effect either"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GETEVENT: &str = "add device 1: /dev/input/event3\n  name: \"keys\"\n  events:\n    KEY (0001): KEY_BACK\n\
add device 2: /dev/input/event2\n  name: \"bst touch\"\n  events:\n    KEY (0001): BTN_TOUCH\n    ABS (0003): ABS_MT_SLOT : value 0, min 0, max 9, fuzz 0\n\
                ABS_MT_TRACKING_ID    : value 0, min 0, max 65535, fuzz 0\n\
                ABS_MT_POSITION_X     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0\n\
                ABS_MT_POSITION_Y     : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0\n";

    #[test]
    fn parse_getevent_first_touch_device() {
        let d = parse_getevent(GETEVENT).unwrap();
        assert_eq!(d.path, "/dev/input/event2");
        assert_eq!((d.x, d.y, d.tid, d.btn, d.slot), ((0, 32767), (0, 32767), true, true, true));
        assert_eq!(parse_getevent("add device 1: /dev/input/event3\n  KEY_BACK\n"), None);
        assert_eq!(position("ABS_MT_POSITION_X:junk min -5, max 7"), Some(('X', (-5, 7))));
        assert_eq!(position("ABS_MT_POSITION_Z : min 1, max 2"), None);
    }

    #[test]
    fn sendevent_protocols_and_scaling() {
        let mut d = parse_getevent(GETEVENT).unwrap();
        let b = sendevent_cmds(&d, 1919, 0, 0);
        assert_eq!(b[0], "sendevent /dev/input/event2 3 47 0");
        assert_eq!(b[2], "sendevent /dev/input/event2 3 53 32767");
        d.tid = false;
        let a = sendevent_cmds(&d, 960, 540, 120);
        // round(960 * 32767 / 1919) = round(16391.54..) = 16392; 540 * 32767 / 1079 = 16398.6..
        assert_eq!(a[0], "sendevent /dev/input/event2 3 53 16392");
        assert_eq!(a[1], "sendevent /dev/input/event2 3 54 16399");
        assert!(a.contains(&"sleep 0.12".to_owned()));
        assert_eq!(scale(1, 3, (0, 3)), 2); // round(1.5) -> 2 (ties to even)
        assert_eq!(scale(1, 5, (0, 2)), 0); // round(0.5) -> 0
    }
}

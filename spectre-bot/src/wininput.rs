//! Native Windows input backend — simulates mouse and keyboard via `SendInput`.
//!
//! No external Windows crates: the handful of `user32` entry points and
//! structures needed are declared here via `unsafe extern "system"`.
//!
//! # Coordinate model
//!
//! Mouse positions are injected with `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE`,
//! i.e. pixel coordinates on the **primary monitor** are normalized to the
//! `0..=65535` range that `SendInput` expects (see [`normalize_coord`]).
//! The screen size is queried via `GetSystemMetrics` on every call, so
//! resolution changes at runtime are picked up. A move and the button events
//! that follow it are submitted in a single `SendInput` call, so they cannot be
//! interleaved with other input streams.
//!
//! If the calling process is not DPI-aware, Windows virtualizes both the
//! reported screen size and the injected coordinates consistently, so pixel
//! coordinates in the (scaled) logical space still land where expected.
//!
//! # Blocking
//!
//! [`InputSimulator`] is a synchronous trait. `tap_hold` and `swipe` sleep on
//! the calling thread for the requested duration.

#[allow(clippy::upper_case_acronyms)] // Win32 type names (INPUT, MOUSEINPUT, ...) use ALL_CAPS by convention.
mod ffi {
    #[repr(C)]
    #[derive(Debug, Clone, Copy)]
    #[allow(non_snake_case)]
    pub struct MOUSEINPUT {
        pub dx: i32,
        pub dy: i32,
        pub mouseData: u32,
        pub dwFlags: u32,
        pub time: u32,
        pub dwExtraInfo: usize,
    }

    #[repr(C)]
    #[derive(Debug, Clone, Copy)]
    #[allow(non_snake_case)]
    pub struct KEYBDINPUT {
        pub wVk: u16,
        pub wScan: u16,
        pub dwFlags: u32,
        pub time: u32,
        pub dwExtraInfo: usize,
    }

    /// Payload union of `INPUT`. `HARDWAREINPUT` (8 bytes) is omitted: it is
    /// never used and `MOUSEINPUT` is the largest member, so the union size
    /// and alignment match the Win32 definition without it.
    #[repr(C)]
    #[derive(Clone, Copy)]
    pub union INPUT_0 {
        pub mi: MOUSEINPUT,
        pub ki: KEYBDINPUT,
    }

    #[repr(C)]
    #[derive(Clone, Copy)]
    #[allow(non_snake_case)]
    pub struct INPUT {
        pub r#type: u32,
        pub Anonymous: INPUT_0,
    }

    pub const INPUT_MOUSE: u32 = 0;
    pub const INPUT_KEYBOARD: u32 = 1;

    pub const MOUSEEVENTF_MOVE: u32 = 0x0001;
    pub const MOUSEEVENTF_LEFTDOWN: u32 = 0x0002;
    pub const MOUSEEVENTF_LEFTUP: u32 = 0x0004;
    pub const MOUSEEVENTF_WHEEL: u32 = 0x0800;
    pub const MOUSEEVENTF_ABSOLUTE: u32 = 0x8000;

    pub const KEYEVENTF_EXTENDEDKEY: u32 = 0x0001;
    pub const KEYEVENTF_KEYUP: u32 = 0x0002;

    pub const SM_CXSCREEN: i32 = 0;
    pub const SM_CYSCREEN: i32 = 1;

    #[link(name = "user32")]
    unsafe extern "system" {
        pub fn SendInput(cInputs: u32, pInputs: *const INPUT, cbSize: i32) -> u32;
        pub fn GetSystemMetrics(nIndex: i32) -> i32;
    }
}

use std::thread;
use std::time::Duration;

use anyhow::{Context, bail};
use ffi::{INPUT, INPUT_0, KEYBDINPUT, MOUSEINPUT};

use crate::engine::InputSimulator;

/// Interval between intermediate mouse moves during a swipe.
const SWIPE_STEP_MILLIS: u64 = 10;
/// Upper bound on intermediate swipe steps (keeps very long swipes cheap).
const SWIPE_MAX_STEPS: u64 = 500;

// ── Pure helpers ────────────────────────────────────────────────────────────

/// Normalize a pixel coordinate to the `0..=65535` absolute range used by
/// `SendInput` with `MOUSEEVENTF_ABSOLUTE`.
///
/// `extent` is the screen size along that axis in pixels. Pixel `0` maps to
/// `0` and pixel `extent - 1` maps to `65535`; coordinates beyond the screen
/// are clamped to the last pixel. Returns `Err` for a non-positive extent.
pub fn normalize_coord(pixel: u32, extent: i32) -> anyhow::Result<i32> {
    if extent <= 0 {
        bail!("invalid screen extent {}", extent);
    }
    let max_pixel = (extent - 1) as u64;
    if max_pixel == 0 {
        return Ok(0);
    }
    let pixel = (pixel as u64).min(max_pixel);
    // Round to nearest instead of truncating.
    Ok(((pixel * 65535 + max_pixel / 2) / max_pixel) as i32)
}

/// Map a key name to its Win32 virtual-key code.
///
/// Matching is case-insensitive. Supported names: `"A"`..`"Z"`,
/// `"0"`..`"9"`, `ENTER`/`RETURN`, `ESC`/`ESCAPE`, `TAB`, `SPACE`,
/// `BACKSPACE`, and the arrow keys `UP`/`DOWN`/`LEFT`/`RIGHT`.
/// Unknown names return `Err`.
pub fn vk_code(key: &str) -> anyhow::Result<u16> {
    let upper = key.trim().to_ascii_uppercase();
    let vk = match upper.as_str() {
        "ENTER" | "RETURN" => 0x0D,
        "ESC" | "ESCAPE" => 0x1B,
        "TAB" => 0x09,
        "SPACE" => 0x20,
        "BACKSPACE" => 0x08,
        "LEFT" => 0x25,
        "UP" => 0x26,
        "RIGHT" => 0x27,
        "DOWN" => 0x28,
        // Letters and digits: the VK code equals the uppercase ASCII value.
        s if s.len() == 1 && s.as_bytes()[0].is_ascii_alphanumeric() => s.as_bytes()[0] as u16,
        _ => bail!("unknown key name '{}'", key),
    };
    Ok(vk)
}

/// Arrow keys sit on the extended part of the keyboard; without the extended
/// flag they would be interpreted as numpad keys.
fn is_extended(vk: u16) -> bool {
    (0x25..=0x28).contains(&vk)
}

fn mouse_input(dx: i32, dy: i32, mouse_data: u32, flags: u32) -> INPUT {
    INPUT {
        r#type: ffi::INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT {
                dx,
                dy,
                mouseData: mouse_data,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

fn key_input(vk: u16, flags: u32) -> INPUT {
    INPUT {
        r#type: ffi::INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: flags,
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

fn button_input(flags: u32) -> INPUT {
    mouse_input(0, 0, 0, flags)
}

// ── Backend ─────────────────────────────────────────────────────────────────

/// Native Windows [`InputSimulator`] backed by `user32!SendInput`.
///
/// Stateless: the screen size is queried on every call.
#[derive(Debug, Default, Clone, Copy)]
pub struct WindowsInput;

impl WindowsInput {
    /// Create a new Windows input backend.
    pub fn new() -> WindowsInput {
        WindowsInput
    }

    /// Primary screen size in pixels.
    fn screen_size() -> anyhow::Result<(i32, i32)> {
        // SAFETY: GetSystemMetrics takes a plain integer and has no preconditions.
        let (w, h) = unsafe {
            (
                ffi::GetSystemMetrics(ffi::SM_CXSCREEN),
                ffi::GetSystemMetrics(ffi::SM_CYSCREEN),
            )
        };
        if w <= 0 || h <= 0 {
            bail!("GetSystemMetrics returned invalid screen size {}x{}", w, h);
        }
        Ok((w, h))
    }

    /// Build an absolute mouse-move event for pixel (x, y).
    fn move_to(x: u32, y: u32, screen: (i32, i32)) -> anyhow::Result<INPUT> {
        let dx = normalize_coord(x, screen.0).context("normalizing x")?;
        let dy = normalize_coord(y, screen.1).context("normalizing y")?;
        Ok(mouse_input(
            dx,
            dy,
            0,
            ffi::MOUSEEVENTF_MOVE | ffi::MOUSEEVENTF_ABSOLUTE,
        ))
    }

    /// Submit events via `SendInput`, failing if not all were inserted
    /// (e.g. input blocked by UIPI or another thread).
    fn send(inputs: &[INPUT]) -> anyhow::Result<()> {
        if inputs.is_empty() {
            return Ok(());
        }
        // SAFETY: `inputs` is a valid, initialized slice of `INPUT` structs whose
        // layout matches the Win32 definition; cbSize is the size of one element.
        let inserted = unsafe {
            ffi::SendInput(
                inputs.len() as u32,
                inputs.as_ptr(),
                std::mem::size_of::<INPUT>() as i32,
            )
        };
        if (inserted as usize) < inputs.len() {
            bail!(
                "SendInput inserted {}/{} events: {}",
                inserted,
                inputs.len(),
                std::io::Error::last_os_error()
            );
        }
        Ok(())
    }
}

impl InputSimulator for WindowsInput {
    fn click(&self, x: u32, y: u32) -> anyhow::Result<()> {
        tracing::debug!("wininput click at ({}, {})", x, y);
        let screen = Self::screen_size()?;
        Self::send(&[
            Self::move_to(x, y, screen)?,
            button_input(ffi::MOUSEEVENTF_LEFTDOWN),
            button_input(ffi::MOUSEEVENTF_LEFTUP),
        ])
    }

    fn tap_hold(&self, x: u32, y: u32, millis: u64) -> anyhow::Result<()> {
        tracing::debug!("wininput tap_hold at ({}, {}) for {}ms", x, y, millis);
        let screen = Self::screen_size()?;
        Self::send(&[
            Self::move_to(x, y, screen)?,
            button_input(ffi::MOUSEEVENTF_LEFTDOWN),
        ])?;
        thread::sleep(Duration::from_millis(millis));
        Self::send(&[button_input(ffi::MOUSEEVENTF_LEFTUP)])
    }

    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, millis: u64) -> anyhow::Result<()> {
        tracing::debug!(
            "wininput swipe ({}, {}) → ({}, {}) in {}ms",
            x1,
            y1,
            x2,
            y2,
            millis
        );
        let screen = Self::screen_size()?;
        Self::send(&[
            Self::move_to(x1, y1, screen)?,
            button_input(ffi::MOUSEEVENTF_LEFTDOWN),
        ])?;

        let steps = (millis / SWIPE_STEP_MILLIS).clamp(1, SWIPE_MAX_STEPS);
        let pause = Duration::from_millis(millis / steps);
        let moved = (1..=steps).try_for_each(|i| {
            let t = i as f64 / steps as f64;
            let x = (x1 as f64 + (x2 as f64 - x1 as f64) * t).round() as u32;
            let y = (y1 as f64 + (y2 as f64 - y1 as f64) * t).round() as u32;
            thread::sleep(pause);
            Self::send(&[Self::move_to(x, y, screen)?])
        });

        // Always release the button, even if an intermediate move failed.
        let released = Self::send(&[button_input(ffi::MOUSEEVENTF_LEFTUP)]);
        moved.and(released)
    }

    fn scroll(&self, delta: i32) -> anyhow::Result<()> {
        tracing::debug!("wininput scroll {}", delta);
        // mouseData is a DWORD but carries a signed wheel delta.
        Self::send(&[mouse_input(0, 0, delta as u32, ffi::MOUSEEVENTF_WHEEL)])
    }

    fn key(&self, key: &str) -> anyhow::Result<()> {
        let vk = vk_code(key)?;
        tracing::debug!("wininput key '{}' (vk 0x{:02X})", key, vk);
        let ext = if is_extended(vk) {
            ffi::KEYEVENTF_EXTENDEDKEY
        } else {
            0
        };
        Self::send(&[
            key_input(vk, ext),
            key_input(vk, ext | ffi::KEYEVENTF_KEYUP),
        ])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // NOTE: none of these tests call SendInput — no real input is generated.

    #[test]
    fn input_struct_layout_matches_win32() {
        #[cfg(target_pointer_width = "64")]
        {
            assert_eq!(std::mem::size_of::<MOUSEINPUT>(), 32);
            assert_eq!(std::mem::size_of::<KEYBDINPUT>(), 24);
            assert_eq!(std::mem::size_of::<INPUT>(), 40);
            assert_eq!(std::mem::align_of::<INPUT>(), 8);
        }
        #[cfg(target_pointer_width = "32")]
        {
            assert_eq!(std::mem::size_of::<INPUT>(), 28);
        }
    }

    #[test]
    fn normalize_maps_edges() {
        assert_eq!(normalize_coord(0, 1920).unwrap(), 0);
        assert_eq!(normalize_coord(1919, 1920).unwrap(), 65535);
        assert_eq!(normalize_coord(1079, 1080).unwrap(), 65535);
    }

    #[test]
    fn normalize_midpoint_and_clamp() {
        // 1920 px → max_pixel 1919; pixel 960 ≈ 50 %.
        let mid = normalize_coord(960, 1920).unwrap();
        assert!((32768 - 20..=32768 + 20).contains(&mid), "mid = {}", mid);
        assert_eq!(normalize_coord(5000, 1920).unwrap(), 65535);
        assert_eq!(normalize_coord(7, 1).unwrap(), 0);
    }

    #[test]
    fn normalize_rejects_bad_extent() {
        assert!(normalize_coord(0, 0).is_err());
        assert!(normalize_coord(0, -5).is_err());
    }

    #[test]
    fn key_names_map_to_vk_codes() {
        assert_eq!(vk_code("A").unwrap(), 0x41);
        assert_eq!(vk_code("z").unwrap(), 0x5A);
        assert_eq!(vk_code("0").unwrap(), 0x30);
        assert_eq!(vk_code("9").unwrap(), 0x39);
        assert_eq!(vk_code("ENTER").unwrap(), 0x0D);
        assert_eq!(vk_code("enter").unwrap(), 0x0D);
        assert_eq!(vk_code("ESC").unwrap(), 0x1B);
        assert_eq!(vk_code("escape").unwrap(), 0x1B);
        assert_eq!(vk_code("TAB").unwrap(), 0x09);
        assert_eq!(vk_code("SPACE").unwrap(), 0x20);
        assert_eq!(vk_code("BACKSPACE").unwrap(), 0x08);
        assert_eq!(vk_code("LEFT").unwrap(), 0x25);
        assert_eq!(vk_code("UP").unwrap(), 0x26);
        assert_eq!(vk_code("RIGHT").unwrap(), 0x27);
        assert_eq!(vk_code("DOWN").unwrap(), 0x28);
    }

    #[test]
    fn unknown_key_is_error() {
        for bad in ["", "F13", "AB", "ä", "?", "CTRL"] {
            assert!(vk_code(bad).is_err(), "'{}' should be rejected", bad);
        }
    }

    #[test]
    fn arrows_are_extended_keys() {
        assert!(is_extended(vk_code("UP").unwrap()));
        assert!(!is_extended(vk_code("A").unwrap()));
        assert!(!is_extended(vk_code("ENTER").unwrap()));
    }

    #[test]
    fn move_event_is_absolute() {
        let ev = WindowsInput::move_to(1919, 0, (1920, 1080)).unwrap();
        assert_eq!(ev.r#type, ffi::INPUT_MOUSE);
        // SAFETY: built by `mouse_input`, so `mi` is the active field.
        let mi = unsafe { ev.Anonymous.mi };
        assert_eq!(
            mi.dwFlags,
            ffi::MOUSEEVENTF_MOVE | ffi::MOUSEEVENTF_ABSOLUTE
        );
        assert_eq!((mi.dx, mi.dy), (65535, 0));
    }

    #[test]
    fn send_empty_is_noop() {
        assert!(WindowsInput::send(&[]).is_ok());
    }

    #[test]
    fn constructible_and_send_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<WindowsInput>();
        let _boxed: Box<dyn InputSimulator> = Box::new(WindowsInput::new());
    }
}

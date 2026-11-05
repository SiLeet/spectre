//! `_raw_to_image` and `shot` (afk_claim_vision L694-L734): raw `exec-out screencap`
//! (T76 fast path), `screencap -p` fallback, persisted as `TMP/<name>.png`.

use super::adb::SCREENCAP_TIMEOUT;
use super::device::Device;
use super::trace::ev_shot;
use super::{InfraError, Result};
use crate::img::{Frame, load_rgb, save_png};
use std::io::Write;

/// `RAW_HEADERS = (12, 16)`: w, h, format (+ colorspace on Android 9+).
pub const RAW_HEADERS: [i128; 2] = [12, 16];

/// `_raw_to_image(data)`: RGB frame, or None unless the size is exactly w*h*4 + a known
/// header, the format is RGBA_8888 (1) and 0 < w, h <= 8192. RGBA -> RGB drops alpha (PIL).
pub fn raw_to_frame(data: &[u8]) -> Option<Frame> {
    if data.len() < 16 {
        return None;
    }
    let le = |i: usize| u32::from_le_bytes([data[i], data[i + 1], data[i + 2], data[i + 3]]);
    let (w, h, fmt) = (le(0), le(4), le(8));
    let hdr = data.len() as i128 - i128::from(w) * i128::from(h) * 4;
    if fmt != 1 || !RAW_HEADERS.contains(&hdr) || !(1..=8192).contains(&w) || !(1..=8192).contains(&h) {
        return None;
    }
    let px = &data[hdr as usize..];
    let rgb = px.as_chunks::<4>().0.iter().flat_map(|p| [p[0], p[1], p[2]]).collect();
    Some(Frame::new(w, h, rgb))
}

/// `shot(name)`: raw screencap first; anything unexpected -> `screencap -p` into the file.
pub fn shot<D: Device + ?Sized>(dev: &mut D, name: &str) -> Result<Frame> {
    let dir = dev.shots_dir();
    std::fs::create_dir_all(&dir).map_err(|e| InfraError::Os(e.to_string()))?;
    let path = dir.join(format!("{name}.png"));
    let raw = match dev.exec(&["exec-out".into(), "screencap".into()], SCREENCAP_TIMEOUT) {
        Ok(p) if p.code == Some(0) => raw_to_frame(&p.stdout),
        _ => None,
    };
    if let Some(frame) = raw {
        save_png(&frame, &path)?;
        dev.trace(ev_shot(name, &frame.key()));
        return Ok(frame);
    }
    // Python opens the file before the call: it exists (maybe empty) even if adb fails
    let mut fh = std::fs::File::create(&path).map_err(|e| InfraError::Os(e.to_string()))?;
    let p = dev.exec(&["exec-out".into(), "screencap".into(), "-p".into()], SCREENCAP_TIMEOUT)?;
    fh.write_all(&p.stdout).and_then(|_| fh.flush()).map_err(|e| InfraError::Os(e.to_string()))?;
    drop(fh);
    if p.code != Some(0) {
        return Err(InfraError::Runtime("screencap failed".into()));
    }
    let frame = load_rgb(&path)?;
    dev.trace(ev_shot(name, &frame.key()));
    Ok(frame)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn raw(w: u32, h: u32, header: usize, fmt: u32) -> Vec<u8> {
        let mut v = [w.to_le_bytes(), h.to_le_bytes(), fmt.to_le_bytes()].concat();
        v.resize(header, 0);
        for _ in 0..w * h {
            v.extend([10, 20, 30, 255]);
        }
        v
    }

    #[test]
    fn raw_to_frame_bounds_like_python() {
        for header in [12, 16] {
            let f = raw_to_frame(&raw(4, 3, header, 1)).unwrap();
            assert_eq!((f.w, f.h, f.pixel(0, 0)), (4, 3, [10, 20, 30]));
        }
        let ok = raw(4, 3, 16, 1);
        assert!(raw_to_frame(&ok[..ok.len() - 1]).is_none()); // truncated
        assert!(raw_to_frame(&raw(4, 3, 20, 1)).is_none()); // unknown header
        assert!(raw_to_frame(&raw(4, 3, 16, 5)).is_none()); // not RGBA_8888
        assert!(raw_to_frame(b"\x89PNG...").is_none()); // < 16 bytes
        assert!(raw_to_frame(&raw(0, 3, 16, 1)).is_none()); // w == 0
        let mut big = [8193u32.to_le_bytes(), 1u32.to_le_bytes(), 1u32.to_le_bytes()].concat();
        big.resize(16 + 8193 * 4, 0);
        assert!(raw_to_frame(&big).is_none()); // w > 8192
        let mut huge = [u32::MAX.to_le_bytes(), u32::MAX.to_le_bytes(), 1u32.to_le_bytes()].concat();
        huge.resize(16, 0);
        assert!(raw_to_frame(&huge).is_none()); // negative header, no overflow
    }
}

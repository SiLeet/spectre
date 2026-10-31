//! `spectre search <pid> <type> --min A --max B` — numeric range search.
//!
//! For values the game only shows rounded ("259K"): every aligned slot of
//! the value's width is decoded and kept when it lies in `[min..=max]`.
//! `--continue` applies the same check to the previous address set.

use anyhow::{Result, anyhow, bail};
use tracing::{debug, info};

use spectre_core::{MemoryReader, ValueType};

use crate::hunt::read_slot;
use crate::{
    SearchArgs, create_reader, fmt_addr, load_search_state, parse_search_type, parse_strict_u64,
    save_search_state, search_state_path,
};

/// Bytes pulled per read (same as the scanner's default batch size).
const BATCH: u64 = 1024 * 1024;

/// Inclusive bounds; i128 holds every u64 and i64 value exactly.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Bounds {
    Int(i128, i128),
    Float(f64, f64),
}

/// A parsed `--min/--max` request.
#[derive(Debug)]
pub(crate) struct SearchRange {
    value_type: ValueType,
    bounds: Bounds,
}

fn is_signed(vt: ValueType) -> bool {
    matches!(
        vt,
        ValueType::I8 | ValueType::I16 | ValueType::I32 | ValueType::I64
    )
}

/// Parse `type` + `--min` + `--max` into a range.
pub(crate) fn parse_search_range(type_name: &str, min: &str, max: &str) -> Result<SearchRange> {
    if type_name.eq_ignore_ascii_case("string") {
        bail!("--min/--max need a numeric type (u8..u64, i8..i64, f32, f64), not string");
    }
    let vt = parse_search_type(type_name)?;
    let bounds = match vt {
        ValueType::F32 | ValueType::F64 => {
            let parse = |s: &str, flag: &str| -> Result<f64> {
                let f: f64 = s
                    .trim()
                    .parse()
                    .map_err(|_| anyhow!("invalid {flag} value '{s}' for {type_name}"))?;
                if f.is_nan() {
                    bail!("{flag} must not be NaN");
                }
                // Round f32 bounds to f32 so `--max 1.2` includes a stored 1.2f32.
                Ok(if vt == ValueType::F32 {
                    f64::from(f as f32)
                } else {
                    f
                })
            };
            Bounds::Float(parse(min, "--min")?, parse(max, "--max")?)
        }
        _ => {
            let bits = 8 * vt.size();
            let (lo, hi) = if is_signed(vt) {
                (-(1i128 << (bits - 1)), (1i128 << (bits - 1)) - 1)
            } else {
                (0, (1i128 << bits) - 1)
            };
            let parse = |s: &str, flag: &str| -> Result<i128> {
                let v = s
                    .trim()
                    .parse::<i128>()
                    .ok()
                    .or_else(|| parse_strict_u64(s).map(i128::from))
                    .ok_or_else(|| anyhow!("invalid {flag} value '{s}' for {type_name}"))?;
                if !(lo..=hi).contains(&v) {
                    bail!("{flag} {v} is out of range for {type_name} ({lo}..={hi})");
                }
                Ok(v)
            };
            Bounds::Int(parse(min, "--min")?, parse(max, "--max")?)
        }
    };
    let ordered = match bounds {
        Bounds::Int(a, b) => a <= b,
        Bounds::Float(a, b) => a <= b,
    };
    if !ordered {
        bail!("--min ({min}) must be <= --max ({max})");
    }
    Ok(SearchRange {
        value_type: vt,
        bounds,
    })
}

impl SearchRange {
    fn width(&self) -> usize {
        self.value_type.size() as usize
    }

    /// Decode one little-endian slot of `width()` bytes and test it.
    fn contains(&self, slot: &[u8]) -> bool {
        let w = slot.len();
        let raw = read_slot(slot, 0, w);
        match self.bounds {
            Bounds::Int(lo, hi) => {
                let v = if is_signed(self.value_type) {
                    let shift = 64 - 8 * w as u32;
                    i128::from(((raw << shift) as i64) >> shift)
                } else {
                    i128::from(raw)
                };
                (lo..=hi).contains(&v)
            }
            Bounds::Float(lo, hi) => {
                let v = if w == 4 {
                    f64::from(f32::from_bits(raw as u32))
                } else {
                    f64::from_bits(raw)
                };
                // NaN compares false against both bounds, so it never matches.
                (lo..=hi).contains(&v)
            }
        }
    }
}

/// Scan every readable+writable region at the value's natural alignment.
///
/// Like the scanner, a failed read skips the rest of that region instead of
/// failing the search.
fn scan_range(
    reader: &dyn MemoryReader,
    pid: u32,
    range: &SearchRange,
    limit: u32,
    batch: u64,
) -> Result<Vec<u64>> {
    let w = range.width() as u64;
    // Batches stay multiples of the width so slots never straddle two reads.
    let batch = batch.max(w) / w * w;
    let mut found = Vec::new();
    for region in reader.memory_regions(pid)? {
        let perms = region.perms.to_lowercase();
        if !(perms.contains('r') && perms.contains('w')) {
            continue;
        }
        let Some(mut pos) = region.start.checked_next_multiple_of(w) else {
            continue;
        };
        while region.end.saturating_sub(pos) >= w {
            let len = (region.end - pos).min(batch);
            let chunk = match reader.read_bytes(pid, pos, len as u32) {
                Ok(c) => c,
                Err(e) => {
                    debug!("skip rest of region after failed read at {pos:#x}: {e}");
                    break;
                }
            };
            for (i, slot) in chunk.chunks_exact(w as usize).enumerate() {
                if range.contains(slot) {
                    found.push(pos + i as u64 * w);
                    if limit > 0 && found.len() >= limit as usize {
                        return Ok(found);
                    }
                }
            }
            pos += len;
        }
    }
    Ok(found)
}

/// Keep the previous addresses whose current value is in range; unreadable
/// addresses are dropped.
fn refine_range(
    reader: &dyn MemoryReader,
    pid: u32,
    range: &SearchRange,
    prev: &[u64],
    limit: u32,
) -> Vec<u64> {
    let mut kept = Vec::new();
    for &addr in prev {
        let hit = reader
            .read_bytes(pid, addr, range.value_type.size())
            .map(|b| b.len() == range.width() && range.contains(&b))
            .unwrap_or(false);
        if hit {
            kept.push(addr);
            if limit > 0 && kept.len() >= limit as usize {
                break;
            }
        }
    }
    kept
}

/// `run_search` for the `--min/--max` mode.
pub(crate) fn run_search_range(args: SearchArgs) -> Result<()> {
    let (Some(min), Some(max)) = (args.min.as_deref(), args.max.as_deref()) else {
        bail!("--min and --max must be given together");
    };
    let range = parse_search_range(&args.value_type, min, max)?;
    let state_path = search_state_path(&args.state);
    let pid = args
        .pid
        .ok_or_else(|| anyhow!("pid is required (also with --continue, to re-read the process)"))?;

    let found = if args.continue_search {
        let prev = load_search_state(&state_path)?;
        info!("refining {} candidate(s) to [{min}..{max}]...", prev.len());
        if prev.is_empty() {
            println!("no previous results to refine");
            return Ok(());
        }
        let reader = create_reader(args.adb, None, None)?;
        refine_range(reader.as_ref(), pid, &range, &prev, args.limit)
    } else {
        let reader = create_reader(args.adb, None, None)?;
        info!(
            "searching pid {pid} for {} in [{min}..{max}]...",
            args.value_type.to_lowercase()
        );
        scan_range(reader.as_ref(), pid, &range, args.limit, BATCH)?
    };

    save_search_state(&state_path, &found)?;
    for a in &found {
        println!("{}", fmt_addr(*a));
    }
    println!("-- {} result(s), saved to {state_path}", found.len());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use spectre_core::{
        BackendKind, DumpFileReader, MemoryRegion, ProcessInfo, ScanPattern, ScanReport,
    };
    use structopt::StructOpt;

    const BASE: u64 = 0x10_0000;

    fn u32_dump(values: &[u32]) -> DumpFileReader {
        let data = values.iter().flat_map(|v| v.to_le_bytes()).collect();
        DumpFileReader::from_bytes(BASE, data, "fake")
    }

    #[test]
    fn parses_integer_ranges() {
        let r = parse_search_range("u32", "259000", "0x3F6FF").unwrap();
        assert_eq!(r.bounds, Bounds::Int(259000, 259839));
        let r = parse_search_range("I32", "-5", "5").unwrap();
        assert_eq!(r.bounds, Bounds::Int(-5, 5));
        let r = parse_search_range("u64", "0", "18446744073709551615").unwrap();
        assert_eq!(r.bounds, Bounds::Int(0, u64::MAX as i128));
    }

    #[test]
    fn parses_float_ranges() {
        let r = parse_search_range("f32", "-1.5", "99.5").unwrap();
        assert_eq!(r.bounds, Bounds::Float(-1.5, 99.5));
        assert!(parse_search_range("f64", "NaN", "1").is_err());
        assert!(parse_search_range("f32", "abc", "1").is_err());
    }

    #[test]
    fn rejects_bad_ranges() {
        assert!(parse_search_range("u32", "10", "5").is_err(), "min > max");
        assert!(parse_search_range("f32", "2", "1").is_err(), "min > max");
        assert!(parse_search_range("string", "1", "2").is_err());
        assert!(parse_search_range("strange", "1", "2").is_err());
        assert!(
            parse_search_range("u32", "-1", "5").is_err(),
            "negative unsigned"
        );
        assert!(
            parse_search_range("u8", "0", "256").is_err(),
            "too wide for u8"
        );
        assert!(
            parse_search_range("i8", "-129", "0").is_err(),
            "too wide for i8"
        );
        assert!(
            parse_search_range("u32", "abc", "5").is_err(),
            "bare hex rejected"
        );
    }

    #[test]
    fn args_accept_value_or_min_and_max() {
        let parse = |a: &[&str]| SearchArgs::from_iter_safe(a);
        let a = parse(&["search", "1", "i32", "--min=-5", "--max", "5"]).unwrap();
        assert_eq!(
            (a.min.as_deref(), a.max.as_deref(), a.value),
            (Some("-5"), Some("5"), None)
        );
        let a = parse(&["search", "1", "i32", "--min", "-5", "--max", "-1"]).unwrap();
        assert_eq!(a.min.as_deref(), Some("-5"));
        assert_eq!(
            parse(&["search", "1", "u32", "42"])
                .unwrap()
                .value
                .as_deref(),
            Some("42")
        );
        assert!(parse(&["search", "1", "u32", "42", "--min", "1", "--max", "2"]).is_err());
        assert!(parse(&["search", "1", "u32", "--min", "1"]).is_err());
        assert!(parse(&["search", "1", "u32"]).is_err());
    }

    #[test]
    fn scan_finds_rounded_value_across_batches() {
        let reader = u32_dump(&[258_999, 259_000, 7, 259_850, 260_000, 259_999, 0]);
        let r = parse_search_range("u32", "259000", "259999").unwrap();
        let want = vec![BASE + 4, BASE + 12, BASE + 20];
        // Batch of 8 bytes: matches sit in different reads.
        assert_eq!(scan_range(&reader, 0, &r, 0, 8).unwrap(), want);
        assert_eq!(scan_range(&reader, 0, &r, 0, BATCH).unwrap(), want);
        assert_eq!(scan_range(&reader, 0, &r, 2, 8).unwrap(), want[..2]);
    }

    #[test]
    fn scan_uses_value_alignment_and_sign() {
        // i16 values -3, 2, 100 at offsets 0, 2, 4.
        let data: Vec<u8> = [-3i16, 2, 100]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        let reader = DumpFileReader::from_bytes(BASE, data, "fake");
        let r = parse_search_range("i16", "-5", "5").unwrap();
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE, BASE + 2]
        );
        // Same bytes as u16: -3 is 65533 and falls outside [0..5].
        let r = parse_search_range("u16", "0", "5").unwrap();
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE + 2]
        );
    }

    #[test]
    fn scan_decodes_unsigned_high_values() {
        // -3i16 read as u16 is 65533: only an unsigned decode hits this range.
        let reader = DumpFileReader::from_bytes(BASE, (-3i16).to_le_bytes().to_vec(), "fake");
        let r = parse_search_range("u16", "65530", "65535").unwrap();
        assert_eq!(scan_range(&reader, 0, &r, 0, BATCH).unwrap(), vec![BASE]);
        let reader = u32_dump(&[1, 0x8000_0005]);
        let r = parse_search_range("u32", "0x80000000", "0xFFFFFFFF").unwrap();
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE + 4]
        );
        let data = [1u64, u64::MAX - 1]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        let reader = DumpFileReader::from_bytes(BASE, data, "fake");
        let r = parse_search_range("u64", "9223372036854775808", "18446744073709551615").unwrap();
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE + 8]
        );
    }

    #[test]
    fn f32_bounds_match_stored_f32_values() {
        let data: Vec<u8> = [1.2f32, 1.3, 0.2, 0.7]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        let reader = DumpFileReader::from_bytes(BASE, data, "fake");
        let hits = |min, max| {
            let r = parse_search_range("f32", min, max).unwrap();
            scan_range(&reader, 0, &r, 0, BATCH).unwrap()
        };
        assert_eq!(hits("1.0", "1.2"), vec![BASE]);
        assert_eq!(hits("1.3", "2"), vec![BASE + 4]);
        assert_eq!(hits("1.2", "1.2"), vec![BASE]);
        assert_eq!(hits("0.1", "0.2"), vec![BASE + 8]);
        assert_eq!(hits("0.7", "0.7"), vec![BASE + 12]);
        // f64 keeps the typed bound exactly.
        let r = parse_search_range("f64", "0.1", "0.2").unwrap();
        assert_eq!(r.bounds, Bounds::Float(0.1, 0.2));
    }

    #[test]
    fn float_scan_never_matches_nan() {
        let data: Vec<u8> = [f32::NAN, 1.5, f32::INFINITY, -0.5]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        let reader = DumpFileReader::from_bytes(BASE, data, "fake");
        let r = parse_search_range("f32", "-1", "2").unwrap();
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE + 4, BASE + 12]
        );
        let r = parse_search_range("f32", "-inf", "inf").unwrap();
        assert_eq!(scan_range(&reader, 0, &r, 0, BATCH).unwrap().len(), 3);
    }

    /// Dump reader with an extra unreadable rw region in front.
    #[derive(Debug)]
    struct HoleyReader(DumpFileReader);

    impl MemoryReader for HoleyReader {
        fn backend_kind(&self) -> BackendKind {
            self.0.backend_kind()
        }
        fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
            self.0.find_process(name)
        }
        fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
            self.0.list_processes()
        }
        fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
            let hole = MemoryRegion {
                start: 0x1000,
                end: 0x2000,
                perms: "rw-p".to_owned(),
                path: None,
            };
            let ro = MemoryRegion {
                start: BASE,
                end: BASE + 8,
                perms: "r--p".to_owned(),
                path: None,
            };
            Ok([vec![hole, ro], self.0.memory_regions(pid)?].concat())
        }
        fn process_name(&self, pid: u32) -> Result<Option<String>> {
            self.0.process_name(pid)
        }
        fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
            self.0.read_bytes(pid, address, size)
        }
        fn scan(
            &self,
            pid: u32,
            patterns: Vec<ScanPattern>,
            little: bool,
        ) -> Result<Vec<ScanReport>> {
            self.0.scan(pid, patterns, little)
        }
    }

    #[test]
    fn scan_skips_unreadable_and_read_only_regions() {
        let reader = HoleyReader(u32_dump(&[259_500, 1, 259_600]));
        let r = parse_search_range("u32", "259000", "259999").unwrap();
        // The read-only duplicate of the first 8 bytes adds no hit.
        assert_eq!(
            scan_range(&reader, 0, &r, 0, BATCH).unwrap(),
            vec![BASE, BASE + 8]
        );
    }

    #[test]
    fn refine_keeps_in_range_and_drops_unreadable() {
        let reader = u32_dump(&[259_500, 300_000, 259_600]);
        let r = parse_search_range("u32", "259000", "259999").unwrap();
        let prev = [BASE, BASE + 4, BASE + 8, 0xdead_0000];
        assert_eq!(refine_range(&reader, 0, &r, &prev, 0), vec![BASE, BASE + 8]);
        assert_eq!(refine_range(&reader, 0, &r, &prev, 1), vec![BASE]);
    }
}

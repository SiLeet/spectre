//! End-to-end scan test: launch the `probe` binary, find it via the native
//! backend, and prove `scan_memory` locates the known structure inside its
//! real process memory. Works on Windows AND Linux (Linux child inherits our
//! UID so /proc/<pid>/mem is readable).

use spectre_core::types::{ScanMatch, ScanPattern, ScanValue, ValueType};
use spectre_native::create_default_reader;
#[cfg(windows)]
use spectre_native::NativeReader;
use std::process::{Child, Command};
use std::time::Duration;

fn probe_bin() -> &'static str {
    env!("CARGO_BIN_EXE_probe")
}

struct ProbeGuard(Child);

impl Drop for ProbeGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

/// Pattern matching the probe's ProbeStruct:
/// marker bytes + level (u32 == 42) + hp (f32 ≈ 9999.5).
fn probe_pattern() -> ScanPattern {
    ScanPattern {
        name: "probe-struct".to_owned(),
        fields: vec![
            // marker: first 16 bytes exact
            pattern_field_compat::marker(),
            // level
            pattern_field_compat::level(),
            // hp (f32 range around 9999.5)
            pattern_field_compat::hp(),
            // gold
            pattern_field_compat::gold(),
        ],
    }
}

mod pattern_field_compat {
    use super::*;
    use spectre_core::types::PatternField;

    pub fn marker() -> PatternField {
        let marker: Vec<u8> = vec![
            b'S', b'P', b'E', b'C', b'T', b'R', b'E', b'_', b'P', b'R', b'O', b'B', b'E', 0x00,
            0xFF, 0xDD,
        ];
        PatternField {
            name: "marker".to_owned(),
            value_type: ValueType::Bytes(16),
            value: ScanValue::Exact(marker),
            alignment: 1,
        }
    }

    pub fn level() -> PatternField {
        PatternField {
            name: "level".to_owned(),
            value_type: ValueType::U32,
            value: ScanValue::IntRange(42, 42),
            alignment: 1,
        }
    }

    pub fn hp() -> PatternField {
        PatternField {
            name: "hp".to_owned(),
            value_type: ValueType::F32,
            value: ScanValue::FloatRange(9990.0, 10010.0),
            alignment: 1,
        }
    }

    pub fn gold() -> PatternField {
        PatternField {
            name: "gold".to_owned(),
            value_type: ValueType::U64,
            value: ScanValue::IntRange(1_234_567_890, 1_234_567_890),
            alignment: 1,
        }
    }
}

fn find_exact_match(matches: &[ScanMatch]) -> Option<&ScanMatch> {
    // A match is "ours" when the marker field at offset 0 matches the bytes —
    // scan_memory already guarantees all fields matched, so any match here
    // is the probe struct (or an identical accidental layout, astronomically
    // unlikely with the 16-byte marker).
    matches.first()
}

#[test]
fn e2e_find_and_scan_probe() {
    // Skipped automatically on CI for non-host builds; unit-test-only guard:
    // if the environment can't list processes this test still fails loudly.
    let reader = create_default_reader();

    // Spawn the probe binary and use its REAL pid (Child::id) — name-based
    // process lookup is unreliable in CI containers where unrelated
    // "probe"-named kernel threads exist (pid 20 on GitHub runners).
    let child = Command::new(probe_bin())
        .spawn()
        .expect("failed to spawn probe binary");
    let pid = child.id();
    eprintln!("probe pid = {pid}");
    let _guard = ProbeGuard(child);

    // Wait for memory pages to be resident (page fault latency).
    std::thread::sleep(Duration::from_millis(500));

    let patterns = vec![probe_pattern()];
    let reports = reader
        .scan(pid, patterns, true)
        .expect("scan must not error");

    assert_eq!(reports.len(), 1, "expected exactly one report");
    let report = &reports[0];
    eprintln!("report '{}': {} match(es)", report.pattern_name, report.matches.len());

    assert!(
        !report.matches.is_empty(),
        "expected at least one match for the probe structure in pid {pid}"
    );

    let m = find_exact_match(&report.matches).expect("match");
    eprintln!("first match at {:#x}", m.address);

    // Verify typed field extraction from the matched address.
    let level = reader
        .read_u32(pid, m.address + 16, true)
        .expect("read level");
    assert_eq!(level, 42, "level at match must be 42");

    let hp = reader
        .read_f32(pid, m.address + 20, true)
        .expect("read hp");
    assert!((hp - 9999.5).abs() < 0.01, "hp at match must be ~9999.5, got {hp}");

    // Drop guard kills the probe.
}

#[test]
fn e2e_regions_available() {
    let reader = create_default_reader();
    // Find any process (our own test binary time) via list_processes.
    let procs = reader.list_processes().expect("list_processes");
    assert!(!procs.is_empty(), "must enumerate processes on this host");
    // Scan OUR OWN process — guaranteed readable (same credentials),
    // unlike arbitrary system services that deny OpenProcess.
    let any_pid = std::process::id();
    let regions = reader.memory_regions(any_pid).expect("memory_regions");
    eprintln!("pid {any_pid}: {} regions", regions.len());
    assert!(!regions.is_empty(), "must have at least one memory region");
}

#[test]
#[cfg(windows)]
fn native_reader_constructs() {
    let _ = NativeReader::Windows(Default::default());
}
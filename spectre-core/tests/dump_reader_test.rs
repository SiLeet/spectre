//! Tests for the offline DumpFileReader: it must behave like a regular
//! MemoryReader over a static byte buffer (regions, reads, scans).

use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{ScanPattern, ScanValue, ValueType};
use spectre_core::{DumpFileReader, MemoryReader};

#[test]
fn regions_cover_the_buffer() {
    let r = DumpFileReader::from_bytes(0x1000, vec![0u8; 64], "dump");
    let regions = r.memory_regions(0).unwrap();
    assert_eq!(regions.len(), 1);
    assert_eq!(regions[0].start, 0x1000);
    assert_eq!(regions[0].end, 0x1040);
    assert_eq!(regions[0].perms, "rw-");
}

#[test]
fn read_bytes_respects_base() {
    let mut data = vec![0u8; 32];
    data[8..12].copy_from_slice(&0xDEADBEEFu32.to_le_bytes());
    let r = DumpFileReader::from_bytes(0x2000, data, "dump");

    assert_eq!(r.read_u32(0, 0x2008, true).unwrap(), 0xDEADBEEF);
    // Absolute address outside the dump -> error, not a panic.
    assert!(r.read_bytes(0, 0x3000, 4).is_err());
    // Oversized read -> error.
    assert!(r.read_bytes(0, 0x2000, 999).is_err());
}

#[test]
fn find_process_matches_name() {
    let r = DumpFileReader::from_bytes(0, vec![], "afk-dump");
    let found = r.find_process("AFK").unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].pid, 0);
    assert!(r.find_process("zzz").unwrap().is_empty());
}

#[test]
fn scan_finds_values_inside_dump() {
    // Structure at dump base: u32 level=42 at +4, f32 hp≈9999.5 at +16.
    let mut data = vec![0u8; 64];
    data[4..8].copy_from_slice(&42u32.to_le_bytes());
    data[16..20].copy_from_slice(&9999.5f32.to_le_bytes());
    let r = DumpFileReader::from_bytes(0x1000, data, "dump");

    let pattern = ScanPattern {
        name: "player".to_owned(),
        fields: vec![
            spectre_core::types::PatternField {
                name: "level".to_owned(),
                value_type: ValueType::U32,
                value: ScanValue::IntRange(42, 42),
                alignment: 1,
            },
            // hp sits at +16 while level ends at +8 (level is at +4): the
            // scanner validates geometry, so the 8-byte gap must be explicit.
            spectre_core::types::PatternField {
                name: "gap".to_owned(),
                value_type: ValueType::Bytes(8),
                value: ScanValue::Any,
                alignment: 1,
            },
            spectre_core::types::PatternField {
                name: "hp".to_owned(),
                value_type: ValueType::F32,
                value: ScanValue::FloatRange(9900.0, 10010.0),
                alignment: 1,
            },
        ],
    };
    let reports = scan_memory(&r, 0, vec![pattern], &ScanConfig::default()).unwrap();
    assert_eq!(reports[0].matches.len(), 1);
    assert_eq!(reports[0].matches[0].address, 0x1004, "match at level offset");
}

#[test]
fn empty_dump_scan_is_empty() {
    let r = DumpFileReader::from_bytes(0, vec![], "dump");
    let pattern = ScanPattern {
        name: "p".to_owned(),
        fields: vec![],
    };
    let reports = r.scan(0, vec![pattern], true).unwrap();
    assert_eq!(reports.len(), 1);
    assert!(reports[0].matches.is_empty());
}
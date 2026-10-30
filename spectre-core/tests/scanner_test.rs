//! Scanner + memory-reader integration tests for spectre-core.
//!
//! Uses an in-memory [`FakeReader`] so scanning can be exercised without
//! touching a real process.

use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{scan_memory, ScanConfig};
use spectre_core::types::{
    BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport,
    ScanValue, ValueType,
};

/// Minimal in-memory MemoryReader for tests.
#[derive(Debug)]
struct FakeReader {
    /// pid → byte contents laid out at a fixed virtual base.
    regions: Vec<MemoryRegion>,
    bytes: Vec<u8>,
    base: u64,
    processes: Vec<ProcessInfo>,
}

impl FakeReader {
    fn new(base: u64, bytes: Vec<u8>) -> Self {
        let end = base + bytes.len() as u64;
        FakeReader {
            regions: vec![MemoryRegion {
                start: base,
                end,
                perms: "rw-".to_owned(),
                path: None,
            }],
            bytes,
            base,
            processes: vec![ProcessInfo { pid: 1234, name: "fake-game".to_owned() }],
        }
    }

    fn addr_to_offset(&self, addr: u64) -> Option<usize> {
        if addr >= self.base && addr < self.base + self.bytes.len() as u64 {
            Some((addr - self.base) as usize)
        } else {
            None
        }
    }
}

impl MemoryReader for FakeReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        let lower = name.to_lowercase();
        Ok(self
            .processes
            .iter()
            .filter(|p| p.name.to_lowercase().contains(&lower))
            .cloned()
            .collect())
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(self.processes.clone())
    }

    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        Ok(self.regions.clone())
    }

    fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
        Ok(Some("fake-game".to_owned()))
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        let off = self.addr_to_offset(address).ok_or_else(|| {
            anyhow::anyhow!("address {address:#x} outside fake memory")
        })?;
        let end = off + size as usize;
        if end > self.bytes.len() {
            anyhow::bail!("read {size} bytes at {address:#x} exceeds fake memory");
        }
        Ok(self.bytes[off..end].to_vec())
    }

    fn scan(&self, _pid: u32, patterns: Vec<ScanPattern>, little: bool) -> anyhow::Result<Vec<ScanReport>> {
        let config = ScanConfig { little_endian: little, ..Default::default() };
        scan_memory(self, _pid, patterns, &config)
    }
}

fn u32_at(bytes: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(bytes[offset..offset + 4].try_into().unwrap())
}

fn pattern_u32(name: &str, field: &str, _off: usize, lo: i64, hi: i64) -> ScanPattern {
    ScanPattern {
        name: name.to_owned(),
        fields: vec![ScanPatternField {
            name: field.to_owned(),
            value_type: ValueType::U32,
            value: ScanValue::IntRange(lo, hi),
            alignment: 1,
        }],
    }
}

use spectre_core::types::PatternField as ScanPatternField;

#[test]
fn find_process_matches_substring() {
    let reader = FakeReader::new(0x1000, vec![0u8; 32]);
    let found = reader.find_process("FAKE").unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].pid, 1234);
}

#[test]
fn scan_finds_u32_range_and_addresses_are_absolute() {
    // Layout: value 42 at base+4, value 900 at base+16.
    let mut bytes = vec![0u8; 64];
    bytes[4..8].copy_from_slice(&42u32.to_le_bytes());
    bytes[16..20].copy_from_slice(&900u32.to_le_bytes());
    let reader = FakeReader::new(0x1000, bytes);

    let pattern = pattern_u32("level", "value", 0, 40, 50);
    let reports = reader.scan(1234, vec![pattern], true).unwrap();
    assert_eq!(reports.len(), 1);
    let matches = &reports[0].matches;
    assert_eq!(matches.len(), 1, "expected exactly one match");
    // Address must be absolute (base + offset), not relative.
    assert_eq!(matches[0].address, 0x1004);
}

#[test]
fn scan_rejects_out_of_range_values() {
    let mut bytes = vec![0u8; 64];
    bytes[0..4].copy_from_slice(&7u32.to_le_bytes()); // below range
    bytes[8..12].copy_from_slice(&300u32.to_le_bytes()); // above range
    let reader = FakeReader::new(0x1000, bytes);

    let pattern = pattern_u32("level", "value", 0, 10, 20);
    let reports = reader.scan(1234, vec![pattern], true).unwrap();
    assert!(reports[0].matches.is_empty());
}

#[test]
fn scan_honours_alignment() {
    // With alignment=4 and a 4-byte value, only addresses 0x1000, 0x1004, ...
    // are candidates. Put a match at 0x1001 (unaligned) — it must NOT be found.
    let mut bytes = vec![0u8; 64];
    let target: u32 = 77;
    bytes[1..5].copy_from_slice(&target.to_le_bytes());
    let reader = FakeReader::new(0x1000, bytes);

    let pattern = ScanPattern {
        name: "aligned".to_owned(),
        fields: vec![ScanPatternField {
            name: "v".to_owned(),
            value_type: ValueType::U32,
            value: ScanValue::Exact(77u32.to_le_bytes().to_vec()),
            alignment: 1,
        }],
    };
    let config = ScanConfig { alignment: 4, ..Default::default() };
    let reports = scan_memory(&reader, 1234, vec![pattern], &config).unwrap();
    // 77 at 0x1001 is skipped due to 4-byte alignment.
    assert!(reports[0].matches.is_empty());
}

#[test]
fn scan_multi_field_pattern_all_fields_must_match() {
    // struct { u32 level; u8 active; } — both must match at the same address.
    let target_level: u32 = 55;
    let mut bytes = vec![0u8; 64];
    bytes[0..4].copy_from_slice(&target_level.to_le_bytes());
    bytes[4] = 1; // active
    let reader = FakeReader::new(0x1000, bytes);

    let pattern = ScanPattern {
        name: "player".to_owned(),
        fields: vec![
            ScanPatternField {
                name: "level".to_owned(),
                value_type: ValueType::U32,
                value: ScanValue::IntRange(50, 60),
                alignment: 1,
            },
            ScanPatternField {
                name: "active".to_owned(),
                value_type: ValueType::U8,
                value: ScanValue::Exact(vec![1]),
                alignment: 1,
            },
        ],
    };
    let reports = scan_memory(&reader, 1234, vec![pattern], &ScanConfig::default()).unwrap();
    assert_eq!(reports[0].matches.len(), 1);
    assert_eq!(reports[0].matches[0].address, 0x1000);
    // Field extraction returns raw bytes for both fields.
    let fields = &reports[0].matches[0].fields;
    assert_eq!(fields.len(), 2);
    assert_eq!(u32_at(&fields[0].2, 0), 55);
    assert_eq!(fields[1].2[0], 1);
}

#[test]
fn scan_is_bounded_by_region_filter() {
    let bytes = vec![0u8; 32];
    let reader = FakeReader { base: 0x1000, ..FakeReader::new(0x1000, bytes) };
    // Region perms are "rw-" so a filter of "x" excludes everything.
    let config = ScanConfig { region_filter: Some("x".to_owned()), ..Default::default() };
    let reports = scan_memory(&reader, 1234, vec![pattern_u32("p", "v", 0, 0, 100)], &config).unwrap();
    assert!(reports[0].matches.is_empty());
}

#[test]
fn typed_reads_endian_and_string() {
    let mut bytes = vec![0u8; 64];
    bytes[8..12].copy_from_slice(&0xDEADBEEFu32.to_be_bytes());
    bytes[16..27].copy_from_slice(b"hello world");
    let reader = FakeReader::new(0x1000, bytes);

    assert_eq!(reader.read_u32(1234, 0x1008, false).unwrap(), 0xDEADBEEF);
    assert_eq!(reader.read_u32(1234, 0x1008, true).unwrap(), 0xEFBEADDE);
    assert_eq!(reader.read_string(1234, 0x1010, 32).unwrap(), "hello world");
    // read_string stops at NUL.
    let mut bytes2 = vec![0u8; 32];
    bytes2[0..7].copy_from_slice(b"abc\0def");
    let r2 = FakeReader::new(0x2000, bytes2);
    assert_eq!(r2.read_string(1, 0x2000, 32).unwrap(), "abc");
}

#[test]
fn max_matches_caps_results() {
    let mut bytes = vec![0u8; 256];
    for i in (0..256).step_by(4) {
        bytes[i..i + 4].copy_from_slice(&42u32.to_le_bytes());
    }
    let reader = FakeReader::new(0x1000, bytes);
    let config = ScanConfig { max_matches_per_pattern: 3, ..Default::default() };

    let reports = scan_memory(
        &reader,
        1234,
        vec![pattern_u32("p", "v", 0, 42, 42)],
        &config,
    )
    .unwrap();
    assert_eq!(reports[0].matches.len(), 3);
}

#[test]
fn value_type_sizes() {
    assert_eq!(ValueType::U8.size(), 1);
    assert_eq!(ValueType::I8.size(), 1);
    assert_eq!(ValueType::U16.size(), 2);
    assert_eq!(ValueType::I32.size(), 4);
    assert_eq!(ValueType::F32.size(), 4);
    assert_eq!(ValueType::U64.size(), 8);
    assert_eq!(ValueType::F64.size(), 8);
    assert_eq!(ValueType::Bytes(17).size(), 17);
}
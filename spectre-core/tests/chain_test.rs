//! Tests for pointer-chain walking (`follow`, `follow_until_end`).
//!
//! Uses an in-memory [`FakeReader`]: one flat buffer mapped at `BASE`;
//! everything outside it is unreadable.

use spectre_core::reader::MemoryReader;
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_core::{ChainStep, ChainStop, follow, follow_until_end};

const BASE: u64 = 0x1000;
const PID: u32 = 1234;

/// Minimal in-memory MemoryReader for tests.
#[derive(Debug)]
struct FakeReader {
    bytes: Vec<u8>,
}

impl FakeReader {
    fn new(len: usize) -> Self {
        FakeReader {
            bytes: vec![0u8; len],
        }
    }

    /// Store `value` little-endian at absolute address `addr`.
    fn put(&mut self, addr: u64, value: u64) -> &mut Self {
        self.put_bytes(addr, &value.to_le_bytes())
    }

    fn put_bytes(&mut self, addr: u64, bytes: &[u8]) -> &mut Self {
        let off = (addr - BASE) as usize;
        self.bytes[off..off + bytes.len()].copy_from_slice(bytes);
        self
    }
}

impl MemoryReader for FakeReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, _name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(vec![])
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(vec![])
    }

    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        Ok(vec![MemoryRegion {
            start: BASE,
            end: BASE + self.bytes.len() as u64,
            perms: "rw-".to_owned(),
            path: None,
        }])
    }

    fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
        Ok(Some("fake-game".to_owned()))
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        let end = BASE + self.bytes.len() as u64;
        if address < BASE || address + size as u64 > end {
            anyhow::bail!("read {size} bytes at {address:#x} outside fake memory");
        }
        let off = (address - BASE) as usize;
        Ok(self.bytes[off..off + size as usize].to_vec())
    }

    fn scan(
        &self,
        _pid: u32,
        _patterns: Vec<ScanPattern>,
        _little: bool,
    ) -> anyhow::Result<Vec<ScanReport>> {
        Ok(vec![])
    }
}

#[test]
fn follow_two_offsets_matches_resolve_ptr_chain() {
    let mut r = FakeReader::new(0x400);
    // *(0x1000 + 0x10) = 0x1200; *(0x1200 + 0x8) = 0xDEAD (value at result).
    r.put(0x1010, 0x1200).put(0x1208, 0xDEAD);

    let chain = follow(&r, PID, 0x1000, &[0x10, 0x8], true).unwrap();
    assert_eq!(chain.stop, ChainStop::Complete);
    assert_eq!(chain.resolved, Some(0x1208));
    assert_eq!(chain.offsets, vec![0x10, 0x8]);
    assert_eq!(
        chain.steps,
        vec![
            ChainStep {
                pointer: 0x1000,
                offset: 0x10,
                address: 0x1010,
                value: 0x1200
            },
            ChainStep {
                pointer: 0x1200,
                offset: 0x8,
                address: 0x1208,
                value: 0xDEAD
            },
        ]
    );
    // Same semantics as the trait's resolve_ptr_chain.
    assert_eq!(
        r.resolve_ptr_chain(PID, 0x1000, &[0x10, 0x8], true)
            .unwrap(),
        chain.resolved
    );
}

#[test]
fn follow_empty_offsets_returns_base_without_reading() {
    let r = FakeReader::new(0x10);
    // Outside fake memory: would fail if it were read.
    let chain = follow(&r, PID, 0x9999_0000, &[], true).unwrap();
    assert_eq!(chain.resolved, Some(0x9999_0000));
    assert_eq!(chain.stop, ChainStop::Complete);
    assert!(chain.steps.is_empty());
    assert_eq!(
        r.resolve_ptr_chain(PID, 0x9999_0000, &[], true).unwrap(),
        chain.resolved
    );
}

#[test]
fn follow_honours_big_endian() {
    let mut r = FakeReader::new(0x400);
    r.put_bytes(0x1000, &0x1100u64.to_be_bytes());
    let chain = follow(&r, PID, 0x1000, &[0, 0x20], false).unwrap();
    assert_eq!(chain.resolved, Some(0x1120));
    assert_eq!(chain.steps[0].value, 0x1100);
}

#[test]
fn follow_stops_at_null_intermediate() {
    let mut r = FakeReader::new(0x400);
    r.put(0x1010, 0); // first deref is NULL
    let chain = follow(&r, PID, 0x1000, &[0x10, 0x8], true).unwrap();
    assert_eq!(chain.stop, ChainStop::Null);
    assert_eq!(chain.resolved, None);
    assert_eq!(chain.steps.len(), 1);
}

#[test]
fn follow_reports_unreadable_where_resolve_ptr_chain_errors() {
    let mut r = FakeReader::new(0x400);
    r.put(0x1010, 0x7777_0000); // points outside fake memory
    let chain = follow(&r, PID, 0x1000, &[0x10, 0x8], true).unwrap();
    assert_eq!(
        chain.stop,
        ChainStop::Unreadable {
            address: 0x7777_0008
        }
    );
    assert_eq!(chain.resolved, None);
    assert_eq!(chain.steps.len(), 1);
    let err = chain.read_error.as_deref().unwrap();
    assert!(err.contains("outside fake memory"), "{err}");
    assert!(
        r.resolve_ptr_chain(PID, 0x1000, &[0x10, 0x8], true)
            .is_err()
    );
}

#[test]
fn cheat_engine_path_needs_a_leading_zero_offset() {
    let mut r = FakeReader::new(0x400);
    // CE path "0x1000 -> [0x10, 0x8]" = [[0x1000]+0x10]+0x8.
    r.put(0x1000, 0x1100).put(0x1110, 0x1200);
    let ce = 0x1200 + 0x8;

    let chain = follow(&r, PID, 0x1000, &[0, 0x10, 0x8], true).unwrap();
    assert_eq!(chain.stop, ChainStop::Complete);
    assert_eq!(chain.resolved, Some(ce));
    // Without the leading 0 the base is not dereferenced: [0x1000+0x10]+0x8.
    let short = follow(&r, PID, 0x1000, &[0x10, 0x8], true).unwrap();
    assert_ne!(short.resolved, Some(ce));
}

#[test]
fn follow_overflow_is_an_error() {
    let r = FakeReader::new(0x10);
    assert!(follow(&r, PID, u64::MAX, &[1], true).is_err());
}

#[test]
fn until_end_stops_at_null() {
    let mut r = FakeReader::new(0x400);
    // 0x1000 -> 0x1100 -> 0x1200 -> NULL
    r.put(0x1000, 0x1100).put(0x1100, 0x1200).put(0x1200, 0);

    let chain = follow_until_end(&r, PID, 0x1000, 16, true).unwrap();
    assert_eq!(chain.stop, ChainStop::Null);
    let addrs: Vec<u64> = chain.steps.iter().map(|s| s.address).collect();
    assert_eq!(addrs, vec![0x1000, 0x1100, 0x1200]);
    assert_eq!(chain.steps.last().unwrap().value, 0);
    assert_eq!(chain.resolved, Some(0x1200));
    assert_eq!(chain.offsets, vec![0, 0, 0]);

    // Replaying the recorded offsets with follow() lands on the same address.
    let replay = follow(&r, PID, chain.base, &chain.offsets, true).unwrap();
    assert_eq!(replay.resolved, chain.resolved);
}

#[test]
fn until_end_respects_max_depth() {
    let mut r = FakeReader::new(0x400);
    // 0x1000 -> 0x1008 -> 0x1010 -> ... (a long non-repeating chain)
    for i in 0..0x40u64 {
        r.put(0x1000 + i * 8, 0x1000 + (i + 1) * 8);
    }
    let chain = follow_until_end(&r, PID, 0x1000, 3, true).unwrap();
    assert_eq!(chain.stop, ChainStop::MaxDepth);
    assert_eq!(chain.steps.len(), 3);
    assert_eq!(chain.resolved, Some(0x1010));

    let none = follow_until_end(&r, PID, 0x1000, 0, true).unwrap();
    assert_eq!(none.stop, ChainStop::MaxDepth);
    assert!(none.steps.is_empty());
    assert_eq!(none.resolved, None);
}

#[test]
fn until_end_detects_cycle() {
    let mut r = FakeReader::new(0x400);
    // 0x1000 -> 0x1100 -> 0x1200 -> 0x1100 (loop)
    r.put(0x1000, 0x1100)
        .put(0x1100, 0x1200)
        .put(0x1200, 0x1100);

    let chain = follow_until_end(&r, PID, 0x1000, 100, true).unwrap();
    assert_eq!(chain.stop, ChainStop::Cycle { address: 0x1100 });
    assert_eq!(chain.steps.len(), 3);
    assert_eq!(chain.resolved, Some(0x1200));
}

#[test]
fn until_end_detects_self_loop() {
    let mut r = FakeReader::new(0x10);
    r.put(0x1000, 0x1000);
    let chain = follow_until_end(&r, PID, 0x1000, 100, true).unwrap();
    assert_eq!(chain.stop, ChainStop::Cycle { address: 0x1000 });
    assert_eq!(chain.steps.len(), 1);
}

#[test]
fn until_end_reports_unreadable() {
    let mut r = FakeReader::new(0x400);
    r.put(0x1000, 0x1100).put(0x1100, 0xBAD0_0000);

    let chain = follow_until_end(&r, PID, 0x1000, 16, true).unwrap();
    assert_eq!(
        chain.stop,
        ChainStop::Unreadable {
            address: 0xBAD0_0000
        }
    );
    assert_eq!(chain.steps.len(), 2);
    assert_eq!(chain.resolved, Some(0x1100));
    assert!(chain.read_error.is_some());

    // Unreadable start: nothing resolved.
    let start = follow_until_end(&r, PID, 0x50, 16, true).unwrap();
    assert_eq!(start.stop, ChainStop::Unreadable { address: 0x50 });
    assert_eq!(start.resolved, None);
    assert!(start.read_error.is_some());

    // Successful walks carry no read error.
    let ok = follow_until_end(&r, PID, 0x1000, 1, true).unwrap();
    assert_eq!(ok.read_error, None);
}

#[test]
fn stop_reason_display() {
    assert_eq!(ChainStop::Null.to_string(), "null pointer");
    assert_eq!(ChainStop::MaxDepth.to_string(), "max depth reached");
    assert_eq!(
        ChainStop::Unreadable { address: 0x10 }.to_string(),
        "unreadable memory at 0x10"
    );
    assert_eq!(
        ChainStop::Cycle { address: 0x10 }.to_string(),
        "cycle (0x10 already visited)"
    );
}

//! Boundary tests for the scanner: matches at region ends, matches that
//! straddle read batches, alignment phase across batches, and an exhaustive
//! comparison against a naive oracle that tests every aligned address.

use std::sync::atomic::{AtomicUsize, Ordering};

use spectre_core::DumpFileReader;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{
    BackendKind, MemoryRegion, PatternField, ProcessInfo, ScanPattern, ScanReport, ScanValue,
    ValueType,
};

/// In-memory reader with several separate regions. A read must lie entirely
/// inside one region, otherwise it fails and is counted as out of bounds.
#[derive(Debug)]
struct MultiReader {
    regions: Vec<(u64, Vec<u8>)>,
    /// Reads covering this address fail (simulates an unreadable page).
    fail_at: Option<u64>,
    reads: AtomicUsize,
    out_of_bounds: AtomicUsize,
}

impl MultiReader {
    fn new(regions: Vec<(u64, Vec<u8>)>) -> Self {
        MultiReader {
            regions,
            fail_at: None,
            reads: AtomicUsize::new(0),
            out_of_bounds: AtomicUsize::new(0),
        }
    }
}

impl MemoryReader for MultiReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, _name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }

    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        Ok(self
            .regions
            .iter()
            .map(|(start, bytes)| MemoryRegion {
                start: *start,
                end: start + bytes.len() as u64,
                perms: "rw-".to_owned(),
                path: None,
            })
            .collect())
    }

    fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
        Ok(None)
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        self.reads.fetch_add(1, Ordering::Relaxed);
        let end = address + u64::from(size);
        if let Some(bad) = self.fail_at
            && (address..end).contains(&bad)
        {
            anyhow::bail!("unreadable page at {bad:#x}");
        }
        for (start, bytes) in &self.regions {
            let region_end = start + bytes.len() as u64;
            if address >= *start && end <= region_end {
                let off = (address - start) as usize;
                return Ok(bytes[off..off + size as usize].to_vec());
            }
        }
        self.out_of_bounds.fetch_add(1, Ordering::Relaxed);
        anyhow::bail!("read of {size} bytes at {address:#x} is outside every region")
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> anyhow::Result<Vec<ScanReport>> {
        let config = ScanConfig { little_endian: little, ..Default::default() };
        scan_memory(self, pid, patterns, &config)
    }
}

/// An all-`Exact` pattern: `(value_type, alignment, bytes)` per field.
#[derive(Clone)]
struct Spec {
    fields: Vec<(ValueType, u32, Vec<u8>)>,
}

impl Spec {
    /// One `Bytes(span)` field with a distinctive signature.
    fn bytes(span: u32) -> Self {
        let sig = (0..span).map(|i| 0xC3u8 ^ (i as u8).wrapping_mul(37)).collect();
        Spec { fields: vec![(ValueType::Bytes(span), 1, sig)] }
    }

    /// `u8` at 0, `u32` aligned to 4 (offset 4), `u16` aligned to 2 (offset
    /// 8): span 10 with internal padding.
    fn mixed() -> Self {
        Spec {
            fields: vec![
                (ValueType::U8, 1, vec![0x5A]),
                (ValueType::U32, 4, vec![0x11, 0x22, 0x33, 0x44]),
                (ValueType::U16, 2, vec![0x99, 0x77]),
            ],
        }
    }

    /// Field offsets relative to the structure start, computed independently
    /// of the scanner: each field starts at the next multiple of its alignment.
    fn layout(&self) -> Vec<(usize, &[u8])> {
        let mut rel = 0usize;
        let mut out = Vec::new();
        for (_, align, bytes) in &self.fields {
            let a = (*align).max(1) as usize;
            rel = rel.div_ceil(a) * a;
            out.push((rel, bytes.as_slice()));
            rel += bytes.len();
        }
        out
    }

    fn span(&self) -> usize {
        self.layout().last().map_or(0, |(rel, b)| rel + b.len())
    }

    fn pattern(&self) -> ScanPattern {
        ScanPattern {
            name: "sig".to_owned(),
            fields: self
                .fields
                .iter()
                .enumerate()
                .map(|(i, (vt, align, bytes))| PatternField {
                    name: format!("f{i}"),
                    value_type: *vt,
                    value: ScanValue::Exact(bytes.clone()),
                    alignment: *align,
                })
                .collect(),
        }
    }

    /// Write the pattern into `buf` at `at` (padding bytes are left alone).
    fn plant(&self, buf: &mut [u8], at: usize) {
        for (rel, bytes) in self.layout() {
            buf[at + rel..at + rel + bytes.len()].copy_from_slice(bytes);
        }
    }
}

/// Naive reference: test every aligned start address directly.
fn oracle(regions: &[(u64, Vec<u8>)], spec: &Spec, alignment: u32) -> Vec<u64> {
    let span = spec.span();
    let align = u64::from(alignment.max(1));
    let mut hits = Vec::new();
    for (start, bytes) in regions {
        if bytes.len() < span {
            continue;
        }
        for off in 0..=bytes.len() - span {
            let addr = start + off as u64;
            if !addr.is_multiple_of(align) {
                continue;
            }
            if spec
                .layout()
                .iter()
                .all(|(rel, want)| &bytes[off + rel..off + rel + want.len()] == *want)
            {
                hits.push(addr);
            }
        }
    }
    hits
}

/// Deterministic filler that rarely contains a signature by accident.
fn filler(len: usize, seed: u32) -> Vec<u8> {
    let mut x = seed.wrapping_mul(2_654_435_761).wrapping_add(1);
    (0..len)
        .map(|_| {
            x = x.wrapping_mul(1_103_515_245).wrapping_add(12_345);
            (x >> 16) as u8
        })
        .collect()
}

fn scan_addrs(reader: &MultiReader, spec: &Spec, alignment: u32, batch_size: u32) -> Vec<u64> {
    let config = ScanConfig {
        alignment,
        batch_size,
        region_filter: None,
        ..Default::default()
    };
    let reports = scan_memory(reader, 1, vec![spec.pattern()], &config).unwrap();
    reports[0].matches.iter().map(|m| m.address).collect()
}

fn batch_sizes(span: u32) -> Vec<u32> {
    let mut v = vec![0, 1, span.saturating_sub(1), span, span + 1, 2 * span - 1, 2 * span + 1, 7, 16, 1 << 20];
    v.sort_unstable();
    v.dedup();
    v
}

fn specs() -> Vec<Spec> {
    let mut v: Vec<Spec> = [1, 2, 3, 4, 5, 8, 13].into_iter().map(Spec::bytes).collect();
    v.push(Spec::mixed());
    v
}

#[test]
fn single_plant_at_every_position_matches_oracle() {
    // One region, one planted structure; move it over every byte position
    // (region start, end - span, every batch boundary) for many
    // span/alignment/batch-size combinations and unaligned region starts.
    for spec in specs() {
        let span = spec.span();
        for region_start in [0x1000u64, 0x1001, 0x1003, 0x1006] {
            let len = 3 * span + 11;
            for at in 0..=len - span {
                let mut bytes = filler(len, at as u32);
                spec.plant(&mut bytes, at);
                let regions = vec![(region_start, bytes)];
                let reader = MultiReader::new(regions.clone());
                for alignment in [1, 2, 4, 8] {
                    let want = oracle(&regions, &spec, alignment);
                    if (region_start + at as u64).is_multiple_of(u64::from(alignment)) {
                        assert!(want.contains(&(region_start + at as u64)));
                    }
                    for batch in batch_sizes(span as u32) {
                        let got = scan_addrs(&reader, &spec, alignment, batch);
                        assert_eq!(
                            got, want,
                            "span={span} region_start={region_start:#x} at={at} \
                             alignment={alignment} batch={batch}"
                        );
                    }
                }
                assert_eq!(reader.out_of_bounds.load(Ordering::Relaxed), 0);
            }
        }
    }
}

#[test]
fn many_plants_across_regions_match_oracle() {
    // Several regions with gaps between them (reads across a gap fail), a
    // structure planted at the start, at end - span and densely in between,
    // including overlapping copies.
    for spec in specs() {
        let span = spec.span();
        let mut regions = Vec::new();
        let mut base = 0x10_000u64;
        for (i, len) in [span, span + 1, 2 * span + 3, 97, 256].into_iter().enumerate() {
            let mut bytes = filler(len, 1000 + i as u32);
            let mut at = 0;
            while at + span <= len {
                spec.plant(&mut bytes, at);
                at += (at % 5) + 1;
            }
            spec.plant(&mut bytes, len - span);
            regions.push((base + (i as u64 % 4), bytes));
            base += 0x1000;
        }
        let reader = MultiReader::new(regions.clone());
        for alignment in [1, 2, 4, 8] {
            let want = oracle(&regions, &spec, alignment);
            assert!(!want.is_empty());
            for batch in batch_sizes(span as u32) {
                assert_eq!(
                    scan_addrs(&reader, &spec, alignment, batch),
                    want,
                    "span={span} alignment={alignment} batch={batch}"
                );
            }
        }
        assert_eq!(reader.out_of_bounds.load(Ordering::Relaxed), 0);
    }
}

#[test]
fn sixteen_byte_dump_holds_one_sixteen_byte_struct() {
    // The practice layout: u32 score, u8 round, 11 marker bytes = 16 bytes.
    let mut data = vec![0xABu8; 16];
    data[0..4].copy_from_slice(&31537u32.to_le_bytes());
    data[4] = 2;
    let reader = DumpFileReader::from_bytes(0x1e4f03d31c0, data, "dump");
    let pattern = ScanPattern {
        name: "PracticeScore".to_owned(),
        fields: vec![
            PatternField {
                name: "score".to_owned(),
                value_type: ValueType::U32,
                value: ScanValue::Any,
                alignment: 1,
            },
            PatternField {
                name: "round".to_owned(),
                value_type: ValueType::U8,
                value: ScanValue::Any,
                alignment: 1,
            },
            PatternField {
                name: "marker".to_owned(),
                value_type: ValueType::Bytes(11),
                value: ScanValue::Any,
                alignment: 1,
            },
        ],
    };
    let reports = scan_memory(&reader, 0, vec![pattern], &ScanConfig::default()).unwrap();
    let matches = &reports[0].matches;
    assert_eq!(matches.len(), 1);
    assert_eq!(matches[0].address, 0x1e4f03d31c0);
    let offsets: Vec<u32> = matches[0].fields.iter().map(|f| f.0).collect();
    assert_eq!(offsets, vec![0, 4, 5]);
    assert_eq!(matches[0].fields[0].2, 31537u32.to_le_bytes());
}

#[test]
fn match_straddling_a_batch_boundary_is_found() {
    let spec = Spec::bytes(4);
    let mut bytes = vec![0u8; 64];
    spec.plant(&mut bytes, 14); // bytes 14..18 cross the first 16-byte batch
    let reader = MultiReader::new(vec![(0x2000, bytes)]);
    assert_eq!(scan_addrs(&reader, &spec, 2, 16), vec![0x200E]);
}

#[test]
fn field_offsets_are_relative_to_the_structure() {
    // Same structure, found through different batch splits, reports the same
    // structure-relative field offsets.
    let spec = Spec::mixed();
    let mut bytes = filler(80, 7);
    spec.plant(&mut bytes, 36);
    let reader = MultiReader::new(vec![(0x3000, bytes)]);
    for batch in [1, 9, 10, 11, 37, 1 << 20] {
        let config = ScanConfig { batch_size: batch, region_filter: None, ..Default::default() };
        let reports = scan_memory(&reader, 1, vec![spec.pattern()], &config).unwrap();
        let m = &reports[0].matches;
        assert_eq!(m.len(), 1, "batch={batch}");
        assert_eq!(m[0].address, 0x3000 + 36);
        let offsets: Vec<u32> = m[0].fields.iter().map(|f| f.0).collect();
        assert_eq!(offsets, vec![0, 4, 8], "batch={batch}");
        assert_eq!(m[0].fields[1].2, vec![0x11, 0x22, 0x33, 0x44]);
    }
}

#[test]
fn max_matches_keeps_the_lowest_addresses_across_batches() {
    let spec = Spec::bytes(4);
    let mut bytes = vec![0u8; 64];
    for at in (0..64).step_by(4) {
        spec.plant(&mut bytes, at);
    }
    let reader = MultiReader::new(vec![(0x4000, bytes)]);
    for batch in [1, 3, 4, 5, 64] {
        let config = ScanConfig {
            batch_size: batch,
            max_matches_per_pattern: 3,
            region_filter: None,
            ..Default::default()
        };
        let reports = scan_memory(&reader, 1, vec![spec.pattern()], &config).unwrap();
        let addrs: Vec<u64> = reports[0].matches.iter().map(|m| m.address).collect();
        assert_eq!(addrs, vec![0x4000, 0x4004, 0x4008], "batch={batch}");
    }
}

#[test]
fn zero_span_pattern_matches_nothing() {
    let reader = MultiReader::new(vec![(0x5000, vec![0u8; 32])]);
    let empty = ScanPattern { name: "empty".to_owned(), fields: vec![] };
    let zero_sized = ScanPattern {
        name: "zero".to_owned(),
        fields: vec![PatternField {
            name: "z".to_owned(),
            value_type: ValueType::Bytes(0),
            value: ScanValue::Any,
            alignment: 1,
        }],
    };
    let config = ScanConfig { batch_size: 1, region_filter: None, ..Default::default() };
    let reports = scan_memory(&reader, 1, vec![empty, zero_sized], &config).unwrap();
    assert!(reports.iter().all(|r| r.matches.is_empty()));
    assert_eq!(reader.reads.load(Ordering::Relaxed), 0);
}

#[test]
fn region_smaller_than_the_pattern_is_skipped() {
    let spec = Spec::bytes(8);
    let reader = MultiReader::new(vec![(0x6000, vec![0u8; 7])]);
    assert!(scan_addrs(&reader, &spec, 1, 1 << 20).is_empty());
    assert_eq!(reader.reads.load(Ordering::Relaxed), 0);
}

#[test]
fn region_at_the_top_of_the_address_space() {
    // The region ends at u64::MAX (exclusive); no address arithmetic may
    // overflow while stepping towards it.
    let spec = Spec::bytes(2);
    let start = u64::MAX - 32;
    let mut bytes = vec![0u8; 32];
    spec.plant(&mut bytes, 25); // at u64::MAX - 7, 8-aligned
    spec.plant(&mut bytes, 30); // ends exactly at the region end
    let regions = vec![(start, bytes)];
    let reader = MultiReader::new(regions.clone());
    assert_eq!(oracle(&regions, &spec, 1), vec![u64::MAX - 7, u64::MAX - 2]);
    for alignment in [1, 2, 4, 8, 64] {
        let want = oracle(&regions, &spec, alignment);
        for batch in [1, 2, 3, 1 << 20] {
            assert_eq!(
                scan_addrs(&reader, &spec, alignment, batch),
                want,
                "alignment={alignment} batch={batch}"
            );
        }
    }
}

#[test]
fn failed_read_skips_rest_of_region_but_not_later_regions() {
    let spec = Spec::bytes(4);
    let mut first = vec![0u8; 64];
    spec.plant(&mut first, 0);
    spec.plant(&mut first, 40);
    let mut second = vec![0u8; 16];
    spec.plant(&mut second, 12);
    let mut reader = MultiReader::new(vec![(0x7000, first), (0x9000, second)]);
    reader.fail_at = Some(0x7000 + 20);
    // Batches of 16: [0x7000, 0x7010) reads fine, the batch holding 0x7014
    // fails, so 0x7028 is not reached; the second region is still scanned.
    assert_eq!(scan_addrs(&reader, &spec, 4, 16), vec![0x7000, 0x900C]);
}

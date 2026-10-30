/// Memory scanner — pattern-based search through process memory.
use crate::reader::MemoryReader;
use crate::types::{MemoryRegion, ScanMatch, ScanPattern, ScanReport, ScanValue};
use anyhow::Result;
use tracing::{debug, info};

/// Configuration for the scanning engine.
#[derive(Debug, Clone)]
pub struct ScanConfig {
    /// Alignment boundary for search (default 4).
    pub alignment: u32,
    /// Maximum bytes to pull per read batch (default 1 MiB).
    pub batch_size: u32,
    /// Endianness: default little.
    pub little_endian: bool,
    /// Stop after finding N matches per pattern (0 = unlimited).
    pub max_matches_per_pattern: u32,
    /// Only scan regions whose perms contain every char in this filter.
    pub region_filter: Option<String>,
}

impl Default for ScanConfig {
    fn default() -> Self {
        Self {
            alignment: 4,
            batch_size: 1024 * 1024,
            little_endian: true,
            max_matches_per_pattern: 0,
            region_filter: Some("rw".to_owned()),
        }
    }
}

/// Execute a multi-pattern scan across process memory.
pub fn scan_memory(
    reader: &dyn MemoryReader,
    pid: u32,
    patterns: Vec<ScanPattern>,
    config: &ScanConfig,
) -> Result<Vec<ScanReport>> {
    let regions = reader.memory_regions(pid)?;
    debug!("found {} memory regions", regions.len());
    let target: Vec<MemoryRegion> = filter_regions(regions, config.region_filter.as_deref());
    info!("scanning {} regions", target.len());

    let mut reports = Vec::with_capacity(patterns.len());
    for pattern in patterns {
        info!("scanning pattern '{}' ({} fields)", pattern.name, pattern.fields.len());
        let matches = scan_single_pattern(reader, pid, &target, &pattern, config)?;
        info!("  `{}`: {} matches", pattern.name, matches.len());
        reports.push(ScanReport { pattern_name: pattern.name, matches });
    }
    Ok(reports)
}

fn scan_single_pattern(
    reader: &dyn MemoryReader,
    pid: u32,
    regions: &[MemoryRegion],
    pattern: &ScanPattern,
    config: &ScanConfig,
) -> Result<Vec<ScanMatch>> {
    let mut all_matches = Vec::new();
    let span = pattern.span();
    let max_matches = config.max_matches_per_pattern;

    for region in regions {
        let start = align_up(region.start, config.alignment as u64);
        let limit = region.end.saturating_sub(span);
        if start >= limit {
            continue;
        }

        let mut cursor = start;
        while cursor < limit {
            let chunk_len = u32::min(config.batch_size, (limit - cursor) as u32);
            // Read one batch; skip region if unreadable (permission race).
            let chunk = match reader.read_bytes(pid, cursor, chunk_len) {
                Ok(c) => c,
                Err(e) => {
                    debug!("skip region read at {cursor:#x}: {e}");
                    break;
                }
            };

            // Test each aligned offset within the chunk.
            let stride = config.alignment.max(1) as usize;
            let mut idx = 0usize;
            loop {
                if idx + span as usize > chunk.len() {
                    break;
                }
                if let Some(m) = try_match(&chunk, idx, pattern, config.little_endian) {
                    all_matches.push(m);
                    if max_matches > 0 && all_matches.len() >= max_matches as usize {
                        return Ok(all_matches);
                    }
                }
                idx += stride;
            }
            cursor += chunk_len as u64;
        }
    }
    Ok(all_matches)
}

fn try_match(
    chunk: &[u8],
    offset: usize,
    pattern: &ScanPattern,
    little: bool,
) -> Option<ScanMatch> {
    let mut fields = Vec::with_capacity(pattern.fields.len());
    let mut field_abs = offset;

    for f in &pattern.fields {
        let size = f.value_type.size() as usize;
        if field_abs + size > chunk.len() {
            return None;
        }
        let bytes = &chunk[field_abs..field_abs + size];
        if !match_field(bytes, size, &f.value, little) {
            return None;
        }
        fields.push((field_abs as u32, f.name.clone(), bytes.to_vec()));
        let align = usize::max(1, f.alignment as usize);
        field_abs = ((field_abs + size + align - 1) / align) * align;
    }

    Some(ScanMatch { address: offset as u64, fields })
}

fn match_field(bytes: &[u8], size: usize, expected: &ScanValue, little: bool) -> bool {
    match expected {
        ScanValue::Exact(pattern) => bytes == pattern.as_slice(),
        ScanValue::IntRange(lo, hi) => {
            let v = bytes_to_i64(bytes, size, little);
            v >= *lo && v <= *hi
        }
        ScanValue::FloatRange(lo, hi) => {
            let v = bytes_to_f64(bytes, size, little);
            v >= *lo && v <= *hi
        }
        ScanValue::Any => true,
    }
}

fn bytes_to_i64(bytes: &[u8], size: usize, little: bool) -> i64 {
    match size {
        1 => bytes[0] as i8 as i64,
        2 => {
            let u = if little { u16::from_le_bytes([bytes[0], bytes[1]]) } else { u16::from_be_bytes([bytes[0], bytes[1]]) };
            u as i16 as i64
        }
        4 => {
            let u = if little { u32::from_le_bytes(bytes.try_into().unwrap()) } else { u32::from_be_bytes(bytes.try_into().unwrap()) };
            u as i32 as i64
        }
        _ => {
            let u = if little { u64::from_le_bytes(bytes.try_into().unwrap()) } else { u64::from_be_bytes(bytes.try_into().unwrap()) };
            u as i64
        }
    }
}

fn bytes_to_f64(bytes: &[u8], size: usize, little: bool) -> f64 {
    match size {
        4 => {
            let u = if little { u32::from_le_bytes(bytes.try_into().unwrap()) } else { u32::from_be_bytes(bytes.try_into().unwrap()) };
            f32::from_bits(u) as f64
        }
        _ => {
            let u = if little { u64::from_le_bytes(bytes.try_into().unwrap()) } else { u64::from_be_bytes(bytes.try_into().unwrap()) };
            f64::from_bits(u)
        }
    }
}

fn align_up(val: u64, alignment: u64) -> u64 {
    if alignment <= 1 {
        return val;
    }
    ((val + alignment - 1) / alignment) * alignment
}

fn filter_regions(regions: Vec<MemoryRegion>, permission_filter: Option<&str>) -> Vec<MemoryRegion> {
    let Some(filter) = permission_filter else {
        return regions;
    };
    let filter_lower = filter.to_lowercase();
    regions
        .into_iter()
        .filter(|r| {
            // Match if every char in the filter appears in perms (e.g. "rw").
            filter_lower.chars().all(|c| r.perms.to_lowercase().contains(c))
        })
        .collect()
}
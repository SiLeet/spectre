/// Memory scanner — pattern-based search through process memory.
use crate::reader::MemoryReader;
use crate::types::{MemoryRegion, ScanMatch, ScanPattern, ScanReport, ScanValue};
use anyhow::Result;
use tracing::{debug, info, warn};

/// Configuration for the scanning engine.
#[derive(Debug, Clone)]
pub struct ScanConfig {
    /// Alignment boundary for search (default 4).
    pub alignment: u32,
    /// Bytes to pull per read batch (default 1 MiB). A batch always holds at
    /// least one whole pattern, so smaller values (including 0) are raised to
    /// the pattern span.
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

/// Scan every region for one pattern.
///
/// Candidates are the addresses `a` with `a % alignment == 0`,
/// `region.start <= a` and `a + span <= region.end`; each one is tested
/// exactly once, in ascending address order. Memory is read in batches of
/// `batch_size` bytes (at least `span`), and each batch starts at the first
/// candidate the previous batch could not test completely, so consecutive
/// reads overlap by fewer than `span` bytes and a structure straddling a
/// batch boundary is still found.
///
/// A pattern with `span == 0` (no fields, or only zero-sized ones) has no
/// bytes to validate and would match every address, so it yields no matches.
///
/// If a read fails, the rest of that region is skipped and the scan moves on
/// to the next region. Retrying the following batches instead would be
/// costly on the adb backend (one shell round trip per failed batch) and
/// would break the web dashboard's cancellation, which relies on a failed
/// read ending the current region.
fn scan_single_pattern(
    reader: &dyn MemoryReader,
    pid: u32,
    regions: &[MemoryRegion],
    pattern: &ScanPattern,
    config: &ScanConfig,
) -> Result<Vec<ScanMatch>> {
    let mut all_matches = Vec::new();
    let span = pattern.span();
    let max_matches = config.max_matches_per_pattern as usize;
    let stride = u64::from(config.alignment.max(1));

    if span == 0 {
        warn!("pattern '{}' spans 0 bytes; nothing to match", pattern.name);
        return Ok(all_matches);
    }
    // `read_bytes` takes a u32 length, so a candidate window must fit one read.
    let Ok(span_len) = u32::try_from(span) else {
        warn!("pattern '{}' spans {span} bytes; too large to scan", pattern.name);
        return Ok(all_matches);
    };
    let read_len = u64::from(config.batch_size.max(span_len));

    for region in regions {
        let Some(first) = region.start.checked_next_multiple_of(stride) else {
            continue;
        };
        let Some(last) = region.end.checked_sub(span) else {
            continue;
        };
        if first > last {
            continue;
        }

        let mut pos = first;
        loop {
            // `pos <= last`, so the read holds at least one full window.
            let read_end = region.end.min(pos.saturating_add(read_len));
            let candidates = (read_end - span - pos) / stride + 1;
            let chunk = match reader.read_bytes(pid, pos, (read_end - pos) as u32) {
                Ok(c) => c,
                Err(e) => {
                    debug!("skip rest of region after failed read at {pos:#x}: {e}");
                    break;
                }
            };

            for i in 0..candidates {
                let idx = (i * stride) as usize;
                if let Some(mut m) = try_match(&chunk, idx, pattern, config.little_endian) {
                    m.address = pos + i * stride;
                    all_matches.push(m);
                    if max_matches > 0 && all_matches.len() >= max_matches {
                        return Ok(all_matches);
                    }
                }
            }

            // Continue at the first candidate this read could not hold.
            match pos.checked_add(candidates * stride) {
                Some(next) if next <= last => pos = next,
                _ => break,
            }
        }
    }
    Ok(all_matches)
}

/// Test the pattern at `chunk[offset..]`.
///
/// Field offsets are laid out relative to the structure start exactly like
/// [`ScanPattern::span`] does (each field is aligned up to its own
/// `alignment`), so the result does not depend on where the chunk begins.
/// The returned field offsets are relative to the structure start; the
/// caller sets the absolute match address.
fn try_match(
    chunk: &[u8],
    offset: usize,
    pattern: &ScanPattern,
    little: bool,
) -> Option<ScanMatch> {
    let mut fields = Vec::with_capacity(pattern.fields.len());
    let mut rel = 0usize;

    for f in &pattern.fields {
        let size = f.value_type.size() as usize;
        rel = rel.next_multiple_of(usize::max(1, f.alignment as usize));
        let at = offset.checked_add(rel)?;
        let bytes = chunk.get(at..at.checked_add(size)?)?;
        if !match_field(bytes, size, &f.value, little) {
            return None;
        }
        fields.push((rel as u32, f.name.clone(), bytes.to_vec()));
        rel += size;
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
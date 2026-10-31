//! `spectre hunt` — automated offset discovery.
//!
//! Dumps a process's hot heaps twice (separated by an interval), then scans
//! both dumps for values of a given numeric type that (a) fall inside a
//! caller-provided range and (b) are byte-identical across both dumps
//! (stable = candidate game value, not allocator/object-table churn).
//!
//! Candidates are scored by how "value-like" their surrounding structure
//! looks (nearby pointer into the 0x72... heap + plausible flag fields),
//! so object-table IDs (repeated values at fixed strides) rank last.

use std::collections::HashMap;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};
use structopt::StructOpt;
use tracing::{debug, info, warn};

use spectre_core::reader::MemoryReader;
use spectre_core::types::MemoryRegion;
use spectre_core::ValueType;

/// `spectre hunt <pid> <min> <max> [options]`
#[derive(StructOpt)]
pub struct HuntArgs {
    /// Target process ID.
    #[structopt(name = "pid")]
    pub pid: u32,

    /// Lower bound of the numeric range to scan (decimal or 0x hex).
    #[structopt(name = "min")]
    pub min: String,

    /// Upper bound of the numeric range to scan (decimal or 0x hex).
    #[structopt(name = "max")]
    pub max: String,

    /// Value type to scan: u32 (default), u64, f32, f64.
    #[structopt(long = "type", default_value = "u32")]
    pub value_type: String,

    /// Seconds between the two dumps (default 5).
    #[structopt(long = "interval", default_value = "5")]
    pub interval: u64,

    /// Bytes per heap to inspect (default 8 MiB per heap, top heaps only).
    #[structopt(long = "bytes", default_value = "8388608")]
    pub bytes: u64,

    /// Only scan the heap(s) whose start address is at least this (hex).
    #[structopt(long = "heap-min")]
    pub heap_min: Option<String>,

    /// Maximum candidates to print (default 25).
    #[structopt(long = "limit", default_value = "25")]
    pub limit: usize,

    /// Print the surrounding 32 bytes of each candidate.
    #[structopt(long = "context")]
    pub context: bool,

    /// Use ADB backend instead of native.
    #[structopt(long = "adb")]
    pub adb: bool,

    /// ADB host (default: 127.0.0.1).
    #[structopt(long = "adb-host")]
    pub adb_host: Option<String>,

    /// ADB port (default: 5555).
    #[structopt(long = "adb-port")]
    pub adb_port: Option<u16>,
}

/// Parse a decimal or 0x hex number.
fn parse_u64(s: &str) -> Result<u64> {
    let t = s.trim();
    if let Some(hex) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
        u64::from_str_radix(hex, 16).context("invalid hex number")
    } else {
        t.parse::<u64>().context("invalid decimal number")
    }
}

struct Candidate {
    addr: u64,
    value: u64,
    score: i32,
    context_bytes: [u8; 32],
    region: String,
}

/// Run the hunt.
pub fn run_hunt(args: HuntArgs) -> Result<()> {
    let min = parse_u64(&args.min)?;
    let max = parse_u64(&args.max)?;
    if min > max {
        bail!("min ({min}) must be <= max ({max})");
    }

    let vt = match args.value_type.as_str() {
        "u32" => ValueType::U32,
        "u64" => ValueType::U64,
        "f32" => ValueType::F32,
        "f64" => ValueType::F64,
        other => bail!("unsupported value type '{other}' (use u32, u64, f32, f64)"),
    };
    let width = vt.size() as usize;
    let heap_min = args
        .heap_min
        .as_deref()
        .map(parse_u64)
        .transpose()?
        .unwrap_or(0);

    let reader: Box<dyn MemoryReader> = if args.adb {
        let host = args.adb_host.unwrap_or_else(|| "127.0.0.1".to_owned());
        let port = args.adb_port.unwrap_or(5555);
        let serial = format!("{host}:{port}");
        Box::new(spectre_adb::AdbReader::with_serial(&host, port, &serial))
    } else {
        spectre_native::create_default_reader()
    };

    // Pick candidate heaps: large anonymous/mmap rw regions >= heap_min.
    let regions = reader.memory_regions(args.pid)?;
    let mut heaps: Vec<MemoryRegion> = regions
        .iter()
        .filter(|r| r.perms.starts_with("rw") && r.path.is_none() && r.start >= heap_min)
        .cloned()
        .collect();
    heaps.sort_by_key(|r| r.end - r.start);
    heaps.reverse();

    if heaps.is_empty() {
        bail!("no readable anonymous rw regions found for pid {}", args.pid);
    }
    info!(
        "hunting {} in [{min}..{max}] over {} candidate heap(s), {:.1} MiB each",
        args.value_type,
        heaps.len().min(8),
        args.bytes as f64 / 1048576.0
    );

    let mut all: Vec<Candidate> = Vec::new();
    let deadline = Instant::now() + Duration::from_secs(600);

    for heap in heaps.iter().take(8) {
        let size = (heap.end - heap.start).min(args.bytes);
        if size < width as u64 {
            continue;
        }
        // Read region A.
        let buf_a = reader.read_bytes(args.pid, heap.start, size as u32)?;
        info!("dumped {:.1} MiB @ {:#x} (A)", size as f64 / 1048576.0, heap.start);
        // Wait, then read region B.
        thread::sleep(Duration::from_secs(args.interval));
        let buf_b = reader.read_bytes(args.pid, heap.start, size as u32)?;
        info!("dumped {:.1} MiB @ {:#x} (B)", size as f64 / 1048576.0, heap.start);

        if buf_a.len() != buf_b.len() {
            warn!("size mismatch at {:#x}, skipping", heap.start);
            continue;
        }

        // Scan aligned slots: value in range and identical in A and B.
        let mut slots = 0usize;
        // Count value frequency across the whole dump; unique values are
        // far more likely to be a player value than object-table IDs.
        let mut frequency: HashMap<u64, usize> = HashMap::new();
        for off in (0..buf_a.len() - width).step_by(width) {
            let v = read_slot(&buf_a, off, width);
            if v >= min && v <= max {
                *frequency.entry(v).or_insert(0) += 1;
            }
        }
        for off in (0..buf_a.len() - width).step_by(width) {
            slots += 1;
            let va = read_slot(&buf_a, off, width);
            let vb = read_slot(&buf_b, off, width);
            if va != vb || va < min || va > max {
                continue;
            }
            let addr = heap.start + off as u64;
            let mut ctx = [0u8; 32];
            let ctx_off = off.saturating_sub(8);
            let n = (buf_a.len() - ctx_off).min(32);
            ctx[..n].copy_from_slice(&buf_a[ctx_off..ctx_off + n]);
            let freq = *frequency.get(&va).unwrap_or(&0);
            let score = structure_score(&buf_a, off, width, va, min, max)
                + if freq == 1 { 4 } else if freq <= 3 { 1 } else { -6 };
            all.push(Candidate {
                addr,
                value: va,
                score,
                context_bytes: ctx,
                region: format!("{:#x}", heap.start),
            });
            if Instant::now() > deadline {
                warn!("time budget exceeded, stopping early");
                break;
            }
        }
        debug!("scanned {slots} slots @ {:#x}", heap.start);
    }

    if all.is_empty() {
        println!("no stable values in [{min}..{max}] found (try --heap-min, --bytes, or a wider range)");
        return Ok(());
    }

    // Sort by score desc, then address.
    all.sort_by(|a, b| b.score.cmp(&a.score).then(a.addr.cmp(&b.addr)));
    let shown = all.len().min(args.limit);
    println!("{shown} candidate(s) of {} stable values (top by structure score):", all.len());
    println!("{:<18} {:>14}  REGION", "ADDRESS", "VALUE");
    for c in &all[..shown] {
        println!(
            "{:<18} {:>14}  {}{}",
            format!("{:#x}", c.addr),
            c.value,
            c.region,
            if args.context {
                format!("  ctx: {}", hex_ctx(&c.context_bytes))
            } else {
                String::new()
            }
        );
    }
    println!();
    println!(
        "next: change the value in-game, re-run `spectre dump` + `dumpdiff`, and check which address moved"
    );
    Ok(())
}

/// Read a width-byte little-endian slot.
pub(crate) fn read_slot(buf: &[u8], off: usize, width: usize) -> u64 {
    let mut v = 0u64;
    for i in 0..width {
        v |= (buf[off + i] as u64) << (8 * i);
    }
    v
}

/// Score how value-like a slot's neighborhood looks.
/// Rewards: a nearby pointer into the 0x72... heap, small flag fields,
/// being a single occurrence (not part of an object table stride).
#[allow(clippy::too_many_arguments)]
fn structure_score(buf: &[u8], off: usize, width: usize, value: u64, min: u64, max: u64) -> i32 {
    let mut score = 0i32;
    let window = 64usize;
    let start = off.saturating_sub(window);
    let end = (off + window + width).min(buf.len());

    // Pointer nearby: look for 0x72...-ish 8-byte values in the window.
    let mut pointer_nearby = false;
    // Neighbors whose VALUE ALSO sits in the scanned range at a fixed-ish
    // stride are the signature of an object/ID table — penalize them, even
    // when the numeric values themselves differ (table rows, not a player slot).
    let mut in_range_neighbors = 0usize;
    for w in (start..end.saturating_sub(8)).step_by(8) {
        if w == off || (w + width > off && w < off + width) {
            continue;
        }
        let p = read_slot(buf, w, 8);
        if (0x7200_0000_0000..0x7300_0000_0000).contains(&p) {
            pointer_nearby = true;
        }
        let nv = read_slot(buf, w, width);
        if (min..=max).contains(&nv) {
            in_range_neighbors += 1;
        }
    }

    if pointer_nearby {
        score += 3;
    }
    if in_range_neighbors == 0 {
        score += 2; // isolated: no neighbor in the scanned range
    } else if in_range_neighbors >= 2 {
        score -= 6; // table pattern: several in-range neighbors
    } else {
        score -= 1;
    }

    // Modest/round-ish values (currencies are rarely huge) get a small bump.
    if value < 10_000_000 {
        score += 1;
    }
    score
}

/// Render context bytes as hex.
fn hex_ctx(ctx: &[u8; 32]) -> String {
    ctx.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(" ")
}
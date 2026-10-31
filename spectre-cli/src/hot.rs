//! `spectre hot` — on-device byte-pattern scan over ADB.
//!
//! The device greps its own memory (`dd | xxd | tr | grep`), so only match
//! offsets cross the adb pipe instead of whole hex dumps. That makes
//! before/after diff cycles take seconds instead of minutes.

use anyhow::{Result, anyhow, bail};
use structopt::StructOpt;
use tracing::info;

use spectre_adb::reader::GREP_MAX_PATTERN;
use spectre_core::reader::MemoryReader;
use spectre_core::types::MemoryRegion;

/// Bytes per on-device grep call (one adb round trip each).
const HOT_CHUNK: u32 = 1 << 20;

/// `spectre hot <pid> <hex> --adb [options]`
#[derive(StructOpt)]
pub struct HotArgs {
    /// Target process ID.
    #[structopt(name = "pid")]
    pub pid: u32,

    /// Byte pattern as hex in memory order, e.g. "b8f30300" or "b8 f3 03 00".
    #[structopt(name = "hex")]
    pub hex: String,

    /// Use ADB backend (required: the scan runs on the device).
    #[structopt(long = "adb")]
    pub adb: bool,

    /// ADB host (default: 127.0.0.1).
    #[structopt(long = "adb-host")]
    pub adb_host: Option<String>,

    /// ADB port (default: 5555).
    #[structopt(long = "adb-port")]
    pub adb_port: Option<u16>,

    /// Only report matches at or above this address (hex with 0x, or decimal).
    #[structopt(long = "base", default_value = "0")]
    pub base: String,

    /// Stop after N matches (0 = unlimited).
    #[structopt(long = "limit", default_value = "0")]
    pub limit: usize,

    /// Output as JSON (array of 0x-hex addresses).
    #[structopt(long = "json")]
    pub json: bool,
}

/// Parse a hex byte pattern; whitespace between digits is ignored.
fn parse_hex_pattern(s: &str) -> Result<Vec<u8>> {
    let digits: String = s.chars().filter(|c| !c.is_whitespace()).collect();
    if digits.is_empty()
        || !digits.len().is_multiple_of(2)
        || !digits.chars().all(|c| c.is_ascii_hexdigit())
    {
        bail!("invalid hex pattern '{s}' (expected an even number of hex digits, e.g. b8f30300)");
    }
    if digits.len() / 2 > GREP_MAX_PATTERN {
        bail!("hex pattern too long (max {GREP_MAX_PATTERN} bytes)");
    }
    (0..digits.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&digits[i..i + 2], 16).map_err(Into::into))
        .collect()
}

/// Anonymous rw regions (unnamed or `[anon:...]`) that reach `base`,
/// clipped to start at `base`.
fn hot_regions(regions: Vec<MemoryRegion>, base: u64) -> Vec<MemoryRegion> {
    regions
        .into_iter()
        .filter(|r| {
            r.perms.starts_with("rw")
                && r.end > base
                && r.path.as_deref().is_none_or(|p| p.starts_with("[anon:"))
        })
        .map(|mut r| {
            r.start = r.start.max(base);
            r
        })
        .collect()
}

/// Run the on-device hot scan.
pub fn run_hot(args: HotArgs) -> Result<()> {
    if !args.adb {
        bail!(
            "`spectre hot` greps on the device and needs --adb (use `spectre search` for native)"
        );
    }
    let pattern = parse_hex_pattern(&args.hex)?;
    let base = super::parse_u64(&args.base).ok_or_else(|| {
        anyhow!(
            "invalid --base '{}' (use 0x-prefixed hex or decimal)",
            args.base
        )
    })?;

    let host = args.adb_host.unwrap_or_else(|| "127.0.0.1".to_owned());
    let port = args.adb_port.unwrap_or(5555);
    let serial = format!("{host}:{port}");
    let reader = spectre_adb::AdbReader::with_serial(&host, port, &serial);

    let regions = hot_regions(reader.memory_regions(args.pid)?, base);
    if regions.is_empty() {
        bail!(
            "no readable anonymous rw regions at or above {base:#x} for pid {}",
            args.pid
        );
    }
    let total: u64 = regions.iter().map(MemoryRegion::size).sum();
    info!(
        "hot scan: {} region(s), {:.1} MiB, pattern {}",
        regions.len(),
        total as f64 / 1048576.0,
        args.hex
    );

    let addrs: Vec<u64> = reader
        .grep_memory(args.pid, &regions, &[pattern], HOT_CHUNK, args.limit)?
        .into_iter()
        .map(|(a, _)| a)
        .collect();

    if args.json {
        let hex: Vec<String> = addrs.iter().map(|a| format!("{a:#x}")).collect();
        println!("{}", serde_json::to_string_pretty(&hex)?);
    } else {
        for a in &addrs {
            println!("{}", super::fmt_addr(*a));
        }
        println!("-- {} match(es)", addrs.len());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(start: u64, end: u64, perms: &str, path: Option<&str>) -> MemoryRegion {
        MemoryRegion {
            start,
            end,
            perms: perms.to_owned(),
            path: path.map(str::to_owned),
        }
    }

    #[test]
    fn hex_pattern_accepts_spaces_and_case() {
        assert_eq!(
            parse_hex_pattern("b8 F3 03 00").unwrap(),
            vec![0xb8, 0xf3, 0x03, 0x00]
        );
    }

    #[test]
    fn hex_pattern_rejects_shell_and_odd_input() {
        for bad in ["", "abc", "0xb8f3", "b8f3;rm", "'00'", "zz"] {
            assert!(parse_hex_pattern(bad).is_err(), "{bad:?} must be rejected");
        }
        assert!(parse_hex_pattern(&"00".repeat(GREP_MAX_PATTERN + 1)).is_err());
    }

    #[test]
    fn hot_regions_keeps_anonymous_rw_above_base() {
        let all = vec![
            region(0x1000, 0x2000, "rw-p", None),
            region(0x3000, 0x4000, "rw-p", Some("[anon:scudo:primary]")),
            region(0x5000, 0x6000, "r--p", None),
            region(0x7000, 0x8000, "rw-p", Some("/system/lib64/libc.so")),
            region(0x9000, 0xa000, "rw-p", None),
        ];
        let starts: Vec<u64> = hot_regions(all.clone(), 0)
            .iter()
            .map(|r| r.start)
            .collect();
        assert_eq!(starts, vec![0x1000, 0x3000, 0x9000]);
        let starts: Vec<u64> = hot_regions(all, 0x3800).iter().map(|r| r.start).collect();
        assert_eq!(starts, vec![0x3800, 0x9000]);
    }

    #[test]
    fn hot_requires_adb_before_touching_a_device() {
        let args = HotArgs::from_iter(["hot", "1", "00"]);
        let err = run_hot(args).unwrap_err().to_string();
        assert!(err.contains("--adb"), "{err}");
    }
}

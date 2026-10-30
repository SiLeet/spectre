use anyhow::Result;
/// Process discovery and /proc/<pid>/maps parsing for ADB-backed readers.
///
/// Parses `adb shell ps` output to find processes by name,
/// and `/proc/<pid>/maps` output into structured MemoryRegion records.
use spectre_core::types::{MemoryRegion, ProcessInfo};

// ── PS Output Parsing ──────────────────────────────────────────────────────

/// Parse the output of `adb shell ps` into a vector of ProcessInfo.
///
/// Handles both the busybox/toybox `ps` columnar output, e.g.:
///
/// ```text
///   PID  PPID   VSZ  RSS USER     COMMAND
///    1     0  1232  456 root     /sbin/init
///  123   122  7890 1234 u0_123   /data/game/executable
/// ```
///
/// The header line (containing "PID") is skipped.  PID is the first
/// whitespace-delimited token; the command name is the last token.
pub fn parse_ps_output(output: &str) -> Result<Vec<ProcessInfo>> {
    let mut processes: Vec<ProcessInfo> = Vec::new();

    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Skip header lines containing "PID" as a column label.
        if trimmed.contains("PID") && !trimmed.chars().all(|c| c.is_ascii_digit() || c.is_whitespace())
        {
            continue;
        }

        // Split on any amount of whitespace.
        let tokens: Vec<&str> = trimmed.split_whitespace().collect();

        if tokens.len() < 2 {
            continue;
        }

        // First token should be PID.
        let Ok(pid) = tokens[0].parse::<u32>() else {
            continue;
        };

        // Last token is the command name / path.
        let name = tokens[tokens.len() - 1].to_owned();

        processes.push(ProcessInfo { pid, name });
    }

    Ok(processes)
}

// ── /proc/<pid>/maps Parsing ──────────────────────────────────────────────

/// Parse the output of `cat /proc/<pid>/maps` into MemoryRegion records.
///
/// Format per line:
///
/// ```text
/// start-end   perms  offset  dev    inode   [path]
/// 08048000-08056000 r-xp 00000000 03:0c 64593  /system/lib/libc.so
/// ```
///
/// The path column is optional (anonymous mappings have no path).
pub fn parse_maps_output(output: &str) -> Result<Vec<MemoryRegion>> {
    let mut regions: Vec<MemoryRegion> = Vec::new();

    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        if let Some(region) = try_parse_maps_line(trimmed) {
            regions.push(region);
        }
    }

    Ok(regions)
}

/// Attempt to parse a single /proc/<pid>/maps line.
fn try_parse_maps_line(line: &str) -> Option<MemoryRegion> {
    // Split on any amount of whitespace.
    let tokens: Vec<&str> = line.split_whitespace().collect();

    if tokens.len() < 5 {
        return None;
    }

    // Token 0: "start-end"
    let addr_range = tokens[0];
    let mut addr_parts = addr_range.split('-');
    let start_str = addr_parts.next()?;
    let end_str = addr_parts.next()?;
    if addr_parts.next().is_some() {
        return None;
    }

    let start = u64::from_str_radix(start_str, 16).ok()?;
    let end = u64::from_str_radix(end_str, 16).ok()?;

    // Token 1: permissions string (e.g. "r-xp")
    let perms = tokens[1].to_owned();

    // Token 2-4: offset, dev, inode (we don't need these for the struct,
    // but we must skip past them to reach the optional path).

    // Token 5+ (if present): mapped file path.
    let path: Option<String> = if tokens.len() >= 6 {
        Some(tokens[5..].join(" "))
    } else {
        None
    };

    Some(MemoryRegion {
        start,
        end,
        perms,
        path,
    })
}

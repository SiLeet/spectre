use anyhow::Result;
/// Process discovery and /proc/<pid>/maps parsing for ADB-backed readers.
///
/// Parses `adb shell ps` output to find processes by name,
/// and `/proc/<pid>/maps` output into structured MemoryRegion records.
use spectre_core::types::{MemoryRegion, ProcessInfo};

// ── PS Output Parsing ──────────────────────────────────────────────────────

/// Parse the output of `adb shell ps` into a vector of ProcessInfo.
///
/// Handles both the busybox/toybox `ps` columnar output. The Android toybox
/// `ps` puts USER first (PID second), while the Linux `ps` puts PID first —
/// the header line is used to locate the PID column by name, falling back
/// to "first whitespace token that parses as u32".
///
/// ```text
/// USER     PID   PPID  VSZ   RSS  WCHAN  ADDR  S    NAME
/// root       1     0  1232  456  ...    0     S    /sbin/init
/// u0_a83   123   122  7890 1234  ...    0     S    com.game.package
/// ```
pub fn parse_ps_output(output: &str) -> Result<Vec<ProcessInfo>> {
    let mut processes: Vec<ProcessInfo> = Vec::new();
    let mut pid_index: Option<usize> = None;

    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let tokens: Vec<&str> = trimmed.split_whitespace().collect();
        if tokens.is_empty() {
            continue;
        }

        // Header line: locate the column that says PID.
        if pid_index.is_none()
            && let Some(idx) = tokens.iter().position(|t| t.eq_ignore_ascii_case("PID"))
        {
            pid_index = Some(idx);
            continue;
        }

        // Resolve the PID column:
        // 1. explicit header position, else
        // 2. the FIRST whitespace token that parses as u32
        let pid = if let Some(idx) = pid_index {
            if idx < tokens.len() {
                tokens[idx].parse::<u32>().ok()
            } else {
                None
            }
        } else {
            tokens.iter().find_map(|t| t.parse::<u32>().ok())
        };

        let Some(pid) = pid else {
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


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_android_ps_with_user_first() {
        let out = "USER     PID   PPID  VSZ    RSS   WCHAN          ADDR  S NAME\n\
                   root       1     0  15248  3304  0               0    S init\n\
                   u0_a83   5258  1887 26812080 1630000 ep_poll      0    S com.farlightgames.igame.gp\n";
        let procs = parse_ps_output(out).unwrap();
        assert_eq!(procs.len(), 2, "both Android ps lines must parse");
        assert_eq!(procs[0].pid, 1);
        assert_eq!(procs[0].name, "init");
        assert_eq!(procs[1].pid, 5258);
        assert_eq!(procs[1].name, "com.farlightgames.igame.gp");
    }

    #[test]
    fn parses_linux_ps_with_pid_first() {
        let out = "  PID  PPID   VSZ  RSS USER     COMMAND\n\
                    1     0  1232  456 root     /sbin/init\n\
                  123   122  7890 1234 u0_123   /data/game/executable\n";
        let procs = parse_ps_output(out).unwrap();
        assert_eq!(procs.len(), 2);
        assert_eq!(procs[0].pid, 1);
        assert_eq!(procs[1].pid, 123);
    }

    #[test]
    fn parses_headerless_output_via_first_u32() {
        let out = "root 42 0 10 10 0 0 S kthreadd\n";
        let procs = parse_ps_output(out).unwrap();
        assert_eq!(procs.len(), 1);
        assert_eq!(procs[0].pid, 42);
        assert_eq!(procs[0].name, "kthreadd");
    }
}

//! Linux process memory reader via `/proc`.
//!
//! - `/proc/<pid>/maps` for memory regions
//! - `/proc/<pid>/mem` for raw reads (requires same UID or root)
//! - `/proc/<pid>/comm` for the process name

use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_core::scanner::{scan_memory, ScanConfig};
use spectre_core::MemoryReader;
use anyhow::{anyhow, Context, Result};
use std::fs;
use std::os::unix::fs::FileExt;

/// Linux native backend.
#[derive(Debug, Default)]
pub struct LinuxReader;

impl LinuxReader {
    pub fn new() -> Self {
        LinuxReader
    }

    fn mem_path(pid: u32) -> String {
        format!("/proc/{pid}/mem")
    }

    fn read_comm(pid: u32) -> Option<String> {
        fs::read_to_string(format!("/proc/{pid}/comm"))
            .ok()
            .map(|s| s.trim().to_owned())
    }

    /// Open `/proc/<pid>/mem` for reading, returning an error with a hint
    /// when permission is denied.
    fn open_mem(pid: u32) -> Result<fs::File> {
        fs::File::open(Self::mem_path(pid)).map_err(|e| Self::mem_error(pid, e))
    }

    /// EPERM and EACCES both map to `ErrorKind::PermissionDenied`.
    fn mem_error(pid: u32, e: std::io::Error) -> anyhow::Error {
        if e.kind() == std::io::ErrorKind::PermissionDenied {
            anyhow!(
                "/proc/{pid}/mem: permission denied (need root or ptrace): {e}. \
                 Try `sudo setcap cap_sys_ptrace=ep $(which spectre)`"
            )
        } else {
            anyhow!("/proc/{pid}/mem: {e}")
        }
    }
}

impl MemoryReader for LinuxReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::NativeLinux
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        let all = self.list_processes()?;
        let lower = name.to_lowercase();
        Ok(all.into_iter().filter(|p| p.name.to_lowercase().contains(&lower)).collect())
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        let mut out = Vec::new();
        let entries = fs::read_dir("/proc").context("cannot read /proc")?;
        for entry in entries.flatten() {
            let name = entry.file_name();
            let name_str = name.to_string_lossy();
            let Ok(pid) = name_str.parse::<u32>() else {
                continue;
            };
            if let Some(comm) = Self::read_comm(pid) {
                out.push(ProcessInfo { pid, name: comm });
            }
        }
        Ok(out)
    }

    fn process_name(&self, pid: u32) -> Result<Option<String>> {
        Ok(Self::read_comm(pid))
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        let map_text = fs::read_to_string(format!("/proc/{pid}/maps"))
            .with_context(|| format!("cannot read /proc/{pid}/maps"))?;
        // Only readable regions are worth scanning.
        Ok(map_text
            .lines()
            .filter_map(parse_maps_line)
            .filter(|r| r.perms.contains('r'))
            .collect())
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        if size == 0 {
            return Ok(Vec::new());
        }
        // pread (read_at) at the virtual address; no alignment needed.
        let file = Self::open_mem(pid)?;
        let mut buf = vec![0u8; size as usize];
        let mut filled = 0usize;
        while filled < buf.len() {
            match file.read_at(&mut buf[filled..], address + filled as u64) {
                Ok(0) => break,
                Ok(n) => filled += n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
                // Range runs into an unmapped page: fail like ReadProcessMemory.
                Err(_) if filled > 0 => break,
                Err(e) => {
                    return Err(Self::mem_error(pid, e).context(format!("read at {address:#x}")));
                }
            }
        }
        // Callers (typed reads) rely on exactly `size` bytes.
        if filled < buf.len() {
            return Err(anyhow!(
                "short read at {address:#x}: got {filled} of {size} bytes"
            ));
        }
        Ok(buf)
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        let config = ScanConfig { little_endian: little, ..Default::default() };
        scan_memory(self, pid, patterns, &config)
    }
}

/// Parse one `/proc/<pid>/maps` line: `start-end perms offset dev inode [path]`.
fn parse_maps_line(line: &str) -> Option<MemoryRegion> {
    let mut parts = line.split_whitespace();
    let (start_s, end_s) = parts.next()?.split_once('-')?;
    let start = u64::from_str_radix(start_s, 16).ok()?;
    let end = u64::from_str_radix(end_s, 16).ok()?;
    let perms = parts.next().unwrap_or("---").to_owned();
    // Skip the offset/dev/inode columns to reach the optional path,
    // which may itself contain spaces (same as the ADB parser).
    let rest: Vec<&str> = parts.skip(3).collect();
    let path = (!rest.is_empty()).then(|| rest.join(" "));
    Some(MemoryRegion {
        start,
        end,
        perms,
        path,
    })
}

#[cfg(test)]
mod tests {
    use super::parse_maps_line;

    #[test]
    fn maps_line_keeps_path_with_spaces() {
        let r = parse_maps_line("7f00-7f01 r--p 00000000 08:01 123 /tmp/my file (deleted)")
            .expect("parse");
        assert_eq!((r.start, r.end), (0x7f00, 0x7f01));
        assert_eq!(r.perms, "r--p");
        assert_eq!(r.path.as_deref(), Some("/tmp/my file (deleted)"));
    }

    #[test]
    fn maps_line_anonymous_and_garbage() {
        let r = parse_maps_line("1000-2000 rw-p 00000000 00:00 0").expect("parse");
        assert_eq!(r.path, None);
        assert!(parse_maps_line("").is_none());
        assert!(parse_maps_line("zzzz-2000 rw-p 0 00:00 0").is_none());
    }
}

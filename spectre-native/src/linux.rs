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
use std::path::Path;

const PAGE_SIZE: u64 = 4096;

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
        fs::File::open(Self::mem_path(pid)).map_err(|e| {
            anyhow!(
                "{e}. Note: reading /proc/{pid}/mem needs the same UID or root; \
                 try `sudo setcap cap_sys_ptrace=ep $(which spectre)`"
            )
        })
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
        let mut regions = Vec::new();
        for line in map_text.lines() {
            // Format: start-end perms offset dev inode [path]
            let mut parts = line.split_whitespace();
            let Some(range) = parts.next() else { continue };
            let Some((start_s, end_s)) = range.split_once('-') else { continue };
            let (Ok(start), Ok(end)) = (
                u64::from_str_radix(start_s, 16),
                u64::from_str_radix(end_s, 16),
            ) else {
                continue;
            };
            let perms = parts.next().unwrap_or("---").to_owned();
            // Skip the offset/dev/inode columns to reach the optional path.
            let _ = parts.next();
            let _ = parts.next();
            let _ = parts.next();
            let path = parts.next().map(|s| s.to_owned());
            // Only anonymous/heap or unexpected regions that are readable.
            if perms.contains('r') {
                regions.push(MemoryRegion { start, end, perms, path });
            }
        }
        Ok(regions)
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        if size == 0 {
            return Ok(Vec::new());
        }
        // Start at a page boundary and rewind to the requested address,
        // because pread on /proc/pid/mem must be page-aligned.
        let page_start = address & !(PAGE_SIZE - 1);
        let offset_in_page = (address - page_start) as usize;
        let total = size as usize + offset_in_page;

        let mut file = Self::open_mem(pid)?;
        use std::io::{Read, Seek, SeekFrom};
        file.seek(SeekFrom::Start(page_start))?;

        let mut buf = vec![0u8; total];
        let mut filled = 0usize;
        while filled < total {
            let n = file.read(&mut buf[filled..])?;
            if n == 0 {
                break;
            }
            filled += n;
        }
        if filled <= offset_in_page {
            return Err(anyhow!("short read at {address:#x}: got {filled} bytes"));
        }
        Ok(buf[offset_in_page..offset_in_page + size as usize].to_vec())
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        let mut config = ScanConfig::default();
        config.little_endian = little;
        scan_memory(self, pid, patterns, &config)
    }
}
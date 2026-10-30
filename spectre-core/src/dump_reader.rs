//! Offline memory-dump reader.
//!
//! [`DumpFileReader`] exposes a raw bytes buffer (e.g. a file saved by
//! `spectre dump`) through the [`MemoryReader`] trait, so scans, bots, and
//! scripts can run against saved snapshots without a live process. Useful for
//! forensic analysis, offset discovery, or testing against a controlled
//! dataset.
use crate::reader::MemoryReader;
use crate::scanner::{scan_memory, ScanConfig};
use crate::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use anyhow::{anyhow, Context, Result};
use std::path::Path;

/// Reads memory from an in-memory byte buffer laid out at a virtual base.
#[derive(Debug, Clone)]
pub struct DumpFileReader {
    /// Virtual address where byte 0 of `data` starts.
    base: u64,
    /// Raw dump contents.
    data: Vec<u8>,
    /// Name reported for the (fake) process this dump represents.
    process_name: String,
}

impl DumpFileReader {
    /// Create a reader over an existing buffer.
    pub fn from_bytes(base: u64, data: Vec<u8>, process_name: impl Into<String>) -> Self {
        Self { base, data, process_name: process_name.into() }
    }

    /// Load a raw binary dump file: `address` is the virtual address of the
    /// first byte in the file.
    pub fn from_file(path: &Path, base: u64, process_name: impl Into<String>) -> Result<Self> {
        let data = std::fs::read(path)
            .with_context(|| format!("failed to read dump file '{}'", path.display()))?;
        Ok(Self::from_bytes(base, data, process_name))
    }

    /// Base address used by the dump.
    pub fn base(&self) -> u64 {
        self.base
    }

    /// Number of bytes in the dump.
    pub fn len(&self) -> usize {
        self.data.len()
    }

    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    fn offset_of(&self, address: u64) -> Option<usize> {
        if address >= self.base && address < self.base + self.data.len() as u64 {
            Some((address - self.base) as usize)
        } else {
            None
        }
    }
}

impl MemoryReader for DumpFileReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        let lower = name.to_lowercase();
        Ok(vec![ProcessInfo {
            pid: 0,
            name: self.process_name.clone(),
        }]
        .into_iter()
        .filter(|p| p.name.to_lowercase().contains(&lower))
        .collect())
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        Ok(vec![ProcessInfo { pid: 0, name: self.process_name.clone() }])
    }

    fn process_name(&self, _pid: u32) -> Result<Option<String>> {
        Ok(Some(self.process_name.clone()))
    }

    fn memory_regions(&self, _pid: u32) -> Result<Vec<MemoryRegion>> {
        Ok(vec![MemoryRegion {
            start: self.base,
            end: self.base + self.data.len() as u64,
            perms: "rw-".to_owned(),
            path: None,
        }])
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        let off = self
            .offset_of(address)
            .ok_or_else(|| anyhow!("address {address:#x} outside dump range"))?;
        let end = off + size as usize;
        if end > self.data.len() {
            return Err(anyhow!(
                "read {size} bytes at {address:#x} exceeds dump ({} bytes)",
                self.data.len()
            ));
        }
        Ok(self.data[off..end].to_vec())
    }

    fn scan(&self, _pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        let config = ScanConfig { little_endian: little, ..Default::default() };
        scan_memory(self, _pid, patterns, &config)
    }
}
//! Optionally wraps a platform backend as a [`NativeReader`] enum
//! so callers can use a single type on any OS.

use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_core::MemoryReader;
use anyhow::Result;

#[cfg(windows)]
use crate::windows::WindowsReader;
#[cfg(unix)]
use crate::linux::LinuxReader;

/// Native memory reader: dispatches to the current platform's backend.
#[derive(Debug)]
pub enum NativeReader {
    #[cfg(windows)]
    Windows(WindowsReader),
    #[cfg(unix)]
    Linux(LinuxReader),
}

impl MemoryReader for NativeReader {
    fn backend_kind(&self) -> BackendKind {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(_) => BackendKind::NativeWindows,
            #[cfg(unix)]
            NativeReader::Linux(_) => BackendKind::NativeLinux,
        }
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.find_process(name),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.find_process(name),
        }
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.list_processes(),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.list_processes(),
        }
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.memory_regions(pid),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.memory_regions(pid),
        }
    }

    fn process_name(&self, pid: u32) -> Result<Option<String>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.process_name(pid),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.process_name(pid),
        }
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.read_bytes(pid, address, size),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.read_bytes(pid, address, size),
        }
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        match self {
            #[cfg(windows)]
            NativeReader::Windows(r) => r.scan(pid, patterns, little),
            #[cfg(unix)]
            NativeReader::Linux(r) => r.scan(pid, patterns, little),
        }
    }
}

/// Return the backend kind for the *current* platform, without instantiating.
pub fn native_backend_kind() -> BackendKind {
    #[cfg(windows)]
    {
        BackendKind::NativeWindows
    }
    #[cfg(unix)]
    {
        BackendKind::NativeLinux
    }
}

/// Create the platform-native reader (boxed as a trait object).
pub fn create_default_reader() -> Box<dyn MemoryReader> {
    #[cfg(windows)]
    {
        Box::new(NativeReader::Windows(WindowsReader::new()))
    }
    #[cfg(unix)]
    {
        Box::new(NativeReader::Linux(LinuxReader::new()))
    }
}
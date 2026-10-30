//! Cancel blocking reader work once the HTTP request that started it is gone.
//!
//! `spawn_blocking` tasks cannot be aborted, and `scan_memory` has no
//! cancellation hook. Instead the scan is given a [`CancellableReader`]: when
//! the handler future is dropped (client disconnected), its [`CancelOnDrop`]
//! guard flips a shared flag and every further read fails. `scan_memory`
//! skips a region on the first failed read, so an orphaned scan winds down
//! after at most one more batch per remaining region instead of running to
//! the end.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use anyhow::{Result, bail};
use spectre_core::{
    BackendKind, MemoryReader, MemoryRegion, ProcessInfo, ScanConfig, ScanPattern, ScanReport,
    scan_memory,
};

/// Wrap `inner` in a reader that stops working once the returned guard drops.
pub(crate) fn cancellable(inner: Arc<dyn MemoryReader>) -> (CancellableReader, CancelOnDrop) {
    let cancelled = Arc::new(AtomicBool::new(false));
    (
        CancellableReader {
            inner,
            cancelled: Arc::clone(&cancelled),
        },
        CancelOnDrop(cancelled),
    )
}

/// Sets the cancellation flag of its [`CancellableReader`] when dropped.
#[derive(Debug)]
pub(crate) struct CancelOnDrop(Arc<AtomicBool>);

impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Relaxed);
    }
}

/// Delegating [`MemoryReader`] whose region and memory reads fail after
/// cancellation.
#[derive(Debug)]
pub(crate) struct CancellableReader {
    inner: Arc<dyn MemoryReader>,
    cancelled: Arc<AtomicBool>,
}

impl CancellableReader {
    fn ensure_live(&self) -> Result<()> {
        if self.cancelled.load(Ordering::Relaxed) {
            bail!("request cancelled");
        }
        Ok(())
    }
}

impl MemoryReader for CancellableReader {
    fn backend_kind(&self) -> BackendKind {
        self.inner.backend_kind()
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        self.inner.find_process(name)
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        self.inner.list_processes()
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        self.ensure_live()?;
        self.inner.memory_regions(pid)
    }

    fn process_name(&self, pid: u32) -> Result<Option<String>> {
        self.inner.process_name(pid)
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        self.ensure_live()?;
        self.inner.read_bytes(pid, address, size)
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        // Scan through `self` so the cancellation flag is honoured.
        let config = ScanConfig {
            little_endian: little,
            ..Default::default()
        };
        scan_memory(self, pid, patterns, &config)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug)]
    struct Zeroes;

    impl MemoryReader for Zeroes {
        fn backend_kind(&self) -> BackendKind {
            BackendKind::DumpFile
        }
        fn find_process(&self, _name: &str) -> Result<Vec<ProcessInfo>> {
            Ok(Vec::new())
        }
        fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
            Ok(Vec::new())
        }
        fn memory_regions(&self, _pid: u32) -> Result<Vec<MemoryRegion>> {
            Ok(Vec::new())
        }
        fn process_name(&self, _pid: u32) -> Result<Option<String>> {
            Ok(None)
        }
        fn read_bytes(&self, _pid: u32, _address: u64, size: u32) -> Result<Vec<u8>> {
            Ok(vec![0; size as usize])
        }
        fn scan(&self, _: u32, _: Vec<ScanPattern>, _: bool) -> Result<Vec<ScanReport>> {
            Ok(Vec::new())
        }
    }

    #[test]
    fn reads_fail_after_guard_drops() {
        let (reader, guard) = cancellable(Arc::new(Zeroes));
        assert_eq!(reader.read_bytes(1, 0, 4).unwrap(), vec![0; 4]);
        assert!(reader.memory_regions(1).is_ok());
        drop(guard);
        assert!(reader.read_bytes(1, 0, 4).is_err());
        assert!(reader.memory_regions(1).is_err());
        // Listing stays available; only memory access is cut off.
        assert!(reader.list_processes().is_ok());
    }
}

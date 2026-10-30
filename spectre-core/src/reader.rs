/// MemoryReader trait — the abstract interface every Spectre backend implements.
use crate::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport, ValueType};
use anyhow::Result;
use std::fmt::Debug;

/// How errors propagate from backends:
/// all methods return `anyhow::Result`, so backends can surface
/// OS, ADB, or permission errors uniformly.
pub trait MemoryReader: Send + Sync + Debug {
    /// Which backend this reader is backed by.
    fn backend_kind(&self) -> BackendKind;

    // ── Process Discovery ───────────────────────────────────────────

    /// Find processes whose name contains `name` (case-insensitive).
    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>>;

    /// List all processes visible to this backend.
    fn list_processes(&self) -> Result<Vec<ProcessInfo>>;

    /// Memory region map for a process.
    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>>;

    /// Resolve a process name from a PID (None if unknown / no permission).
    fn process_name(&self, pid: u32) -> Result<Option<String>>;

    // ── Raw Memory Reading ───────────────────────────────────────────

    /// Read exactly `size` bytes from `address` (backend must handle errors).
    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>>;

    // ── Typed Reads (defaults on top of read_bytes) ──────────────────

    fn read_u8(&self, pid: u32, address: u64) -> Result<u8> {
        let b = self.read_bytes(pid, address, 1)?;
        Ok(b[0])
    }

    fn read_u16(&self, pid: u32, address: u64, little: bool) -> Result<u16> {
        let b = self.read_bytes(pid, address, 2)?;
        Ok(if little {
            u16::from_le_bytes([b[0], b[1]])
        } else {
            u16::from_be_bytes([b[0], b[1]])
        })
    }

    fn read_u32(&self, pid: u32, address: u64, little: bool) -> Result<u32> {
        let b = self.read_bytes(pid, address, 4)?;
        Ok(if little {
            u32::from_le_bytes([b[0], b[1], b[2], b[3]])
        } else {
            u32::from_be_bytes([b[0], b[1], b[2], b[3]])
        })
    }

    fn read_u64(&self, pid: u32, address: u64, little: bool) -> Result<u64> {
        let b = self.read_bytes(pid, address, 8)?;
        Ok(if little {
            u64::from_le_bytes(b.try_into().unwrap())
        } else {
            u64::from_be_bytes(b.try_into().unwrap())
        })
    }

    fn read_i8(&self, pid: u32, address: u64) -> Result<i8> {
        Ok(self.read_u8(pid, address)? as i8)
    }

    fn read_i16(&self, pid: u32, address: u64, little: bool) -> Result<i16> {
        Ok(self.read_u16(pid, address, little)? as i16)
    }

    fn read_i32(&self, pid: u32, address: u64, little: bool) -> Result<i32> {
        Ok(self.read_u32(pid, address, little)? as i32)
    }

    fn read_i64(&self, pid: u32, address: u64, little: bool) -> Result<i64> {
        let b = self.read_bytes(pid, address, 8)?;
        Ok(if little {
            i64::from_le_bytes(b.try_into().unwrap())
        } else {
            i64::from_be_bytes(b.try_into().unwrap())
        })
    }

    fn read_f32(&self, pid: u32, address: u64, little: bool) -> Result<f32> {
        Ok(f32::from_bits(self.read_u32(pid, address, little)?))
    }

    fn read_f64(&self, pid: u32, address: u64, little: bool) -> Result<f64> {
        Ok(f64::from_bits(self.read_u64(pid, address, little)?))
    }

    /// Read a (possibly null-terminated) string up to `max_len` bytes.
    fn read_string(&self, pid: u32, address: u64, max_len: u32) -> Result<String> {
        let buf = self.read_bytes(pid, address, max_len)?;
        let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
        // Keep only valid UTF-8 prefix; fall back to lossy conversion.
        let s = String::from_utf8_lossy(&buf[..end]).into_owned();
        Ok(s)
    }

    /// Read a value of a given type at an address, returning raw bytes.
    fn read_value(&self, pid: u32, address: u64, vt: ValueType, little: bool) -> Result<Vec<u8>> {
        let mut endian_fix = self.read_bytes(pid, address, vt.size())?;
        if little {
            #[cfg(target_endian = "big")]
            endian_fix.reverse();
        } else {
            #[cfg(target_endian = "little")]
            endian_fix.reverse();
        }
        Ok(endian_fix)
    }

    // ── Scanning ─────────────────────────────────────────────────────

    /// Scan all readable regions of the process for the given patterns.
    /// Backends may delegate to `crate::scanner::scan_memory`.
    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>>;

    // ── Pointer Chains ────────────────────────────────────────────────

    /// Follow: add offset to base, read pointer there, add next offset, ...
    /// The last `base + offset` address is read (must be readable) but not
    /// followed; it is returned. Returns the base if `offsets` is empty.
    /// See [`crate::chain::follow`] for a step-recording variant.
    fn resolve_ptr_chain(
        &self,
        pid: u32,
        base: u64,
        offsets: &[u64],
        little: bool,
    ) -> Result<Option<u64>> {
        if offsets.is_empty() {
            return Ok(Some(base));
        }
        let mut addr = base;
        let last = offsets.len() - 1;
        for (i, off) in offsets.iter().enumerate() {
            let target = addr.checked_add(*off).ok_or_else(|| anyhow::anyhow!("pointer overflow"))?;
            let ptr = self.read_u64(pid, target, little)?;
            if i == last {
                return Ok(Some(target));
            }
            addr = ptr;
        }
        Ok(Some(addr))
    }
}
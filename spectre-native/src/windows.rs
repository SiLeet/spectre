//! Windows process memory reader using raw Win32 FFI (kernel32).
//!
//! No external Windows crates: we declare the handful of functions we need
//! via `extern "system"` and define the minimal types ourselves.

use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_core::scanner::{scan_memory, ScanConfig};
use spectre_core::MemoryReader;
use anyhow::{anyhow, Result, bail};
use std::ffi::c_void;
use std::mem::size_of;

// ── Win32 FFI declarations ────────────────────────────────────────────────

#[allow(non_camel_case_types)]
type HANDLE = *mut c_void;
#[allow(non_camel_case_types)]
type BOOL = i32;
#[allow(non_camel_case_types)]
type DWORD = u32;
#[allow(non_camel_case_types)]
type WORD = u16;
#[allow(non_camel_case_types)]
type LPVOID = *mut c_void;

const PROCESS_VM_READ: DWORD = 0x0010;
const PROCESS_QUERY_INFORMATION: DWORD = 0x0400;
const TH32CS_SNAPPROCESS: DWORD = 0x00000002;
const INVALID_HANDLE_VALUE: isize = -1;

#[repr(C)]
#[derive(Debug, Clone, Copy)]
#[allow(non_snake_case)]
#[allow(non_camel_case_types)]
struct PROCESSENTRY32 {
    pub dwSize: DWORD,
    pub cntUsage: DWORD,
    pub th32ProcessID: DWORD,
    pub th32DefaultHeapID: *mut c_void,
    pub th32ModuleID: DWORD,
    pub cntThreads: DWORD,
    pub th32ParentProcessID: DWORD,
    pub pcPriClassBase: i32,
    pub dwFlags: DWORD,
    pub szExeFile: [u16; 260],
}

#[repr(C)]
#[derive(Debug, Clone, Copy)]
#[allow(non_snake_case)]
#[allow(non_camel_case_types)]
struct MEMORY_BASIC_INFORMATION {
    pub BaseAddress: *mut c_void,
    pub AllocationBase: *mut c_void,
    pub AllocationProtect: DWORD,
    pub __alignment1: usize,
    pub RegionSize: usize,
    pub State: DWORD,
    pub Protect: DWORD,
    pub Type: DWORD,
    pub __alignment2: usize,
}

unsafe extern "system" {
    fn OpenProcess(dwDesiredAccess: DWORD, bInheritHandle: BOOL, dwProcessId: DWORD) -> HANDLE;
    fn ReadProcessMemory(
        hProcess: HANDLE,
        lpBaseAddress: LPVOID,
        lpBuffer: LPVOID,
        nSize: usize,
        lpNumberOfBytesRead: *mut usize,
    ) -> BOOL;
    fn CloseHandle(hObject: HANDLE) -> BOOL;
    fn CreateToolhelp32Snapshot(dwFlags: DWORD, th32ProcessID: DWORD) -> HANDLE;
    fn Process32First(hSnapshot: HANDLE, lppe: *mut PROCESSENTRY32) -> BOOL;
    fn Process32Next(hSnapshot: HANDLE, lppe: *mut PROCESSENTRY32) -> BOOL;
    fn VirtualQueryEx(
        hProcess: HANDLE,
        lpAddress: LPVOID,
        lpBuffer: *mut MEMORY_BASIC_INFORMATION,
        dwLength: usize,
    ) -> usize;
    fn GetLastError() -> DWORD;
}

// ── Reader ────────────────────────────────────────────────────────────────

/// Windows native backend.
#[derive(Debug, Default)]
pub struct WindowsReader;

impl WindowsReader {
    pub fn new() -> Self {
        WindowsReader
    }

    /// Open a read-only handle to the target process.
    fn open(pid: u32) -> Result<HANDLE> {
        let h = unsafe { OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, 0, pid) };
        if h.is_null() {
            Err(anyhow!("OpenProcess failed for pid {pid} (error {})", unsafe { GetLastError() }))
        } else {
            Ok(h)
        }
    }

    /// Convert a Win32 wide-char buffer (nul-terminated) to String.
    fn wide_to_string(buf: &[u16]) -> String {
        let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        String::from_utf16_lossy(&buf[..end])
    }

    fn perms_of(protect: DWORD) -> String {
        // Bit meanings (best-effort): PAGE_READONLY 0x02, READWRITE 0x04,
        // WRITECOPY 0x08, EXECUTE 0x10, EXECUTE_READ 0x20,
        // EXECUTE_READWRITE 0x40, EXECUTE_WRITECOPY 0x80.
        let r = protect & 0x02 != 0 || protect & 0x04 != 0 || protect & 0x20 != 0 || protect & 0x40 != 0;
        let w = protect & 0x04 != 0 || protect & 0x40 != 0;
        let x = protect & 0x10 != 0 || protect & 0x20 != 0 || protect & 0x40 != 0 || protect & 0x80 != 0;
        format!("{}{}{}", if r { 'r' } else { '-' }, if w { 'w' } else { '-' }, if x { 'x' } else { '-' })
    }
}

impl MemoryReader for WindowsReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::NativeWindows
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        let all = self.list_processes()?;
        let lower = name.to_lowercase();
        Ok(all.into_iter().filter(|p| p.name.to_lowercase().contains(&lower)).collect())
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        let mut out = Vec::new();
        // SAFETY: bounded, documented Win32 usage.
        let snap = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
        if snap == INVALID_HANDLE_VALUE as HANDLE || snap.is_null() {
            bail!("CreateToolhelp32Snapshot failed (error {})", unsafe { GetLastError() });
        }
        let mut entry: PROCESSENTRY32 = unsafe { std::mem::zeroed() };
        entry.dwSize = size_of::<PROCESSENTRY32>() as DWORD;
        let mut ok = unsafe { Process32First(snap, &mut entry) } != 0;
        while ok {
            out.push(ProcessInfo {
                pid: entry.th32ProcessID,
                name: Self::wide_to_string(&entry.szExeFile),
            });
            ok = unsafe { Process32Next(snap, &mut entry) } != 0;
        }
        unsafe { CloseHandle(snap) };
        Ok(out)
    }

    fn process_name(&self, pid: u32) -> Result<Option<String>> {
        for p in self.list_processes()? {
            if p.pid == pid {
                return Ok(Some(p.name));
            }
        }
        Ok(None)
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        let h = Self::open(pid)?;
        let mut regions = Vec::new();
        let mut addr: *mut c_void = std::ptr::null_mut();
        loop {
            let mut mbi: MEMORY_BASIC_INFORMATION = unsafe { std::mem::zeroed() };
            let len = unsafe { VirtualQueryEx(h, addr, &mut mbi, size_of::<MEMORY_BASIC_INFORMATION>()) };
            if len == 0 {
                break;
            }
            let start = mbi.BaseAddress as u64;
            let size = mbi.RegionSize as u64;
            // Only committed memory (MEM_COMMIT = 0x1000).
            if mbi.State == 0x1000 && size > 0 {
                regions.push(MemoryRegion {
                    start,
                    end: start + size,
                    perms: Self::perms_of(mbi.Protect),
                    path: None,
                });
            }
            addr = (mbi.BaseAddress as u64 + size) as *mut c_void;
        }
        unsafe { CloseHandle(h) };
        Ok(regions)
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        if size == 0 {
            return Ok(Vec::new());
        }
        let h = Self::open(pid)?;
        let mut buf = vec![0u8; size as usize];
        let mut read: usize = 0;
        let ok = unsafe {
            ReadProcessMemory(
                h,
                address as *mut c_void,
                buf.as_mut_ptr() as *mut c_void,
                buf.len(),
                &mut read,
            )
        };
        let last_error = unsafe { GetLastError() };
        unsafe { CloseHandle(h) };
        if ok == 0 {
            Err(anyhow!("ReadProcessMemory at {address:#x} failed (error {last_error})"))
        } else {
            buf.truncate(read);
            Ok(buf)
        }
    }

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        let mut config = ScanConfig::default();
        config.little_endian = little;
        scan_memory(self, pid, patterns, &config)
    }
}
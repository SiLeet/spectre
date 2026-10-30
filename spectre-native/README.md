# spectre-native

**OS-native process memory reader for Spectre.**

Reads process memory directly from the host operating system using low-level platform APIs. No debugger, no ptrace-gdb chain, no hardware debugger — just raw OS syscalls and file I/O.

## Platform Support

| Platform | API | Implementation | File |
|----------|-----|----------------|------|
| **Windows** | `OpenProcess` + `ReadProcessMemory` (kernel32 FFI) | `WindowsReader` in `src/windows.rs` | |
| **Linux** | `/proc/pid/mem` file I/O + `/proc/pid/maps` region parsing | `LinuxReader` in `src/linux.rs` | |

No heavy dependencies — all platform APIs are accessed via raw FFI (`extern "C"`) or direct filesystem access.

## Quick Start

```rust
use spectre_native::NativeReader;
use spectre_core::reader::MemoryReader;

// Auto-detect platform
let reader = NativeReader::create();

// Find a process by name
let procs = reader.find_process("my_game");
let pid = procs[0].pid;

// Read 16 bytes from address 0x7FF0_1234_0000
let data = reader.read_bytes(pid, 0x7FF0_1234_0000, 16);

// Follow a pointer chain
let value_addr = reader.resolve_ptr_chain(
    pid,
    0x7FF0_0000_0000,      // base address of global table
    [0x10, 0x28],           // offsets to chase
    true,                   // little endian
);
```

## Module Structure

```
spectre-native/
├── Cargo.toml
├── README.md
└── src/
    ├── lib.rs         — Crate root, module exports, `create_default_reader()` convenience
    ├── windows.rs     — WindowsReader (Win32 FFI, kernel32.dll)
    ├── linux.rs       — LinuxReader (/proc/pid/mem + /proc/pid/maps)
    └── reader.rs      — NativeReader enum implementing MemoryReader trait
```

## Platform Details

### Windows (`WindowsReader`)

Uses raw FFI declarations — no `windows-rs` or other wrapper crates.

**Key APIs called:**
- `OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, FALSE, pid)` → `HANDLE`
- `ReadProcessMemory(hProcess, address, buffer, size, &bytesRead)` → `BOOL`
- `CloseHandle(hProcess)` → `BOOL`
- `CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)` → process snapshot
- `Process32Next(hSnapshot, &entry)` → iterate processes
- `VirtualQueryEx(hProcess, address, &memQuery, size)` → region enumeration
- `GetLastError()` → `DWORD` error code

**Required permissions:** Process must be readable by caller (same user, or admin).

**Constraints:**
- Reads are limited by process protection (ASLR, protected process bits)
- 64-bit processes can read both 64-bit and 32-bit processes; 32-bit readers can only read 32-bit processes

### Linux (`LinuxReader`)

Direct filesystem access with no FFI needed.

**Files accessed:**
- `/proc/[pid]/mem` — Raw process memory as a seekable file (requires `pread`/`read_at`)
- `/proc/[pid]/maps` — Memory region map (start-end addresses, permissions, mapped file)
- `/proc/[pid]/status` — Process name (extracted from `Name:` field)
- `/proc/[pid]/comm` — Fallback process name

**Required permissions:**
- Same user as target process, or root
- May need `ptrace_race` sysctl adjusted: `echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_race`
- Or run as root / with `CAP_SYS_PTRACE`

**Notes:**
- Reads at invalid addresses return `EIO` rather than crashing the reader
- Region information comes from `/proc/pid/maps` — no extra API calls needed

## Trait: MemoryReader

All platform readers implement `spectre_core::reader::MemoryReader`:

```rust
pub trait MemoryReader: Send + Sync {
    fn backend_kind(&self) -> BackendKind;
    fn find_process(&self, name: &str) -> anyhow::Result<Vec<ProcessInfo>>;
    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>>;
    fn memory_regions(&self, pid: u32) -> anyhow::Result<Vec<MemoryRegion>>;
    fn process_name(&self, pid: u32) -> anyhow::Result<Option<String>>;
    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>>;
    // + typed read helpers with default implementations
    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> ...;
    fn dump_region(&self, pid: u32, region, path) -> ...;
    fn resolve_ptr_chain(&self, pid, base, offsets, little) -> ...;
}
```

## Dependency Rationale

| Crate | Why |
|-------|-----|
| `spectre-core` | Provides `MemoryReader` trait + types (`ProcessInfo`, `MemoryRegion`, etc.) |
| `anyhow` | Error type `anyhow::Result<T>` for ergonomic error propagation |
| `traced` | Structured tracing / logging |
| `tokio` | Async runtime (minimal usage; most operations are synchronous) |

No OS-specific dependencies (`windows-rs`, `libc`) — all platform calls are implemented via direct FFI or file I/O.

## Building

```bash
# Build for current platform
cargo build

# Cross-compile (example)
cargo build --target x86_64-pc-windows-msvc   # Windows
cargo build --target x86_64-unknown-linux-gnu  # Linux
```

## Testing

The crate includes integration tests that run on their native platform:

```bash
# On Windows:
cargo test -- --nocapture --ignored windows_integration

# On Linux:
cargo test -- --nocapture --ignored linux_integration
```

> **Note:** Integration tests are ignored by default because they require running processes to attach to. Use `--ignored` to include them.
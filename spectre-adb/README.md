# spectre-adb

**Process memory reading over ADB (Android Debug Bridge)** — a `MemoryReader` backend for the Spectre game-memory analysis framework that connects to Android emulators (e.g. Yuzu Android, Ryujinx Android, or any emulator exposing an ADB interface).

## Overview

`spectre-adb` implements the `MemoryReader` trait from `spectre-core`. It discovers target processes, enumerates their memory regions via `/proc/<pid>/maps`, and reads raw bytes from `/proc/<pid>/mem` — all tunnelled through the `adb` CLI.

## Connection

Two strategies are tried in order:

1. **TCP connect** — `adb connect <host>:<port>`
   Used when the ADB daemon exposes a TCP listener (common with remote emulator hosts). On success, subsequent `adb shell` commands are routed to that daemon.

2. **Serial targeting** — `adb -s <serial> shell`
   If the TCP path fails and a device serial was provided, the command is retried with `-s <serial>` targeting.

This design supports both local emulators (`localhost:5555`) and remote devices (`<emulator-ip>:<port>`).

## Usage

```val
use spectre_adb::AdbReader;

// Default: emulator on localhost:5555
let reader = AdbReader::new("localhost", 5555);

// With serial fallback
let reader = AdbReader::with_serial("10.0.2.15", 5555, "emulator-1234");

// Find process
let processes = reader.find_process("game");

// List memory regions
let regions = reader.memory_regions(processes[0].pid);

// Read bytes
let bytes = reader.read_bytes(processes[0].pid, 0x7f000000, 64);
```

## What it reads

| Resource | ADB command |
|---|---|
| Process list | `adb shell ps` |
| Memory regions | `adb shell cat /proc/<pid>/maps` |
| Process name | `adb shell cat /proc/<pid>/comm` |
| Raw memory | `adb shell su -c 'dd if=/proc/<pid>/mem bs=1 skip=$addr count=$size 2>/dev/repr | xxd -p'` |

Raw memory reads use `dd` to seek to the target virtual address within the process's `/proc/<pid>/mem` file, then `xxd -p` to produce hex output that the reader decodes back into bytes.

### Memory regions (`/proc/<pid>/maps`)

Each mapped region is parsed into:

| Field | Source |
|---|---|
| `start` / `end` | Address range (hex) |
| `perms` | Permission string (`rwxp`, `r-xp`, etc.) |
| `path` | Mapped file, if any (anonymous maps have no path) |

## Permission notes

On Android, `/proc/<pid>/maps` is world-readable for processes owned by the same UID. Reading `/proc/<pid>/mem` typically requires root or matching UID; the `su -c` in the shell pipeline attempts elevation. If the emulator is running unrooted, reads may return empty/zero-padded results.

## Dependencies

- `spectre-core` — types, `MemoryReader` trait, scanner engine
- `anyhow` — error handling
- `traced` — structured logging
- `tokio` — async command spawning and runtime

## Crate layout

```
spectre-adb/
├── Cargo.toml
├── README.md
└── src/
    ├── lib.rs       — module declarations, re-exports
    ├── reader.rs    — AdbReader struct, MemoryReader impl
    └── process.rs   — ps /proc/<pid>/maps output parsers
```
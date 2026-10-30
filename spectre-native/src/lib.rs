//! Native OS process memory reader.
//!
//! Implements [`MemoryReader`] using the host operating system:
//! - Windows: Win32 API (`OpenProcess` / `ReadProcessMemory` / `VirtualQueryEx`)
//!   via raw FFI — no external Windows crates.
//! - Linux: `/proc/<pid>/mem` + `/proc/<pid>/maps` via file I/O.
//!
//! A thin [`NativeReader`] enum dispatches to the platform-specific backend.

#[cfg(windows)]
mod windows;
#[cfg(unix)]
mod linux;

mod reader;

pub use reader::{create_default_reader, NativeReader, native_backend_kind};

/// Minimal re-exports used by higher layers.
pub use spectre_core::MemoryReader;
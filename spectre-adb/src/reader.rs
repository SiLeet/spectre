use crate::process::{parse_maps_output, parse_ps_output};
use anyhow::{Context, Result, bail};
use spectre_core::error::SpectreError;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};

/// ADB-backed MemoryReader implementation for Android emulators.
///
/// Connects to an Android emulator via the `adb` CLI, then reads
/// `/proc/<pid>/maps` for memory region layout and `/proc/<pid>/mem`
/// (through dd piped to xxd) for raw memory reads.
static ADB_PROGRAM: std::sync::OnceLock<String> = std::sync::OnceLock::new();

// ── AdbReader ──────────────────────────────────────────────────────────────

/// Reads process memory from an Android emulator over ADB.
///
/// Two connection strategies, tried in order:
///   1. `adb connect <host>:<port>` (TCP-mode ADB daemon)
///   2. `adb -s <serial> shell` (serial-targeted device)
///
/// Every ADB shell command is attempted via strategy 1 first; if it fails
/// and a serial was provided, the command is retried with strategy 2.
#[derive(Debug)]
pub struct AdbReader {
    /// ADB daemon host (e.g. "localhost" or emulator IP).
    pub host: String,
    /// ADB daemon port (default 5555).
    pub port: u16,
    /// Optional device serial for `adb -s <serial>` fallback.
    pub serial: Option<String>,
}

impl AdbReader {
    /// Create a reader that targets an ADB daemon at `host:port`.
    ///
    /// No serial is configured; commands are sent via `adb connect` followed
    /// by `adb shell`.
    pub fn new(host: &str, port: u16) -> AdbReader {
        AdbReader {
            host: host.to_owned(),
            port,
            serial: None,
        }
    }

    /// Create a reader with a specific device serial for fallback.
    ///
    /// Commands are first attempted via `adb shell` (after connecting),
    /// and retried with `adb -s <serial> shell` on failure.
    pub fn with_serial(host: &str, port: u16, serial: &str) -> AdbReader {
        AdbReader {
            host: host.to_owned(),
            port,
            serial: Some(serial.to_owned()),
        }
    }
}

// ── Low-level helpers ─────────────────────────────────────────────────────

impl AdbReader {
    /// Run `adb` with the given arguments, awaiting completion.
    async fn adb_output(&self, args: &[&str]) -> Result<std::process::Output> {
        let adb = ADB_PROGRAM
            .get_or_init(crate::multi::adb_path)
            .clone();
        tokio::process::Command::new(adb)
            .args(args)
            .output()
            .await
            .context("failed to spawn adb")
    }

    /// Wrap a `tokio::process::Command` for arbitrary adb args.
    async fn adb_output_with(
        &self,
        extra: &[&str],
        sub: &str,
        args: &str,
    ) -> Result<std::process::Output> {
        let adb = ADB_PROGRAM
            .get_or_init(crate::multi::adb_path)
            .clone();
        let mut cmd = tokio::process::Command::new(adb);
        cmd.args(extra).arg(sub).arg(args);
        cmd.output()
            .await
            .context("failed to spawn adb")
    }

    /// Run a shell command on the target Android device via ADB.
    ///
    /// The command string is passed verbatim to `adb shell` (run through
    /// `/system/bin/sh -c` on the device). Yes, `run_adb_shell` is
    /// synchronous — it builds a short-lived current-thread Tokio runtime
    /// because `adb_output_with` is `async` (tokio process API).
    ///
    /// The plain shell is tried first; if it fails or returns nothing
    /// (permission denied under the `shell` UID), the command is retried
    /// with root elevation (`su -c '...'`) so the reader works both on
    /// rooted emulators (BlueStacks with root on) and unrooted devices.
    fn run_adb_shell(&self, command: &str) -> Result<String> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .context("failed to build tokio runtime")?;

        rt.block_on(async {
            // Step 1: try to connect to the remote ADB daemon via TCP.
            // This is idempotent — already-connected daemons ignore the request.
            let host_port = format!("{}:{}", self.host, self.port);
            let _ = self.adb_output(&["connect", &host_port]).await;

            let (serial_args, label): (Vec<&str>, String) = match &self.serial {
                Some(s) => (vec!["-s", s.as_str()], format!("adb -s {s}")),
                None => (vec![], "adb".to_owned()),
            };

            // Run plain, then fall back to root if it fails or is empty.
            let plain = self
                .adb_output_with(&serial_args, "shell", command)
                .await?;
            if plain.status.success() && !plain.stdout.is_empty() {
                return Ok(String::from_utf8_lossy(&plain.stdout).into_owned());
            }

            // Root fallback: `su -c '<command>'`; swallow su's own errors.
            let rooted = format!("su -c '{command}' 2>/dev/null || true");
            let root_run = self
                .adb_output_with(&serial_args, "shell", &rooted)
                .await?;
            if root_run.status.success() && !root_run.stdout.is_empty() {
                return Ok(String::from_utf8_lossy(&root_run.stdout).into_owned());
            }

            // Prefer the plain output for error reporting (more meaningful).
            let stderr = String::from_utf8_lossy(&plain.stderr);
            bail!(SpectreError::BackendError(format!(
                "{label} shell failed (exit={}): {stderr}",
                plain.status
            )));
        })
    }
}

// ── MemoryReader trait implementation ──────────────────────────────────────

impl MemoryReader for AdbReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::Adb
    }

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        let all = self.list_processes()?;
        Ok(all.into_iter().filter(|p| p.name.contains(name)).collect())
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        let output = self.run_adb_shell("ps")?;
        parse_ps_output(&output)
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        let output = self.run_adb_shell(&format!(
            "/bin/cat /proc/{pid}/maps 2>/dev/null || true"
        ))?;
        parse_maps_output(&output)
    }

    fn process_name(&self, pid: u32) -> Result<Option<String>> {
        let output =
            self.run_adb_shell(&format!("/bin/cat /proc/{pid}/comm 2>/dev/null || true"))?;
        let name = output.trim();
        if name.is_empty() {
            Ok(None)
        } else {
            Ok(Some(name.to_owned()))
        }
    }

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        if size == 0 {
            return Ok(Vec::new());
        }

        // On Android, dd supports byte-wise skip only with bs=1, which is
        // ~7x slower than 4K-block page reads. Because anonymous/mmap heaps
        // are page-aligned, split the read: leading unaligned head via bs=1,
        // the aligned middle via 4K blocks, trailing tail via bs=1.
        const PAGE: u64 = 4096;
        let mut out: Vec<u8> = Vec::with_capacity(size as usize);
        let mut addr = address;
        let mut remaining = size as u64;

        let head = (PAGE - (addr % PAGE)) % PAGE;
        if head > 0 && head < remaining {
            let part = self.read_bytes_bs1(pid, addr, head as u32)?;
            out.extend_from_slice(&part);
            addr += head;
            remaining -= head;
        }

        let aligned = remaining - (remaining % PAGE);
        if aligned >= PAGE {
            let part = self.read_bytes_pages(pid, addr, aligned as u32)?;
            out.extend_from_slice(&part);
            addr += aligned;
            remaining -= aligned;
        }

        if remaining > 0 {
            let part = self.read_bytes_bs1(pid, addr, remaining as u32)?;
            out.extend_from_slice(&part);
        }

        Ok(out)
    }

    fn scan(
        &self,
        pid: u32,
        patterns: Vec<ScanPattern>,
        little: bool,
    ) -> Result<Vec<ScanReport>> {
        let config = ScanConfig {
            little_endian: little,
            ..Default::default()
        };
        scan_memory(self, pid, patterns, &config)
    }
}

// ── Raw read helpers (inherent, page-aware) ───────────────────────────────

impl AdbReader {
    /// Decode an `xxd -p` hex stream (whitespace-tolerant) into `size` bytes.
    /// Missing hex digits decode as zero; extra digits are ignored.
    fn hex_decode(&self, hex: &str, size: u32) -> Vec<u8> {
        let mut out = Vec::with_capacity(size as usize);
        let mut hi: Option<u8> = None;
        for ch in hex.chars() {
            if !ch.is_ascii_hexdigit() {
                continue;
            }
            let nib = char_to_nibble(ch);
            match hi.take() {
                Some(h) => out.push((h << 4) | nib),
                None => hi = Some(nib),
            }
            if out.len() == size as usize {
                break;
            }
        }
        // A dangling high nibble at the end.
        if let Some(h) = hi {
            if (out.len() as u32) < size {
                out.push(h << 4);
            }
        }
        while (out.len() as u32) < size {
            out.push(0);
        }
        out
    }

    /// Byte-wise read (bs=1). Used for unaligned heads/tails.
    fn read_bytes_bs1(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        let cmd = format!(
            "su -c 'dd if=/proc/{pid}/mem bs=1 skip={address} count={size} 2>/dev/null | xxd -p' 2>/dev/null || true"
        );
        let output = self.run_adb_shell(&cmd)?;
        Ok(self.hex_decode(&output, size))
    }

    /// Page-aligned bulk read using 4K blocks (bs=4096, skip in pages).
    fn read_bytes_pages(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        debug_assert_eq!(address % 4096, 0, "page reads require aligned addresses");
        let page = address / 4096;
        let count = size / 4096;
        let cmd = format!(
            "su -c 'dd if=/proc/{pid}/mem bs=4096 skip={page} count={count} 2>/dev/null | xxd -p' 2>/dev/null || true"
        );
        let output = self.run_adb_shell(&cmd)?;
        Ok(self.hex_decode(&output, size))
    }
}

// ── Hex helper ─────────────────────────────────────────────────────────────

/// Convert an ASCII hex character to its 4-bit numeric value.
fn char_to_nibble(ch: char) -> u8 {
    match ch {
        '0'..='9' => (ch as u8) - b'0',
        'a'..='f' => (ch as u8) - b'a' + 10,
        'A'..='F' => (ch as u8) - b'A' + 10,
        _ => 0,
    }
}

use crate::process::{parse_maps_output, parse_ps_output};
use anyhow::{Context, Result, bail};
use spectre_core::error::SpectreError;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
/// ADB-backed MemoryReader implementation for Android emulators.
///
/// Connects to an Android emulator via the `adb` CLI, then reads
/// `/proc/<pid>/maps` for memory region layout and `/proc/<pid>/mem`
/// (through dd piped to xxd) for raw memory reads.
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};

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

    // ── Low-level helpers ─────────────────────────────────────────────

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

    /// Run a shell command on the target Android device via ADB.
    ///
    /// The command string is passed verbatim to `adb shell` (run through
    /// `/bin/sh -c` on the device). If the plain shell fails or produces
    /// nothing (permission denied under the `shell` UID), the command is
    /// retried with root elevation (`su -c '...'`) so the reader works both
    /// on rooted emulators (BlueStacks with root on) and on unrooted devices.
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

    /// Wrap a `tokio::process::Command` for arbitrary adb args.
    async fn adb_output_with(&self, extra: &[&str], sub: &str, args: &str) -> Result<std::process::Output> {
            let adb = ADB_PROGRAM
                .get_or_init(crate::multi::adb_path)
                .clone();
            let mut cmd = tokio::process::Command::new(adb);
            cmd.args(extra).arg(sub).arg(args);
            cmd.output()
                .await
                .context("failed to spawn adb")
        }

    /// Decode a hex string (from `xxd -p` output) into raw bytes.
    ///
    /// Strips all whitespace and newlines, then parses two-char hex groups.
    /// Returns a vector of exactly `expected_count` bytes, padding with
    /// zeroes on short output (readable region smaller than requested).
    fn hex_decode(&self, hex: &str, expected_count: u32) -> Vec<u8> {
        // Strip whitespace, newlines, and any non-hex separators.
        let mut cleaned: Vec<char> = Vec::new();
        for ch in hex.chars() {
            if ch.is_ascii_hexdigit() {
                cleaned.push(ch);
            }
        }

        let mut bytes: Vec<u8> = Vec::new();
        let mut i: usize = 0;
        while i + 1 < cleaned.len() && (bytes.len() as u32) < expected_count {
            let hi = char_to_nibble(cleaned[i]) << 4;
            let lo = char_to_nibble(cleaned[i + 1]);
            bytes.push(hi | lo);
            i += 2;
        }

        // Pad with zero bytes if the device returned less data than requested
        // (can happen when reading near the end of a memory region).
        while (bytes.len() as u32) < expected_count {
            bytes.push(0);
        }

        bytes
    }
}

// ── MemoryReader Trait Implementation ─────────────────────────────────────

impl MemoryReader for AdbReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::Adb
    }

    // ── Process Discovery ────────────────────────────────────────────

    fn find_process(&self, name: &str) -> Result<Vec<ProcessInfo>> {
        let lower = name.to_lowercase();
        Ok(self
            .list_processes()?
            .into_iter()
            .filter(|p| p.name.to_lowercase().contains(&lower))
            .collect())
    }

    fn list_processes(&self) -> Result<Vec<ProcessInfo>> {
        let output = self.run_adb_shell("ps")?;
        parse_ps_output(&output)
    }

    fn memory_regions(&self, pid: u32) -> Result<Vec<MemoryRegion>> {
        // On Android, /proc/<pid>/maps is world-readable for the same UID.
        let output = self.run_adb_shell(&format!("/bin/cat /proc/{pid}/maps"))?;
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

    // ── Raw Memory Reading ───────────────────────────────────────────

    fn read_bytes(&self, pid: u32, address: u64, size: u32) -> Result<Vec<u8>> {
        if size == 0 {
            return Ok(Vec::new());
        }

        // Shell incantation: use dd to seek to `address` in /proc/<pid>/mem
        // (with root elevation via `su -c`), then pipe through xxd -p for hex output.
        // stderr from dd (e.g. partial read warnings) is discarded.
        //
        // The `|| true` prevents a non-zero exit from killing the pipeline.
        let cmd = format!(
            "su -c 'dd if=/proc/{pid}/mem bs=1 skip={address} count={size} 2>/dev/null | xxd -p' 2>/dev/null || true"
        );
        let output = self.run_adb_shell(&cmd)?;

        Ok(self.hex_decode(&output, size))
    }

    // ── Scanning ─────────────────────────────────────────────────────

    fn scan(&self, pid: u32, patterns: Vec<ScanPattern>, little: bool) -> Result<Vec<ScanReport>> {
        let config = ScanConfig { little_endian: little, ..Default::default() };
        scan_memory(self, pid, patterns, &config)
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

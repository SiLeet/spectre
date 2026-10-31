use crate::process::{parse_maps_output, parse_ps_output};
use anyhow::{Context, Result, bail};
use spectre_core::error::SpectreError;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use tracing::warn;

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
        if let Some(h) = hi
            && (out.len() as u32) < size
        {
            out.push(h << 4);
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

// ── On-device pattern grep (hot scan) ─────────────────────────────────────

/// Longest pattern [`AdbReader::grep_memory`] accepts: each chunk reads one
/// extra page, which must cover any match that starts in the chunk.
pub const GREP_MAX_PATTERN: usize = 4096;

impl AdbReader {
    /// Search `regions` of `pid` for byte `patterns` *on the device*, so only
    /// match offsets cross the adb pipe instead of a full hex dump.
    ///
    /// Regions are read in page-aligned chunks of `chunk` bytes (rounded up
    /// to whole pages; 1 MiB is a good default). A chunk the device cannot
    /// read is logged and skipped; it does not abort the scan.
    ///
    /// Returns `(absolute address, pattern index)` pairs sorted by address.
    pub fn grep_memory(
        &self,
        pid: u32,
        regions: &[MemoryRegion],
        patterns: &[Vec<u8>],
        chunk: u32,
    ) -> Result<Vec<(u64, usize)>> {
        grep_regions(pid, regions, patterns, chunk, |cmd| self.run_adb_shell(cmd))
    }
}

/// Core of [`AdbReader::grep_memory`], with the shell runner injected for tests.
fn grep_regions(
    pid: u32,
    regions: &[MemoryRegion],
    patterns: &[Vec<u8>],
    chunk: u32,
    mut run: impl FnMut(&str) -> Result<String>,
) -> Result<Vec<(u64, usize)>> {
    const PAGE: u64 = 4096;
    if patterns.is_empty() {
        bail!("grep_memory needs at least one pattern");
    }
    if let Some(p) = patterns
        .iter()
        .find(|p| p.is_empty() || p.len() > GREP_MAX_PATTERN)
    {
        bail!(
            "pattern length {} out of range (1..={GREP_MAX_PATTERN} bytes)",
            p.len()
        );
    }
    // Hex-encoding here is also the injection guard: only [0-9a-f] reaches the shell.
    let hex: Vec<String> = patterns.iter().map(|p| hex_encode(p)).collect();
    let chunk = u64::from(chunk.max(1)).div_ceil(PAGE) * PAGE;

    let mut hits = Vec::new();
    for r in regions {
        let mut addr = r.start - r.start % PAGE;
        while addr < r.end {
            let len = (r.end - addr).min(chunk);
            // One extra page so a match starting in this chunk but ending in
            // the next is still seen; `off < len` gives each start to exactly
            // one chunk, so overlapping chunks never report a match twice.
            let cmd = grep_chunk_command(pid, addr / PAGE, len.div_ceil(PAGE) + 1, &hex);
            match run(&cmd) {
                Ok(out) => hits.extend(
                    parse_grep_output(&out, &hex)
                        .into_iter()
                        .filter(|&(off, _)| off < len)
                        .map(|(off, idx)| (addr + off, idx)),
                ),
                Err(e) => warn!("hot scan: skipping unreadable chunk {addr:#x}+{len:#x}: {e:#}"),
            }
            addr += len;
        }
    }
    hits.sort_unstable();
    hits.dedup();
    Ok(hits)
}

/// Device command that greps `count` pages from page `skip` of `/proc/<pid>/mem`.
///
/// Why xxd: grep cannot take NUL bytes in `-e` patterns, so memory and
/// patterns are both compared as `xxd -p` hex text. `xxd -p` wraps lines, so
/// `tr -d "\n"` joins the chunk into one line: no match is lost at a line
/// break and `grep -b` offsets are plain hex-char offsets (byte = off / 2).
/// The trailing `echo` keeps the output non-empty when nothing matches, which
/// `run_adb_shell` would otherwise treat as a failure.
///
/// `hex_patterns` must be lowercase hex from [`hex_encode`] (shell-safe).
fn grep_chunk_command(pid: u32, skip: u64, count: u64, hex_patterns: &[String]) -> String {
    let es: String = hex_patterns.iter().map(|p| format!(" -e {p}")).collect();
    format!(
        "su -c 'dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null \
         | xxd -p | tr -d \"\\n\" | grep -boF{es}' 2>/dev/null; echo end"
    )
}

/// Parse `grep -bo` lines (`<hex-char offset>:<match>`) into
/// `(byte offset, pattern index)`; anything else (e.g. the sentinel) is ignored.
///
/// shortcut: `grep -o` reports non-overlapping matches only, so an occurrence
/// overlapping an earlier hit (self-similar patterns like `00000000`) can be
/// missed; re-check such runs with `spectre dump` if it ever matters.
fn parse_grep_output(output: &str, hex_patterns: &[String]) -> Vec<(u64, usize)> {
    output
        .lines()
        .filter_map(|line| {
            let (off, m) = line.split_once(':')?;
            let off: u64 = off.trim().parse().ok()?;
            // An odd hex-char offset starts mid-byte: a false positive.
            if !off.is_multiple_of(2) {
                return None;
            }
            let idx = hex_patterns.iter().position(|p| p == m.trim())?;
            Some((off / 2, idx))
        })
        .collect()
}

/// Lowercase hex, no separators (the `xxd -p` alphabet).
fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(start: u64, end: u64) -> MemoryRegion {
        MemoryRegion {
            start,
            end,
            perms: "rw-p".to_owned(),
            path: None,
        }
    }

    /// What the device pipeline `xxd -p | tr -d "\n" | grep -boF -e ...` prints.
    fn fake_device_grep(data: &[u8], hex_patterns: &[String]) -> String {
        // xxd -p wraps at 30 bytes; tr removes the newlines again.
        let wrapped: Vec<String> = data.chunks(30).map(hex_encode).collect();
        let line = wrapped.join("\n").replace('\n', "");
        let mut out = String::new();
        let mut pos = 0;
        // grep -o: leftmost match, then continue after it (non-overlapping).
        while let Some((at, p)) = hex_patterns
            .iter()
            .filter_map(|p| line[pos..].find(p.as_str()).map(|i| (pos + i, p)))
            .min_by_key(|&(at, p)| (at, usize::MAX - p.len()))
        {
            out.push_str(&format!("{at}:{p}\n"));
            pos = at + p.len();
        }
        out + "end\n"
    }

    /// Runner simulating `/proc/<pid>/mem` holding `mem` at `base`.
    fn fake_runner<'a>(
        mem: &'a [u8],
        base: u64,
        failing_page: Option<u64>,
        hex: &'a [String],
        calls: &'a mut Vec<(u64, u64)>,
    ) -> impl FnMut(&str) -> Result<String> + 'a {
        move |cmd: &str| {
            let arg = |key: &str| -> u64 {
                cmd.split_whitespace()
                    .find_map(|t| t.strip_prefix(key))
                    .unwrap()
                    .parse()
                    .unwrap()
            };
            let (skip, count) = (arg("skip="), arg("count="));
            calls.push((skip, count));
            if failing_page.is_some_and(|p| (skip..skip + count).contains(&p)) {
                bail!("simulated adb failure");
            }
            let from = (skip * 4096 - base) as usize;
            let to = (from + (count * 4096) as usize).min(mem.len());
            Ok(fake_device_grep(&mem[from.min(to)..to], hex))
        }
    }

    #[test]
    fn hex_encode_is_lowercase_xxd_alphabet() {
        assert_eq!(hex_encode(&[0xde, 0xAD, 0x00, 0x0f]), "dead000f");
    }

    #[test]
    fn command_contains_only_numeric_and_hex_inputs() {
        let cmd = grep_chunk_command(1234, 5, 257, &["b8f30300".into(), "00ff".into()]);
        assert_eq!(
            cmd,
            "su -c 'dd if=/proc/1234/mem bs=4096 skip=5 count=257 2>/dev/null \
             | xxd -p | tr -d \"\\n\" | grep -boF -e b8f30300 -e 00ff' 2>/dev/null; echo end"
        );
        // Exactly the two quotes wrapping the su -c script.
        assert_eq!(cmd.matches('\'').count(), 2);
    }

    #[test]
    fn parser_maps_even_hex_offsets_to_bytes() {
        let hex = vec!["b8f30300".to_owned(), "dead".to_owned()];
        let out = "0:b8f30300\n120:dead\r\n7:b8f30300\n44:cafe\nend\ngarbage\n";
        // 7 is odd (mid-byte, dropped); "cafe" is not ours; "end" is the sentinel.
        assert_eq!(parse_grep_output(out, &hex), vec![(0, 0), (60, 1)]);
    }

    #[test]
    fn odd_nibble_false_positive_is_rejected() {
        // Bytes 0x0b 0x8f 0x30 0x30 0x00 -> "0b8f303000" holds "b8f30300" at hex offset 1.
        let hex = vec![hex_encode(&[0xb8, 0xf3, 0x03, 0x00])];
        let out = fake_device_grep(&[0x0b, 0x8f, 0x30, 0x30, 0x00, 0x00], &hex);
        assert!(
            out.starts_with("1:"),
            "fake grep must see the false hit: {out}"
        );
        assert!(parse_grep_output(&out, &hex).is_empty());
    }

    #[test]
    fn grep_finds_matches_across_xxd_lines_and_chunk_boundaries() {
        let base = 0x7000_0000;
        let pat = vec![0xb8, 0xf3, 0x03, 0x00];
        let mut mem = vec![0u8; 3 * 4096];
        // Straddles the first 30-byte xxd line, straddles the 4096-byte chunk
        // boundary, first byte of the last chunk, last bytes of the region.
        let at = [28, 4096 - 2, 2 * 4096, 3 * 4096 - 4];
        for &a in &at {
            mem[a..a + 4].copy_from_slice(&pat);
        }
        let hex = vec![hex_encode(&pat)];
        let mut calls = Vec::new();
        let hits = grep_regions(
            42,
            &[region(base, base + mem.len() as u64)],
            &[pat],
            4096,
            fake_runner(&mem, base, None, &hex, &mut calls),
        )
        .unwrap();
        let want: Vec<(u64, usize)> = at.iter().map(|&a| (base + a as u64, 0)).collect();
        assert_eq!(hits, want);
        // One chunk per page, each reading one overlap page.
        let first = base / 4096;
        assert_eq!(calls, vec![(first, 2), (first + 1, 2), (first + 2, 2)]);
    }

    #[test]
    fn failing_chunk_is_skipped_not_fatal() {
        let base = 0x1000_0000;
        let pat = vec![0x11, 0x22, 0x33];
        let mut mem = vec![0u8; 3 * 4096];
        mem[10..13].copy_from_slice(&pat);
        mem[2 * 4096 + 100..2 * 4096 + 103].copy_from_slice(&pat);
        let hex = vec![hex_encode(&pat)];
        let mut calls = Vec::new();
        // Page 1 fails: chunks 0 (reads 0..2) and 1 (reads 1..3) both die.
        let hits = grep_regions(
            1,
            &[region(base, base + mem.len() as u64)],
            &[pat],
            4096,
            fake_runner(&mem, base, Some(base / 4096 + 1), &hex, &mut calls),
        )
        .unwrap();
        assert_eq!(hits, vec![(base + 2 * 4096 + 100, 0)]);
        assert_eq!(calls.len(), 3);
    }

    #[test]
    fn multiple_patterns_report_their_index() {
        let base = 0x2000;
        let mut mem = vec![0u8; 4096];
        mem[0..2].copy_from_slice(&[0xaa, 0xbb]);
        mem[100..103].copy_from_slice(&[0x01, 0x02, 0x03]);
        let pats = vec![vec![0x01, 0x02, 0x03], vec![0xaa, 0xbb]];
        let hex: Vec<String> = pats.iter().map(|p| hex_encode(p)).collect();
        let mut calls = Vec::new();
        let hits = grep_regions(
            1,
            &[region(base, base + 4096)],
            &pats,
            1 << 20,
            fake_runner(&mem, base, None, &hex, &mut calls),
        )
        .unwrap();
        assert_eq!(hits, vec![(base, 1), (base + 100, 0)]);
    }

    #[test]
    fn invalid_patterns_are_rejected_before_any_shell_call() {
        let run = |_: &str| -> Result<String> { panic!("must not run") };
        assert!(grep_regions(1, &[region(0, 4096)], &[], 4096, run).is_err());
        assert!(grep_regions(1, &[region(0, 4096)], &[vec![]], 4096, run).is_err());
        let huge = vec![vec![0u8; GREP_MAX_PATTERN + 1]];
        assert!(grep_regions(1, &[region(0, 4096)], &huge, 4096, run).is_err());
    }
}

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
    /// to whole pages; 1 MiB is a good default). Only matches inside
    /// `[start, end)` of a region are reported, so a region may start
    /// unaligned. A chunk the device cannot read is logged and skipped; if
    /// no chunk at all can be read (no root, dead pid) this is an error.
    /// Scanning stops early once `limit` matches are found (0 = unlimited).
    ///
    /// Returns `(absolute address, pattern index)` pairs sorted by address.
    pub fn grep_memory(
        &self,
        pid: u32,
        regions: &[MemoryRegion],
        patterns: &[Vec<u8>],
        chunk: u32,
        limit: usize,
    ) -> Result<Vec<(u64, usize)>> {
        grep_regions(pid, regions, patterns, chunk, limit, |cmd| {
            self.run_adb_shell(cmd)
        })
    }
}

/// Core of [`AdbReader::grep_memory`], with the shell runner injected for tests.
fn grep_regions(
    pid: u32,
    regions: &[MemoryRegion],
    patterns: &[Vec<u8>],
    chunk: u32,
    limit: usize,
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
    // Hex-encoding here is also the injection guard: only [0-9a-f ] reaches the shell.
    let tokens: Vec<String> = patterns.iter().map(|p| hex_tokens(p)).collect();
    let chunk = u64::from(chunk.max(1)).div_ceil(PAGE) * PAGE;

    let mut hits = Vec::new();
    let mut readable = 0usize;
    let mut last_err = None;
    'scan: for r in regions {
        let mut addr = r.start - r.start % PAGE;
        while addr < r.end {
            let len = (r.end - addr).min(chunk);
            // One extra page so a match starting in this chunk but ending in
            // the next is still seen; `< addr + len` gives each start to exactly
            // one chunk, so overlapping chunks never report a match twice.
            let cmd = grep_chunk_command(pid, addr / PAGE, len.div_ceil(PAGE) + 1, &tokens);
            match run(&cmd).and_then(|out| parse_grep_output(&out, &tokens)) {
                Ok((found, read)) => {
                    readable += 1;
                    if read < len {
                        warn!("hot scan: short read at {addr:#x}: {read:#x} of {len:#x} bytes");
                    }
                    hits.extend(
                        found
                            .into_iter()
                            .map(|(off, idx)| (addr + off, idx))
                            .filter(|&(a, _)| a >= r.start && a < addr + len),
                    );
                }
                Err(e) => {
                    warn!("hot scan: skipping unreadable chunk {addr:#x}+{len:#x}: {e:#}");
                    last_err = Some(e);
                }
            }
            addr += len;
            if limit > 0 && hits.len() >= limit {
                break 'scan;
            }
        }
    }
    if let (0, Some(e)) = (readable, last_err) {
        return Err(e.context(format!("hot scan: no memory of pid {pid} was readable")));
    }
    hits.sort_unstable();
    hits.dedup();
    if limit > 0 {
        hits.truncate(limit);
    }
    Ok(hits)
}

/// Bytes per od output line: `-w256` prints 256 bytes, each as `"xx"` joined
/// by single spaces with NO trailing space on the line, after `sed 's/^ //'`
/// strips the leading space — 767 hex chars (`256*3 - 1`). With the trailing
/// newline, one stream line occupies 768 chars.
pub const OD_LINE_BYTES: u64 = 256;
/// Stream chars per od line (hex chars + newline); grep's `-b` offsets are
/// global stream offsets, so a line with global offset `off` starts at byte
/// `(off / 768) * 256` and a match at char `at` inside it is byte `+ at/3`.
pub const OD_LINE_CHARS: u64 = 768;

/// Device command that greps `count` pages from page `skip` of `/proc/<pid>/mem`.
///
/// grep cannot take NUL bytes in `-e` patterns, so memory and patterns are
/// both compared as hex text. `od -An -tx1 -v -w256 | sed 's/^ //'` prints
/// 256 bytes per line (`"b8 f3 03 00 ..."`, 767 chars + newline), so a 4-16
/// byte pattern only straddles a line break when it starts in the last
/// (len-1) bytes of a line (~0.4-1.2% loss for 4-8 byte patterns, acceptable
/// for a hot scan; re-check with `spectre dump`). toybox grep's `-b` reports
/// ONE global offset per line and DROPS the offset for later matches in the
/// same line when combined with `-o`, so this uses plain `-b` and the Rust
/// side scans the whole line content (every real hit starts on a byte
/// boundary: char index % 3 == 0 preceded by space or line start).
/// Patterns are trimmed of the trailing space (hex_tokens emits `"b8 f3 "`
/// for shell safety; od lines have no trailing space).
/// `echo end` lands as its own line; its offset proves the root shell ran
/// and tells how much dd read (`0:end` means nothing was readable).
///
/// `tokens` must come from [`hex_tokens`] (shell-safe `[0-9a-f ]`).
fn grep_chunk_command(pid: u32, skip: u64, count: u64, tokens: &[String]) -> String {
    let es: String = tokens.iter().map(|t| format!(" -e \"{}\"", t.trim_end())).collect();
    let body = format!(
        "dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null | od -An -tx1 -v -w256 | sed 's/^ //'; echo end"
    );
    format!("su -c '({body}) | grep -bF{es} -e end' 2>/dev/null")
}
fn parse_grep_output(output: &str, tokens: &[String]) -> Result<(Vec<(u64, usize)>, u64)> {
    let mut hits = Vec::new();
    let mut end = None;
    for line in output.lines() {
        let Some((off, content)) = line.split_once(':') else {
            continue;
        };
        let Ok(off) = off.trim().parse::<u64>() else {
            continue;
        };
        let content = content.trim_end_matches('\r');
        if content.trim() == "end" {
            end = Some(off);
            continue;
        }
        // toybox grep -b reports ONE offset per line (the line start) and
        // DROPS offsets for later matches in the same line (-o makes it worse),
        // so we scan the whole line content here. Every real hit must start on
        // a byte boundary: index % 3 == 0 preceded by space or line start.
        // (od's last byte of a line has no trailing space, so a token must
        // not rely on a trailing space; hex_tokens tokens are trimmed.)
        for (ti, tok) in tokens.iter().enumerate() {
            let tok = tok.trim_end();
            let mut from = 0;
            while let Some(at) = content[from..].find(tok) {
                let at = from + at;
                let ok_boundary = at % 3 == 0 && (at == 0 || content.as_bytes()[at - 1] == b' ');
                if ok_boundary {
                    let byte = (off / OD_LINE_CHARS) * OD_LINE_BYTES + (at as u64 / 3);
                    hits.push((byte, ti));
                }
                from = at + 1;
            }
        }
    }
    match end {
        Some(off) if off > 0 => {
            let full = (off / OD_LINE_CHARS) * OD_LINE_BYTES;
            // A partial last line of b bytes prints 3b-1 hex chars + newline
            // = 3b stream chars, so tail = (off % 768) / 3.
            let tail = (off % OD_LINE_CHARS) / 3;
            Ok((hits, full + tail))
        }
        _ => bail!("device read no memory (no root, dead pid or unreadable page)"),
    }
}

/// One `"xx "` token per byte, the format `xxd -p -c1 | tr "\n" " "` produces.
fn hex_tokens(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x} ")).collect()
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

    /// What `dd | od -An -tx1 -v -w256; echo end | grep -boF -e ... -e end`
    /// prints for `data` (checked against the real tools): od emits lines of
    /// up to 256 bytes (`256*3=768` chars + newline); grep -b reports the
    /// GLOBAL stream char offset of each (first) match per line, with `end`
    /// as its own line. toybox reports one offset per line — we keep that.
        /// Emulates `dd | od -An -tx1 -v -w256 | sed 's/^ //'; echo end | grep -bF`
    /// on the device (verified against real Android toybox): od emits lines of
    /// up to 256 bytes with NO trailing space (`256*3-1` hex chars), grep -b
    /// prints each MATCHING line as `GLOBAL_LINE_START:line-content` (one
    /// offset per line — toybox drops offsets for later matches, so we mimic
    /// plain -b), and `end` is always its own last line.
    /// A pattern straddling a 256-byte line break is invisible to grep (real
    /// behaviour, ~0.4-1.2% loss for 4-8 byte patterns) and not emitted.
    fn fake_device_grep(data: &[u8], tokens: &[String]) -> String {
        let mut out = String::new();
        let mut global = 0usize;
        for chunk in data.chunks(OD_LINE_BYTES as usize) {
            let content = hex_space(chunk);
            let matches = tokens.iter().any(|t| content.contains(t.trim_end()));
            if matches {
                out.push_str(&format!("{global}:{content}\n"));
            }
            global += content.len() + 1;
        }
        out.push_str(&format!("{global}:end\n"));
        out
    }

    /// od-style hex line: `"b8 f3 03 00"` (no trailing space).
    fn hex_space(data: &[u8]) -> String {
        data.iter()
            .map(|b| format!("{b:02x}"))
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Runner simulating `/proc/<pid>/mem` holding `mem` at `base`; dd stops
    /// at `failing_page` like a real read error.
    fn fake_runner<'a>(
        mem: &'a [u8],
        base: u64,
        failing_page: Option<u64>,
        tokens: &'a [String],
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
            let (skip, mut count) = (arg("skip="), arg("count="));
            calls.push((skip, count));
            if let Some(p) = failing_page.filter(|p| (skip..skip + count).contains(p)) {
                count = p - skip;
            }
            let from = (skip * 4096 - base) as usize;
            let to = (from + (count * 4096) as usize).min(mem.len());
            Ok(fake_device_grep(&mem[from.min(to)..to], tokens))
        }
    }

    type Hits = Vec<(u64, usize)>;

    fn scan(
        mem: &[u8],
        base: u64,
        regions: &[MemoryRegion],
        pats: &[Vec<u8>],
        chunk: u32,
        limit: usize,
        failing_page: Option<u64>,
    ) -> (Result<Hits>, Vec<(u64, u64)>) {
        let tokens: Vec<String> = pats.iter().map(|p| hex_tokens(p)).collect();
        let mut calls = Vec::new();
        let run = fake_runner(mem, base, failing_page, &tokens, &mut calls);
        let hits = grep_regions(1, regions, pats, chunk, limit, run);
        (hits, calls)
    }

    #[test]
    fn hex_tokens_are_lowercase_space_separated_bytes() {
        assert_eq!(hex_tokens(&[0xde, 0xAD, 0x00, 0x0f]), "de ad 00 0f ");
    }

    #[test]
    fn command_contains_only_numeric_and_hex_inputs() {
        let cmd = grep_chunk_command(1234, 5, 257, &[hex_tokens(&[0xb8, 0xf3]), "00 ".into()]);
        assert_eq!(
            cmd,
            "su -c '(dd if=/proc/1234/mem bs=4096 skip=5 count=257 2>/dev/null | od -An -tx1 -v -w256 | sed 's/^ //'; echo end) | grep -bF -e \"b8 f3\" -e \"00\" -e end' 2>/dev/null"
        );
        // Two quotes wrap the su -c script; sed 's/^ //' adds two more.
        assert_eq!(cmd.matches('\'').count(), 4);
    }

    #[test]
    fn parser_maps_char_offsets_to_bytes_and_reads_sentinel() {
        let tokens = vec![
            hex_tokens(&[0xb8, 0xf3, 0x03, 0x00]),
            hex_tokens(&[0xde, 0xad]),
        ];
        // Two od -w256 lines (each 767 hex chars + newline = 768 stream chars).
        // Line 1 starts at global 0 and holds our 4-byte token at byte 16
        // (chars 48); line 2 starts at global 768 and holds "de ad" at byte 5
        // (chars 15). "ca fe" on line 1 is not one of our tokens.
        let mut l1 = hex_space(&[0u8; 256]);
        l1.replace_range(16 * 3..16 * 3 + 11, "b8 f3 03 00");
        let mut l2 = hex_space(&[0u8; 256]);
        l2.replace_range(5 * 3..5 * 3 + 5, "de ad");
        let out = format!("0:{l1}\n768:{l2}\n1536:end\n");
        let (hits, read) = parse_grep_output(&out, &tokens).unwrap();
        assert_eq!(hits, vec![(16, 0), (256 + 5, 1)]);
        assert_eq!(read, 512);
    }

    #[test]
    fn missing_or_empty_sentinel_is_an_error() {
        let tokens = vec![hex_tokens(&[0])];
        // su denied (nothing) or dd read nothing (`0:end`): both are errors.
        for out in ["", "0:end\n"] {
            assert!(parse_grep_output(out, &tokens).is_err(), "{out:?}");
        }
    }

    #[test]
    fn mid_byte_hit_cannot_hide_real_match() {
        // Hex "1000000000": a mid-byte "00000000" at nibble 1 used to swallow
        // the real u32 zero at byte 1.
        let tokens = vec![hex_tokens(&[0; 4])];
        let out = fake_device_grep(&[0x10, 0, 0, 0, 0], &tokens);
        assert_eq!(parse_grep_output(&out, &tokens).unwrap(), (vec![(1, 0)], 5));
        // Hex "0010000001000000": u32 1 at byte 4 used to be lost the same way.
        let tokens = vec![hex_tokens(&[1, 0, 0, 0])];
        let out = fake_device_grep(&[0, 0x10, 0, 0, 1, 0, 0, 0], &tokens);
        assert_eq!(parse_grep_output(&out, &tokens).unwrap(), (vec![(4, 0)], 8));
    }

    #[test]
    fn grep_finds_matches_across_chunk_boundaries() {
        let base = 0x7000_0000;
        let pat = vec![0xb8, 0xf3, 0x03, 0x00];
        let mut mem = vec![0u8; 3 * 4096];
        // Straddles the 4096-byte chunk boundary, first byte of the last
        // chunk, last bytes of the region. (4096-2 is deliberately NOT used:
        // it would straddle a 256-byte od line, invisible to device grep.)
        let at = [28, 4096 - 8, 2 * 4096, 3 * 4096 - 4];
        for &a in &at {
            mem[a..a + 4].copy_from_slice(&pat);
        }
        let reg = [region(base, base + mem.len() as u64)];
        let (hits, calls) = scan(&mem, base, &reg, &[pat], 4096, 0, None);
        let want: Vec<(u64, usize)> = at.iter().map(|&a| (base + a as u64, 0)).collect();
        assert_eq!(hits.unwrap(), want);
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
        mem[4096 + 50..4096 + 53].copy_from_slice(&pat);
        mem[2 * 4096 + 100..2 * 4096 + 103].copy_from_slice(&pat);
        let reg = [region(base, base + mem.len() as u64)];
        // Page 1 is unreadable: chunk 0 still reads its own page (dd stops at
        // the overlap page), chunk 1 reads nothing and is skipped.
        let (hits, calls) = scan(&mem, base, &reg, &[pat], 4096, 0, Some(base / 4096 + 1));
        assert_eq!(
            hits.unwrap(),
            vec![(base + 10, 0), (base + 2 * 4096 + 100, 0)]
        );
        assert_eq!(calls.len(), 3);
    }

    #[test]
    fn nothing_readable_is_an_error_not_zero_matches() {
        let base = 0x1000_0000;
        let mem = vec![0u8; 4096];
        let reg = [region(base, base + 4096)];
        // dd reads nothing (no root / dead pid).
        let (hits, _) = scan(&mem, base, &reg, &[vec![0]], 4096, 0, Some(base / 4096));
        assert!(hits.is_err());
        // su denied: run_adb_shell fails on the empty output.
        let run = |_: &str| -> Result<String> { bail!("adb shell failed") };
        assert!(grep_regions(1, &reg, &[vec![0]], 4096, 0, run).is_err());
    }

    #[test]
    fn unaligned_region_start_and_limit_across_regions() {
        let base = 0x4000;
        let pat = vec![0xaa, 0xbb];
        let mut mem = vec![0u8; 3 * 4096];
        for a in [0x10, 0x100, 0x200, 2 * 4096 + 8, 2 * 4096 + 16] {
            mem[a..a + 2].copy_from_slice(&pat);
        }
        // First region starts mid-page (e.g. clipped to --base 0x4080).
        let regs = [
            region(base + 0x80, base + 4096),
            region(base + 2 * 4096, base + 3 * 4096),
        ];
        let (hits, _) = scan(&mem, base, &regs, std::slice::from_ref(&pat), 4096, 0, None);
        let addrs: Vec<u64> = hits.unwrap().iter().map(|h| h.0).collect();
        assert_eq!(
            addrs,
            vec![
                base + 0x100,
                base + 0x200,
                base + 2 * 4096 + 8,
                base + 2 * 4096 + 16
            ]
        );
        // --limit 3 stops in the second region and keeps the lowest three.
        let (hits, calls) = scan(&mem, base, &regs, std::slice::from_ref(&pat), 4096, 3, None);
        let addrs: Vec<u64> = hits.unwrap().iter().map(|h| h.0).collect();
        assert_eq!(addrs, vec![base + 0x100, base + 0x200, base + 2 * 4096 + 8]);
        assert_eq!(calls.len(), 2);
        // --limit 2 is met by the first region: the second is never read.
        let (_, calls) = scan(&mem, base, &regs, &[pat], 4096, 2, None);
        assert_eq!(calls.len(), 1);
    }

    #[test]
    fn multiple_patterns_report_their_index() {
        let base = 0x2000;
        let mut mem = vec![0u8; 4096];
        mem[0..2].copy_from_slice(&[0xaa, 0xbb]);
        mem[100..103].copy_from_slice(&[0x01, 0x02, 0x03]);
        let pats = vec![vec![0x01, 0x02, 0x03], vec![0xaa, 0xbb]];
        let (hits, _) = scan(
            &mem,
            base,
            &[region(base, base + 4096)],
            &pats,
            1 << 20,
            0,
            None,
        );
        assert_eq!(hits.unwrap(), vec![(base, 1), (base + 100, 0)]);
    }

    #[test]
    fn invalid_patterns_are_rejected_before_any_shell_call() {
        let run = |_: &str| -> Result<String> { panic!("must not run") };
        assert!(grep_regions(1, &[region(0, 4096)], &[], 4096, 0, run).is_err());
        assert!(grep_regions(1, &[region(0, 4096)], &[vec![]], 4096, 0, run).is_err());
        let huge = vec![vec![0u8; GREP_MAX_PATTERN + 1]];
        assert!(grep_regions(1, &[region(0, 4096)], &huge, 4096, 0, run).is_err());
    }
}

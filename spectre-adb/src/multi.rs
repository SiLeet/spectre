//! Multi-device orchestration: discover every attached ADB device and talk
//! to all of them at once.
//!
//! ```no_run
//! use spectre_adb::AdbManager;
//!
//! let manager = AdbManager::discover()?;
//! for (pid, serial) in manager.find_process_on_all("com.example.game") {
//!     println!("{serial}: pid {pid}");
//! }
//! # Ok::<(), anyhow::Error>(())
//! ```
//!
//! # How readers are built
//!
//! Every reader is created through [`AdbReader::with_serial`], so commands
//! can always be routed with `adb -s <serial> shell ...`. The reader also
//! needs a `host:port` (it issues a best-effort, result-ignored
//! `adb connect <host>:<port>` before each command); [`reader_for_serial`]
//! derives it from the serial:
//!
//! | serial              | host:port used           | why                                        |
//! |---------------------|--------------------------|--------------------------------------------|
//! | `127.0.0.1:5555`    | `127.0.0.1:5555`         | TCP transport — reconnect is a no-op       |
//! | `emulator-5554`     | `localhost:5555`         | AVD adb port is console port + 1           |
//! | `R58M123ABC` (USB)  | `localhost:5555`         | no TCP endpoint; reader default, see below |
//!
//! For USB serials there is no TCP endpoint, but `AdbReader` cannot skip its
//! connect step, so the reader default `localhost:5555` is used. This stays
//! correct: an un-targeted `adb shell` only succeeds when exactly one device
//! is online, and with several devices it fails ("more than one device") and
//! the reader retries with `-s <serial>`.

use std::process::Command;

use anyhow::{Context, Result, bail};
use spectre_core::reader::MemoryReader;
use tracing::{debug, info, warn};

use crate::reader::AdbReader;

/// Host used when a serial carries no TCP endpoint of its own.
const DEFAULT_HOST: &str = "localhost";
/// Port used when a serial carries no TCP endpoint of its own
/// (matches the CLI / `AdbConfig` default).
const DEFAULT_PORT: u16 = 5555;

/// Device states `adb devices` can report. Lines whose second column is not
/// one of these (e.g. "adb server version ... doesn't match") are noise.
const KNOWN_STATES: &[&str] = &[
    "device",
    "offline",
    "unauthorized",
    "authorizing",
    "connecting",
    "bootloader",
    "recovery",
    "rescue",
    "sideload",
    "host",
    "detached",
    "unknown",
];

// ── Device-list parsing ────────────────────────────────────────────────────

/// One entry of `adb devices [-l]` output.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdbDevice {
    /// Device serial as accepted by `adb -s` (e.g. `emulator-5554`,
    /// `127.0.0.1:5555`, `R58M123ABC`).
    pub serial: String,
    /// Connection state: `device`, `offline`, `unauthorized`,
    /// `no permissions`, ...
    pub state: String,
    /// `key:value` columns from `adb devices -l` (`product`, `model`,
    /// `device`, `transport_id`, `usb`), in output order.
    pub properties: Vec<(String, String)>,
}

impl AdbDevice {
    /// Whether the device is online and authorized (state `device`).
    pub fn is_ready(&self) -> bool {
        self.state == "device"
    }

    /// Look up a `-l` property such as `model` or `product`.
    pub fn property(&self, key: &str) -> Option<&str> {
        self.properties
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }
}

/// Parse the output of `adb devices` or `adb devices -l`.
///
/// Skips the `List of devices attached` header, blank lines, daemon noise
/// (`* daemon started successfully *`) and any line whose state column is
/// not a known adb state. Columns may be separated by tabs or spaces. The
/// multi-word state `no permissions (...)` is normalised to
/// `no permissions`.
pub fn parse_adb_devices(output: &str) -> Vec<AdbDevice> {
    output.lines().filter_map(parse_device_line).collect()
}

fn parse_device_line(line: &str) -> Option<AdbDevice> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('*') || line.starts_with("List of devices") {
        return None;
    }

    let mut tokens = line.split_whitespace();
    let serial = tokens.next()?;
    let first = tokens.next()?;

    let state = if first == "no" {
        // "no permissions (user in plugdev group; ...); see [http://...]"
        // — the explanation is free text, so nothing after it is parsed.
        if tokens.next()? != "permissions" {
            return None;
        }
        return Some(AdbDevice {
            serial: serial.to_owned(),
            state: "no permissions".to_owned(),
            properties: Vec::new(),
        });
    } else if KNOWN_STATES.contains(&first) {
        first.to_owned()
    } else {
        debug!("ignoring unrecognised adb devices line: {line}");
        return None;
    };

    let properties = tokens
        .filter_map(|t| t.split_once(':'))
        .map(|(k, v)| (k.to_owned(), v.to_owned()))
        .collect();

    Some(AdbDevice {
        serial: serial.to_owned(),
        state,
        properties,
    })
}

// ── Reader construction ────────────────────────────────────────────────────

/// Build an [`AdbReader`] that targets `serial`, deriving the `host:port`
/// for the reader's connect step (see the module docs for the rules).
pub fn reader_for_serial(serial: &str) -> AdbReader {
    let (host, port) = endpoint_for_serial(serial);
    AdbReader::with_serial(&host, port, serial)
}

fn endpoint_for_serial(serial: &str) -> (String, u16) {
    // TCP transports: "127.0.0.1:5555", "192.168.1.20:5037", "[::1]:5555".
    if let Some((host, port)) = serial.rsplit_once(':')
        && !host.is_empty()
        && let Ok(port) = port.parse::<u16>()
    {
        return (host.to_owned(), port);
    }

    // AVD emulators: "emulator-<console port>", adb listens on console + 1.
    if let Some(console) = serial.strip_prefix("emulator-")
        && let Ok(console) = console.parse::<u16>()
        && let Some(adb_port) = console.checked_add(1)
    {
        return (DEFAULT_HOST.to_owned(), adb_port);
    }

    (DEFAULT_HOST.to_owned(), DEFAULT_PORT)
}

// ── AdbManager ─────────────────────────────────────────────────────────────

/// A set of [`AdbReader`]s, one per ready ADB device.
#[derive(Debug, Default)]
pub struct AdbManager {
    pub readers: Vec<AdbReader>,
}

impl AdbManager {
    /// Wrap an existing set of readers.
    pub fn new(readers: Vec<AdbReader>) -> AdbManager {
        AdbManager { readers }
    }

    /// Run `adb devices -l` and build one reader per device in state
    /// `device`. Devices in any other state (unauthorized, offline,
    /// no permissions, ...) are skipped with a warning.
    ///
    /// Fails only if `adb` cannot be run or exits non-zero; an empty device
    /// list yields an empty manager.
    pub fn discover() -> Result<AdbManager> {
        let output = Command::new("adb")
            .args(["devices", "-l"])
            .output()
            .context("failed to run 'adb devices' — is adb on PATH?")?;
        if !output.status.success() {
            bail!(
                "adb devices failed (exit={}): {}",
                output.status,
                String::from_utf8_lossy(&output.stderr).trim()
            );
        }

        let manager = AdbManager::from_devices_output(&String::from_utf8_lossy(&output.stdout));
        info!("discovered {} ready ADB device(s)", manager.readers.len());
        Ok(manager)
    }

    /// Build a manager from already captured `adb devices [-l]` output.
    /// Non-ready devices are skipped with a warning.
    pub fn from_devices_output(output: &str) -> AdbManager {
        let readers = parse_adb_devices(output)
            .into_iter()
            .filter(|dev| {
                if !dev.is_ready() {
                    warn!("skipping ADB device {} (state: {})", dev.serial, dev.state);
                }
                dev.is_ready()
            })
            .map(|dev| {
                debug!(
                    "adding ADB device {} (model: {})",
                    dev.serial,
                    dev.property("model").unwrap_or("-")
                );
                reader_for_serial(&dev.serial)
            })
            .collect();
        AdbManager { readers }
    }

    /// Search every reader for processes whose name contains `name`
    /// (case-insensitive, via [`MemoryReader::find_process`]).
    ///
    /// Readers are queried in parallel (one thread each). Returns
    /// `(pid, serial)` pairs in reader order; readers without a serial are
    /// identified as `host:port`. A failing reader is logged with a warning
    /// and skipped.
    pub fn find_process_on_all(&self, name: &str) -> Vec<(u32, String)> {
        std::thread::scope(|scope| {
            let handles: Vec<_> = self
                .readers
                .iter()
                .map(|reader| (reader, scope.spawn(move || reader.find_process(name))))
                .collect();

            let mut hits = Vec::new();
            for (reader, handle) in handles {
                let id = reader_id(reader);
                match handle.join() {
                    Ok(Ok(procs)) => hits.extend(procs.into_iter().map(|p| (p.pid, id.clone()))),
                    Ok(Err(err)) => warn!("find_process on {id} failed: {err:#}"),
                    Err(_) => warn!("find_process on {id} panicked"),
                }
            }
            hits
        })
    }
}

fn reader_id(reader: &AdbReader) -> String {
    reader
        .serial
        .clone()
        .unwrap_or_else(|| format!("{}:{}", reader.host, reader.port))
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn states(devs: &[AdbDevice]) -> Vec<(&str, &str)> {
        devs.iter()
            .map(|d| (d.serial.as_str(), d.state.as_str()))
            .collect()
    }

    #[test]
    fn parses_plain_output_with_mixed_states() {
        let out = "List of devices attached\n\
                   emulator-5554\tdevice\n\
                   127.0.0.1:5565\tdevice\n\
                   R58M123ABC\tunauthorized\n\
                   127.0.0.1:5575\toffline\n\
                   \n";
        let devs = parse_adb_devices(out);
        assert_eq!(
            states(&devs),
            vec![
                ("emulator-5554", "device"),
                ("127.0.0.1:5565", "device"),
                ("R58M123ABC", "unauthorized"),
                ("127.0.0.1:5575", "offline"),
            ]
        );
        assert!(devs.iter().all(|d| d.properties.is_empty()));
        assert_eq!(devs.iter().filter(|d| d.is_ready()).count(), 2);
    }

    #[test]
    fn parses_long_format_with_properties() {
        let out = "List of devices attached\n\
                   emulator-5554          device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 device:emu64xa transport_id:1\n\
                   127.0.0.1:5555         device product:SM-S908E model:SM_S908E device:star2qltechn transport_id:3\n\
                   0123456789ABCDEF       unauthorized usb:1-4 transport_id:4\n";
        let devs = parse_adb_devices(out);
        assert_eq!(
            states(&devs),
            vec![
                ("emulator-5554", "device"),
                ("127.0.0.1:5555", "device"),
                ("0123456789ABCDEF", "unauthorized"),
            ]
        );
        assert_eq!(devs[1].property("model"), Some("SM_S908E"));
        assert_eq!(devs[1].property("transport_id"), Some("3"));
        assert_eq!(devs[2].property("usb"), Some("1-4"));
        assert_eq!(devs[0].property("missing"), None);
    }

    #[test]
    fn skips_daemon_noise_and_handles_no_permissions() {
        let out = "* daemon not running; starting now at tcp:5037\n\
                   * daemon started successfully *\n\
                   List of devices attached\n\
                   \n\
                   emulator-5556 device\n\
                   0123456789ABCDEF\tno permissions (user in plugdev group; are your udev rules wrong?); see [http://developer.android.com/tools/device.html]\n\
                   \n";
        let devs = parse_adb_devices(out);
        assert_eq!(
            states(&devs),
            vec![
                ("emulator-5556", "device"),
                ("0123456789ABCDEF", "no permissions"),
            ]
        );
        assert!(devs[1].properties.is_empty());
    }

    #[test]
    fn ignores_unrecognised_lines() {
        let out = "adb server version (40) doesn't match this client (41); killing...\n\
                   List of devices attached\n\
                   emulator-5554\tdevice\n";
        assert_eq!(
            states(&parse_adb_devices(out)),
            vec![("emulator-5554", "device")]
        );
    }

    #[test]
    fn parses_empty_list() {
        assert!(parse_adb_devices("List of devices attached\n\n").is_empty());
        assert!(parse_adb_devices("").is_empty());
    }

    #[test]
    fn derives_endpoint_from_serial() {
        assert_eq!(
            endpoint_for_serial("127.0.0.1:5555"),
            ("127.0.0.1".to_owned(), 5555)
        );
        assert_eq!(
            endpoint_for_serial("192.168.1.20:37000"),
            ("192.168.1.20".to_owned(), 37000)
        );
        assert_eq!(
            endpoint_for_serial("[::1]:5555"),
            ("[::1]".to_owned(), 5555)
        );
        assert_eq!(
            endpoint_for_serial("emulator-5554"),
            ("localhost".to_owned(), 5555)
        );
        assert_eq!(
            endpoint_for_serial("emulator-5556"),
            ("localhost".to_owned(), 5557)
        );
        assert_eq!(
            endpoint_for_serial("R58M123ABC"),
            ("localhost".to_owned(), 5555)
        );
        assert_eq!(
            endpoint_for_serial("host:notaport"),
            ("localhost".to_owned(), 5555)
        );
    }

    #[test]
    fn reader_for_serial_sets_serial() {
        let reader = reader_for_serial("127.0.0.1:5565");
        assert_eq!(reader.host, "127.0.0.1");
        assert_eq!(reader.port, 5565);
        assert_eq!(reader.serial.as_deref(), Some("127.0.0.1:5565"));
    }

    #[test]
    fn manager_keeps_only_ready_devices() {
        let out = "List of devices attached\n\
                   emulator-5554\tdevice\n\
                   127.0.0.1:5565\tdevice\n\
                   R58M123ABC\tunauthorized\n\
                   127.0.0.1:5575\toffline\n";
        let manager = AdbManager::from_devices_output(out);
        let serials: Vec<_> = manager.readers.iter().map(reader_id).collect();
        assert_eq!(serials, vec!["emulator-5554", "127.0.0.1:5565"]);
    }

    #[test]
    fn manager_from_empty_list_is_empty() {
        let manager = AdbManager::from_devices_output("List of devices attached\n\n");
        assert!(manager.readers.is_empty());
        assert!(manager.find_process_on_all("game").is_empty());
    }

    #[test]
    fn reader_id_falls_back_to_host_port() {
        assert_eq!(
            reader_id(&AdbReader::new("10.0.0.5", 5555)),
            "10.0.0.5:5555"
        );
    }
}

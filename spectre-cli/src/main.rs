//! Spectre CLI — user-facing command-line interface for memory scanning and bot control.
//!
//! Usage:
//!   spectre scan <game> [--pid P] [--offsets PATH] [--format table|json|yaml] [--output PATH]
//!                       [--adb [--adb-host H] [--adb-port P]]
//!   spectre dump <pid> <address> <size> [--output PATH] [--format hex|raw|ascii] [--adb]
//!   spectre dumpdiff <old> <new> [--base ADDR] [--json]
//!   spectre find <name> [--json] [--adb]
//!   spectre regions <pid> [--filter PERMS] [--json] [--adb]
//!   spectre search <pid> <type> <value> [--limit N] [--continue] [--state PATH]
//!   spectre bot <config.yaml> [--once] [--name N] [--dry-run]
//!   spectre info [--json]
//!   spectre adb list | adb ping [serial]
//!
//! Global flags: --version, --verbose (repeat for more detail).

use std::collections::HashMap;
use std::path::Path;
use std::process::{Command, ExitCode};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, anyhow, bail};
use structopt::StructOpt;
use tracing::{debug, info, warn};

use spectre_core::{
    FieldDef, FieldType, GameOffsets, MemoryReader, MemoryRegion, PatternField, ScanConfig,
    ScanPattern, ScanReport, ScanValue, StructDef, ValueType, scan_memory,
};

// ── Top-Level CLI ────────────────────────────────────────────────────────────

#[derive(StructOpt)]
#[structopt(
    name = "spectre",
    about = "Spectre — mobile game memory reading and bot framework",
    version = env!("CARGO_PKG_VERSION")
)]
pub struct CliArgs {
    /// Enable verbose logging (repeat for more detail).
    #[structopt(short = "v", long = "verbose", parse(from_occurrences))]
    pub verbose: u8,

    /// Subcommand to execute.
    #[structopt(subcommand)]
    pub command: Option<SubCommand>,
}

// ── Subcommands ──────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub enum SubCommand {
    /// Scan a running game for known structures.
    #[structopt(about = "Scan a running game for known data structures")]
    Scan(ScanArgs),

    /// Dump raw bytes from a process address.
    #[structopt(about = "Dump raw memory bytes from a process address")]
    Dump(DumpArgs),

    /// Find a process by name substring.
    #[structopt(about = "Find processes by name")]
    Find(FindArgs),

    /// List memory regions of a process.
    #[structopt(about = "List memory regions of a process")]
    Regions(RegionsArgs),

    /// Run a bot from a config file.
    #[structopt(about = "Run a bot automation script")]
    Bot(BotArgs),

    /// Search memory for a value (Cheat-Engine style, with refinement).
    #[structopt(about = "Search memory for a value; refine previous results")]
    Search(SearchArgs),

    /// Execute a Lua bot script.
    #[structopt(about = "Execute a Lua bot script")]
    Script(ScriptArgs),

    /// Show version and available backend info.
    #[structopt(about = "Show version and available backends")]
    Info(InfoArgs),

    /// ADB device management.
    #[structopt(about = "ADB device management")]
    Adb(AdbArgs),

    /// Compare two raw dump files byte-by-byte.
    #[structopt(
        name = "dumpdiff",
        about = "Compare two raw dump files and show changed offsets"
    )]
    DumpDiff(DumpDiffArgs),
}

// ── Scan Command ─────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct ScanArgs {
    /// Game name (e.g. "afk-journey"). Loads the corresponding offset file.
    #[structopt(name = "game")]
    pub game: String,

    /// PID of the target process (auto-detect if omitted).
    #[structopt(short = "p", long = "pid")]
    pub pid: Option<u32>,

    /// Path to a custom offsets YAML file.
    #[structopt(short = "o", long = "offsets")]
    pub offsets: Option<String>,

    /// Output format: table (default), json, yaml.
    #[structopt(short = "f", long = "format")]
    pub format: Option<String>,

    /// Write results to this file instead of stdout.
    #[structopt(short = "O", long = "output")]
    pub output: Option<String>,

    /// Use ADB backend instead of native.
    #[structopt(long = "adb")]
    pub adb: bool,

    /// ADB host (default: localhost).
    #[structopt(long = "adb-host")]
    pub adb_host: Option<String>,

    /// ADB port (default: 5555).
    #[structopt(long = "adb-port")]
    pub adb_port: Option<u16>,

    /// Scan an offline memory dump file instead of a live process.
    #[structopt(long = "dump")]
    pub dump: Option<String>,

    /// Virtual address of the first byte in the dump file (default: 0).
    #[structopt(long = "dump-base", default_value = "0")]
    pub dump_base: String,
}

// ── Search Command ───────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct SearchArgs {
    /// Process ID (omit when using --continue).
    #[structopt(name = "pid", required_unless = "continue")]
    pub pid: Option<u32>,

    /// Value type: u8/u16/u32/u64/i8/i16/i32/i64/f32/f64.
    #[structopt(name = "type")]
    pub value_type: String,

    /// Value to find (decimal, hex with 0x, or float).
    #[structopt(name = "value")]
    pub value: String,

    /// Refine the previous search results instead of scanning all memory.
    #[structopt(long = "continue")]
    pub continue_search: bool,

    /// State file for previous/next search (default: .spectre-search.json).
    #[structopt(long = "state")]
    pub state: Option<String>,

    /// Stop after N results (0 = unlimited).
    #[structopt(long = "limit", default_value = "0")]
    pub limit: u32,

    /// Output as JSON.
    #[structopt(long = "json")]
    pub json: bool,

    /// Use ADB backend.
    #[structopt(long = "adb")]
    pub adb: bool,
}

// ── Dump Command ─────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct DumpArgs {
    /// Process ID.
    #[structopt(name = "pid")]
    pub pid: u32,

    /// Starting address (hex with 0x prefix, or decimal).
    #[structopt(name = "address")]
    pub address: String,

    /// Number of bytes to dump.
    #[structopt(name = "size")]
    pub size: u32,

    /// Output file (default: stdout).
    #[structopt(short = "o", long = "output")]
    pub output: Option<String>,

    /// Output format: hex (default), raw, ascii.
    #[structopt(short = "f", long = "format")]
    pub format: Option<String>,

    /// Use ADB backend.
    #[structopt(long = "adb")]
    pub adb: bool,
}

// ── DumpDiff Command ─────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct DumpDiffArgs {
    /// Older raw dump file (e.g. from `spectre dump --format raw`).
    #[structopt(name = "old")]
    pub old: String,

    /// Newer raw dump file of the same memory range.
    #[structopt(name = "new")]
    pub new: String,

    /// Virtual address of the first byte in both dumps; added to printed offsets.
    #[structopt(long = "base", default_value = "0")]
    pub base: String,

    /// Output as JSON (full hex, with file offset and address per region).
    #[structopt(long = "json")]
    pub json: bool,
}

// ── Find Command ─────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct FindArgs {
    /// Process name substring to search for.
    #[structopt(name = "name")]
    pub name: String,

    /// Output as JSON.
    #[structopt(long = "json")]
    pub json: bool,

    /// Use ADB backend.
    #[structopt(long = "adb")]
    pub adb: bool,
}

// ── Regions Command ──────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct RegionsArgs {
    /// Process ID.
    #[structopt(name = "pid")]
    pub pid: u32,

    /// Filter by permission substring (e.g. "rw", "r--").
    #[structopt(short = "f", long = "filter")]
    pub filter: Option<String>,

    /// Output as JSON.
    #[structopt(long = "json")]
    pub json: bool,

    /// Use ADB backend.
    #[structopt(long = "adb")]
    pub adb: bool,
}

// ── Bot Command ──────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct BotArgs {
    /// Path to bot configuration YAML file.
    #[structopt(name = "config")]
    pub config: String,

    /// Run once and exit (no scheduling loop).
    #[structopt(long = "once")]
    pub once: bool,

    /// Bot instance name (for multi-bot setups).
    #[structopt(short = "n", long = "name")]
    pub name: Option<String>,

    /// Dry run — validate config without executing.
    #[structopt(long = "dry-run")]
    pub dry_run: bool,
}

// ── Script Command ───────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct ScriptArgs {
    /// Path to a Lua script file.
    #[structopt(name = "script")]
    pub script: String,

    /// Input backend for bot.* actions (default: adb).
    #[structopt(long = "input-backend")]
    pub input_backend: Option<String>,
}

// ── Info Command ─────────────────────────────────────────────────────────────

#[derive(StructOpt)]
pub struct InfoArgs {
    /// Output as JSON.
    #[structopt(long = "json")]
    pub json: bool,
}

// ── Adb Command ──────────────────────────────────────────────────────────────

#[derive(StructOpt)]
#[structopt(about = "ADB device management")]
pub struct AdbArgs {
    #[structopt(subcommand)]
    pub sub: AdbSubCommand,
}

#[derive(StructOpt)]
pub enum AdbSubCommand {
    /// List connected ADB devices.
    List,
    /// Ping an ADB device (serial optional — pings the default device if omitted).
    Ping(AdbPingArgs),
}

#[derive(StructOpt)]
pub struct AdbPingArgs {
    /// ADB device serial number.
    #[structopt(name = "serial")]
    pub serial: Option<String>,
}

// ── Main ─────────────────────────────────────────────────────────────────────

fn main() -> ExitCode {
    let args = CliArgs::from_args();
    init_logging(args.verbose);

    let result = match args.command {
        Some(SubCommand::Scan(cmd)) => run_scan(cmd),
        Some(SubCommand::Dump(cmd)) => run_dump(cmd),
        Some(SubCommand::Find(cmd)) => run_find(cmd),
        Some(SubCommand::Regions(cmd)) => run_regions(cmd),
        Some(SubCommand::Bot(cmd)) => run_bot(cmd),
        Some(SubCommand::Search(cmd)) => run_search(cmd),
        Some(SubCommand::Script(cmd)) => run_script(cmd),
        Some(SubCommand::Info(cmd)) => run_info(cmd),
        Some(SubCommand::Adb(cmd)) => run_adb(cmd),
        Some(SubCommand::DumpDiff(cmd)) => run_dumpdiff(cmd),
        None => {
            eprintln!("error: a subcommand is required; run `spectre --help` for usage");
            return ExitCode::from(2);
        }
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("error: {e:#}");
            ExitCode::from(1)
        }
    }
}

fn init_logging(verbose: u8) {
    use tracing_subscriber::filter::LevelFilter;

    let level = match verbose {
        0 => LevelFilter::WARN,
        1 => LevelFilter::INFO,
        2 => LevelFilter::DEBUG,
        _ => LevelFilter::TRACE,
    };
    let _ = tracing_subscriber::fmt().with_max_level(level).try_init();
}

// ── Version / Info ───────────────────────────────────────────────────────────

fn print_version() {
    println!("{} v{}", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION"));
    println!("  authors: {}", env!("CARGO_PKG_AUTHORS"));
    println!("  license: {}", env!("CARGO_PKG_LICENSE"));
    println!("  backends: native (Windows/Linux), ADB");
}

fn run_info(args: InfoArgs) -> Result<()> {
    if args.json {
        let value = info_to_json();
        println!("{}", serde_json::to_string_pretty(&value)?);
        return Ok(());
    }

    print_version();
    println!();
    println!("Backends:");
    println!(
        "  native           — {:?}",
        spectre_native::native_backend_kind()
    );
    println!(
        "  adb              — {}",
        if adb_available() {
            "available (adb on PATH)"
        } else {
            "missing (adb not on PATH)"
        }
    );
    println!();
    println!("Installed Games:");
    let games = list_installed_games();
    if games.is_empty() {
        println!("  (none found — place offset YAML files in games/<game>/offsets.yaml)");
    } else {
        for g in &games {
            println!("  - {g}");
        }
    }
    Ok(())
}

fn info_to_json() -> serde_json::Value {
    serde_json::json!({
        "name": env!("CARGO_PKG_NAME"),
        "version": env!("CARGO_PKG_VERSION"),
        "authors": env!("CARGO_PKG_AUTHORS"),
        "license": env!("CARGO_PKG_LICENSE"),
        "backends": {
            "native": format!("{:?}", spectre_native::native_backend_kind()),
            "adb": if adb_available() { "available" } else { "missing" },
        },
        "games": list_installed_games(),
    })
}

fn adb_available() -> bool {
    Command::new("adb")
        .arg("version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn list_installed_games() -> Vec<String> {
    let mut games = Vec::new();
    if let Ok(entries) = std::fs::read_dir("games") {
        for entry in entries.flatten() {
            let path = entry.path();
            let is_game = if path.is_dir() {
                path.join("offsets.yaml").is_file()
            } else {
                path.extension()
                    .map(|e| e == "yaml" || e == "yml")
                    .unwrap_or(false)
            };
            if is_game {
                games.push(entry.file_name().to_string_lossy().into_owned());
            }
        }
    }
    games.sort();
    games
}

// ── Shared Helpers ───────────────────────────────────────────────────────────

/// Create the backend reader: ADB (via spectre_adb::AdbReader) or native
/// (via spectre_native::create_default_reader).
///
/// TODO(spectre-adb/spectre-native): if `AdbReader::new` or
/// `create_default_reader` change their signatures once those crates are
/// fixed, only this function needs to be adapted.
fn create_reader(
    adb: bool,
    adb_host: Option<String>,
    adb_port: Option<u16>,
) -> Result<Box<dyn MemoryReader>> {
    if adb {
        let host = adb_host.unwrap_or_else(|| "localhost".to_owned());
        let port = adb_port.unwrap_or(5555);
        let reader = spectre_adb::AdbReader::new(&host, port);
        Ok(Box::new(reader))
    } else {
        let reader = spectre_native::create_default_reader();
        Ok(reader)
    }
}

fn resolve_pid(reader: &dyn MemoryReader, game: &str, hint: Option<u32>) -> Result<u32> {
    if let Some(pid) = hint {
        return Ok(pid);
    }
    let processes = reader
        .find_process(game)
        .with_context(|| format!("process lookup failed for '{game}'"))?;
    if processes.is_empty() {
        bail!("could not auto-detect process for '{game}'; specify --pid");
    }
    if processes.len() > 1 {
        warn!(
            "multiple processes match '{game}'; using first (pid {})",
            processes[0].pid
        );
    }
    info!(
        "auto-detected pid {} ({})",
        processes[0].pid, processes[0].name
    );
    Ok(processes[0].pid)
}

fn parse_u64(s: &str) -> Option<u64> {
    let t = s.trim();
    if let Some(hex) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
        u64::from_str_radix(hex, 16).ok()
    } else {
        t.parse::<u64>()
            .ok()
            .or_else(|| u64::from_str_radix(t, 16).ok())
    }
}

/// Strict integer parse for search values: decimal OR explicit 0x-hex only.
/// Unlike [`parse_u64`], this rejects bare "abc" (which would otherwise be
/// interpreted as hex 0xabc).
fn parse_strict_u64(s: &str) -> Option<u64> {
    let t = s.trim();
    if let Some(hex) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
        u64::from_str_radix(hex, 16).ok()
    } else {
        t.parse::<u64>().ok()
    }
}

fn write_output(text: &str, output_path: Option<&str>) -> Result<()> {
    match output_path {
        Some(path) => {
            std::fs::write(path, text).with_context(|| format!("cannot write '{path}'"))?;
            println!("results written to {path}");
        }
        None => println!("{text}"),
    }
    Ok(())
}

// ── Game Offsets Loading ─────────────────────────────────────────────────────

/// Resolve game offsets: explicit `--offsets` path first, then conventional
/// `games/<game>/offsets.yaml` / `games/<game>.yaml`, then the spectre-game
/// registry as a fallback.
fn load_game_offsets(game: &str, explicit: Option<&str>) -> Result<GameOffsets> {
    if let Some(path) = explicit {
        return parse_offsets_file(path, game);
    }

    let candidates = [
        format!("games/{game}/offsets.yaml"),
        format!("games/{game}.yaml"),
    ];
    for candidate in &candidates {
        if Path::new(candidate).is_file() {
            return parse_offsets_file(candidate, game);
        }
    }

    // TODO(spectre-game): keep in sync with the final spectre-game API
    // (GameRegistry::scan_dir / find_game as written by the game agent).
    let registry = spectre_game::GameRegistry::scan_dir("games");
    if let Some(entry) = registry.find_game(game).first() {
        return Ok(entry.offsets.clone());
    }

    bail!(
        "no offsets found for game '{game}' (looked for games/{game}/offsets.yaml, \
         games/{game}.yaml, and the games/ registry); use --offsets <path>"
    )
}

/// YAML mirrors of the spectre-game offset file format. Defined locally so the
/// CLI does not depend on spectre-game's (in-flux) serde types.
#[derive(serde::Deserialize)]
struct YamlGameFile {
    #[serde(default)]
    game: String,
    #[serde(default)]
    version: String,
    #[serde(default)]
    structures: Vec<YamlStructDef>,
}

#[derive(serde::Deserialize)]
struct YamlStructDef {
    name: String,
    #[serde(default, rename = "base_offset")]
    base_offset: u64,
    #[serde(default)]
    fields: Vec<YamlFieldDef>,
}

#[derive(serde::Deserialize)]
struct YamlFieldDef {
    name: String,
    #[serde(rename = "type")]
    field_type: String,
    #[serde(default)]
    offset: u64,
    #[serde(default)]
    desc: Option<String>,
    #[serde(default)]
    length: Option<u32>,
}

fn parse_field_type(raw: &str) -> Result<FieldType> {
    let s = raw.trim().to_lowercase();
    if let Some(len_str) = s.strip_prefix("string:") {
        let len = len_str
            .parse::<u32>()
            .with_context(|| format!("invalid string length in field type '{raw}'"))?;
        return Ok(FieldType::String(len));
    }
    match s.as_str() {
        "u8" => Ok(FieldType::U8),
        "u16" => Ok(FieldType::U16),
        "u32" => Ok(FieldType::U32),
        "u64" => Ok(FieldType::U64),
        "i8" => Ok(FieldType::I8),
        "i16" => Ok(FieldType::I16),
        "i32" => Ok(FieldType::I32),
        "i64" => Ok(FieldType::I64),
        "f32" => Ok(FieldType::F32),
        "f64" => Ok(FieldType::F64),
        "bool" => Ok(FieldType::Bool),
        "string" => Ok(FieldType::String(128)),
        "pointer32" | "ptr32" => Ok(FieldType::Pointer32),
        "pointer64" | "ptr64" | "pointer" => Ok(FieldType::Pointer64),
        other => bail!("unknown field type '{other}' in offsets YAML"),
    }
}

fn parse_offsets_file(path: &str, fallback_game: &str) -> Result<GameOffsets> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("cannot read offsets file '{path}'"))?;
    let yf: YamlGameFile =
        serde_yaml::from_str(&text).with_context(|| format!("invalid offsets YAML in '{path}'"))?;

    let mut structures = Vec::with_capacity(yf.structures.len());
    for ys in yf.structures {
        let mut fields = Vec::with_capacity(ys.fields.len());
        for yfd in ys.fields {
            let field_type = parse_field_type(&yfd.field_type)?;
            let field_type = match (field_type, yfd.length) {
                (FieldType::String(_), Some(n)) => FieldType::String(n),
                (ft, _) => ft,
            };
            fields.push(FieldDef {
                name: yfd.name,
                field_type,
                offset: yfd.offset,
                desc: yfd.desc,
            });
        }
        structures.push(StructDef {
            name: ys.name,
            base_offset: ys.base_offset,
            fields,
        });
    }

    Ok(GameOffsets {
        game: if yf.game.is_empty() {
            fallback_game.to_owned()
        } else {
            yf.game
        },
        version: yf.version,
        structures,
    })
}

// ── Scan Implementation ──────────────────────────────────────────────────────

fn field_type_to_value_type(ft: FieldType) -> ValueType {
    match ft {
        FieldType::U8 => ValueType::U8,
        FieldType::U16 => ValueType::U16,
        FieldType::U32 => ValueType::U32,
        FieldType::U64 => ValueType::U64,
        FieldType::I8 => ValueType::I8,
        FieldType::I16 => ValueType::I16,
        FieldType::I32 => ValueType::I32,
        FieldType::I64 => ValueType::I64,
        FieldType::F32 => ValueType::F32,
        FieldType::F64 => ValueType::F64,
        FieldType::Bool => ValueType::U8,
        FieldType::String(n) => ValueType::Bytes(n),
        FieldType::Pointer32 => ValueType::U32,
        FieldType::Pointer64 => ValueType::U64,
    }
}

fn build_scan_patterns(offsets: &GameOffsets) -> Vec<ScanPattern> {
    // Translate the declarative structure layout (base_offset + per-field
    // offsets) into a scanner pattern. Fields are NOT packed sequentially:
    // gaps between field offsets are emitted as anonymous `Bytes` fields, so
    // the scanner validates the exact structure geometry. This cuts false
    // positives massively compared to layout-only matching.
    offsets
        .structures
        .iter()
        .map(|sd| {
            // Sort fields by declared offset (offset files may not be ordered).
            let mut fields: Vec<&FieldDef> = sd.fields.iter().collect();
            fields.sort_by_key(|f| f.offset);

            // Field offsets are RELATIVE to the structure base; the scanner
            // matches at any address X and validates geometry at X+offset.
            // Starting at base_offset (= the *expected* absolute address)
            // would inject a multi-gigabyte filler gap for real games.
            let mut pattern_fields: Vec<PatternField> = Vec::new();
            let mut cursor: u64 = 0;

            for fd in fields {
                // Leading gap before this field.
                if fd.offset > cursor {
                    pattern_fields.push(gap_field(fd.offset - cursor));
                }
                // The field itself. Naming is kept on the real field so scan
                // reports carry meaningful names; pointer fields are left
                // unconstrained since their value is process-dependent.
                pattern_fields.push(PatternField {
                    name: fd.name.clone(),
                    value_type: field_type_to_value_type(fd.field_type),
                    value: ScanValue::Any,
                    alignment: 1, // scanner runs aligned by ScanConfig stride anyway
                });
                cursor = fd.offset + field_type_to_value_type(fd.field_type).size() as u64;
            }

            ScanPattern { name: sd.name.clone(), fields: pattern_fields }
        })
        .collect()
}

/// Build an anonymous fixed-size filler field for a gap between offsets.
fn gap_field(size: u64) -> PatternField {
    PatternField {
        name: "gap".to_owned(),
        value_type: ValueType::Bytes(size as u32),
        value: ScanValue::Any,
        alignment: 1,
    }
}

fn run_scan(args: ScanArgs) -> Result<()> {
    // Offline mode: scan a dump file instead of a live process.
    if let Some(dump_path) = args.dump.as_deref() {
        let base = parse_u64(&args.dump_base).ok_or_else(|| {
            anyhow!("invalid dump base '{}' (use 0x-prefixed hex or decimal)", args.dump_base)
        })?;
        let reader = spectre_core::DumpFileReader::from_file(
            Path::new(dump_path),
            base,
            format!("{}-dump", args.game),
        )
        .with_context(|| format!("failed to load dump '{}'", dump_path))?;
        info!(
            "scanning dump '{}' ({} bytes @ {base:#x})",
            dump_path,
            reader.len()
        );

        let offsets = load_game_offsets(&args.game, args.offsets.as_deref())?;
        let patterns = build_scan_patterns(&offsets);
        info!(
            "loaded {} structure(s) for '{}' v{}",
            offsets.structures.len(),
            offsets.game,
            offsets.version
        );
        let reports = scan_memory(&reader, 0, patterns, &ScanConfig::default())?;
        let total: usize = reports.iter().map(|r| r.matches.len()).sum();
        info!("scan complete: {} pattern(s), {total} total match(es)", reports.len());
        return output_scan_reports(&reports, args.format.as_deref(), args.output.as_deref());
    }

    let reader = create_reader(args.adb, args.adb_host, args.adb_port)?;
    let pid = resolve_pid(reader.as_ref(), &args.game, args.pid)?;
    info!("scanning game '{}' (pid {pid})", args.game);

    let offsets = load_game_offsets(&args.game, args.offsets.as_deref())?;
    let patterns = build_scan_patterns(&offsets);
    info!(
        "loaded {} structure(s) for '{}' v{}",
        offsets.structures.len(),
        offsets.game,
        offsets.version
    );

    debug!(
        "scanning {} pattern(s) across process memory",
        patterns.len()
    );
    let reports = scan_memory(reader.as_ref(), pid, patterns, &ScanConfig::default())?;

    let total: usize = reports.iter().map(|r| r.matches.len()).sum();
    info!(
        "scan complete: {} pattern(s), {total} total match(es)",
        reports.len()
    );

    output_scan_reports(&reports, args.format.as_deref(), args.output.as_deref())
}

fn output_scan_reports(
    reports: &[ScanReport],
    format: Option<&str>,
    output_path: Option<&str>,
) -> Result<()> {
    let fmt = format.unwrap_or("table").to_lowercase();
    let text = match fmt.as_str() {
        "table" => render_scan_table(reports),
        "json" => serde_json::to_string_pretty(&scan_reports_to_json(reports))?,
        "yaml" | "yml" => serde_yaml::to_string(&scan_reports_to_json(reports))?,
        other => bail!("unknown format '{other}' (expected table, json, or yaml)"),
    };
    write_output(&text, output_path)
}

fn render_scan_table(reports: &[ScanReport]) -> String {
    let mut lines: Vec<String> = Vec::new();
    for report in reports {
        lines.push(format!("\nPattern: {}", report.pattern_name));
        lines.push(format!("Matches: {}", report.matches.len()));
        lines.push("-".repeat(80));
        for m in &report.matches {
            lines.push(format!("  Address: {:#x}", m.address));
            for (offset, name, bytes) in &m.fields {
                lines.push(format!(
                    "    [{offset:#06x}] {name:<20} = {}",
                    hex_bytes(bytes)
                ));
            }
        }
    }
    lines.join("\n")
}

fn scan_reports_to_json(reports: &[ScanReport]) -> serde_json::Value {
    serde_json::json!({
        "patterns": reports.iter().map(|r| {
            serde_json::json!({
                "pattern": r.pattern_name,
                "match_count": r.matches.len(),
                "matches": r.matches.iter().map(|m| {
                    serde_json::json!({
                        "address": format!("{:#x}", m.address),
                        "field_count": m.fields.len(),
                        "fields": m.fields.iter().map(|(off, name, bytes)| {
                            serde_json::json!({
                                "offset": off,
                                "name": name,
                                "hex": hex_bytes(bytes),
                            })
                        }).collect::<Vec<_>>(),
                    })
                }).collect::<Vec<_>>(),
            })
        }).collect::<Vec<_>>(),
    })
}

// ── Dump Implementation ──────────────────────────────────────────────────────

fn run_dump(args: DumpArgs) -> Result<()> {
    let address = parse_u64(&args.address).ok_or_else(|| {
        anyhow!(
            "invalid address '{}' (use 0x-prefixed hex or decimal)",
            args.address
        )
    })?;
    debug!(
        "dumping {} bytes from pid {} at {address:#x}",
        args.size, args.pid
    );

    let reader = create_reader(args.adb, None, None)?;
    let data = reader
        .read_bytes(args.pid, address, args.size)
        .with_context(|| {
            format!(
                "failed to read {} bytes from pid {} at {address:#x}",
                args.size, args.pid
            )
        })?;

    let fmt = args.format.as_deref().unwrap_or("hex").to_lowercase();
    match fmt.as_str() {
        "raw" => {
            if let Some(path) = &args.output {
                std::fs::write(path, &data).with_context(|| format!("cannot write '{path}'"))?;
                println!("wrote {} bytes to {path}", data.len());
            } else {
                use std::io::Write;
                std::io::stdout()
                    .write_all(&data)
                    .context("failed to write raw bytes to stdout")?;
            }
        }
        "ascii" => write_output(&render_ascii(&data), args.output.as_deref())?,
        "hex" => write_output(&render_hex_dump(&data, address), args.output.as_deref())?,
        other => bail!("unknown dump format '{other}' (expected hex, raw, or ascii)"),
    }
    Ok(())
}

fn render_hex_dump(data: &[u8], base: u64) -> String {
    let mut lines = Vec::new();
    for (i, chunk) in data.chunks(16).enumerate() {
        let addr = base + (i as u64) * 16;
        let ascii: String = chunk
            .iter()
            .map(|b| {
                if b.is_ascii_graphic() || *b == b' ' {
                    *b as char
                } else {
                    '.'
                }
            })
            .collect();
        lines.push(format!("{addr:016x}  {:<48}  {ascii}", hex_bytes(chunk)));
    }
    lines.join("\n")
}

/// Format bytes as space-separated lowercase hex pairs ("de ad be ef").
fn hex_bytes(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

/// Like [`hex_bytes`], but shows at most `max` bytes followed by
/// "…(N bytes)" with the total length. Empty input renders as "-".
fn hex_preview(bytes: &[u8], max: usize) -> String {
    if bytes.is_empty() {
        "-".to_owned()
    } else if bytes.len() > max {
        format!("{} …({} bytes)", hex_bytes(&bytes[..max]), bytes.len())
    } else {
        hex_bytes(bytes)
    }
}

fn render_ascii(data: &[u8]) -> String {
    data.iter()
        .map(|b| {
            if *b >= 0x20 && *b <= 0x7e {
                *b as char
            } else {
                '.'
            }
        })
        .collect()
}

// ── DumpDiff Implementation ──────────────────────────────────────────────────

/// Max bytes of hex shown per side in table output (JSON is never truncated).
const DUMPDIFF_TABLE_HEX_MAX: usize = 32;

fn run_dumpdiff(args: DumpDiffArgs) -> Result<()> {
    let base = parse_u64(&args.base).ok_or_else(|| {
        anyhow!(
            "invalid base '{}' (use 0x-prefixed hex or decimal)",
            args.base
        )
    })?;
    let old = std::fs::read(&args.old).with_context(|| format!("cannot read '{}'", args.old))?;
    let new = std::fs::read(&args.new).with_context(|| format!("cannot read '{}'", args.new))?;
    let longest = old.len().max(new.len()) as u64;
    if base.checked_add(longest).is_none() {
        bail!("base {base:#x} + dump length {longest} overflows the 64-bit address space");
    }

    let diff = spectre_core::diff_dumps(&old, &new);
    info!(
        "dumpdiff: {} region(s), {} changed byte(s)",
        diff.changed_count(),
        diff.changed_bytes()
    );

    let text = if args.json {
        serde_json::to_string_pretty(&dumpdiff_to_json(
            &diff,
            base,
            (&args.old, old.len()),
            (&args.new, new.len()),
        ))?
    } else {
        render_dumpdiff_table(&diff, base, old.len(), new.len())
    };
    println!("{text}");
    Ok(())
}

fn render_dumpdiff_table(
    diff: &spectre_core::DumpDiff,
    base: u64,
    old_len: usize,
    new_len: usize,
) -> String {
    let mut lines = vec![format!(
        "{} changed region(s), {} changed byte(s)  (old: {old_len} bytes, new: {new_len} bytes)",
        diff.changed_count(),
        diff.changed_bytes()
    )];
    for r in diff.regions() {
        lines.push(format!(
            "0x{:X}  old: {}  new: {}",
            base + r.offset as u64,
            hex_preview(&r.old_bytes, DUMPDIFF_TABLE_HEX_MAX),
            hex_preview(&r.new_bytes, DUMPDIFF_TABLE_HEX_MAX)
        ));
    }
    lines.join("\n")
}

fn dumpdiff_to_json(
    diff: &spectre_core::DumpDiff,
    base: u64,
    (old_path, old_len): (&str, usize),
    (new_path, new_len): (&str, usize),
) -> serde_json::Value {
    serde_json::json!({
        "old": { "path": old_path, "len": old_len },
        "new": { "path": new_path, "len": new_len },
        "base": format!("{base:#x}"),
        "region_count": diff.changed_count(),
        "changed_bytes": diff.changed_bytes(),
        "regions": diff.regions().iter().map(|r| {
            serde_json::json!({
                "offset": r.offset,
                "address": format!("{:#x}", base + r.offset as u64),
                "len": r.len(),
                "changed_bytes": r.changed_bytes(),
                "old": hex_bytes(&r.old_bytes),
                "new": hex_bytes(&r.new_bytes),
            })
        }).collect::<Vec<_>>(),
    })
}

// ── Find Implementation ──────────────────────────────────────────────────────

fn run_find(args: FindArgs) -> Result<()> {
    let reader = create_reader(args.adb, None, None)?;
    let processes = reader
        .find_process(&args.name)
        .with_context(|| format!("process lookup failed for '{}'", args.name))?;

    if processes.is_empty() {
        println!("no processes found matching '{}'", args.name);
        return Ok(());
    }

    if args.json {
        let value = serde_json::json!(
            processes
                .iter()
                .map(|p| serde_json::json!({"pid": p.pid, "name": p.name}))
                .collect::<Vec<_>>()
        );
        println!("{}", serde_json::to_string_pretty(&value)?);
    } else {
        println!("{:<8}  NAME", "PID");
        for p in &processes {
            println!("{:<8}  {}", p.pid, p.name);
        }
        println!("found {} process(es)", processes.len());
    }
    Ok(())
}

// ── Regions Implementation ───────────────────────────────────────────────────

fn run_regions(args: RegionsArgs) -> Result<()> {
    let reader = create_reader(args.adb, None, None)?;
    let regions = reader
        .memory_regions(args.pid)
        .with_context(|| format!("failed to list memory regions for pid {}", args.pid))?;

    let filtered: Vec<&MemoryRegion> = match args.filter.as_deref() {
        Some(f) => {
            let needle = f.to_lowercase();
            regions
                .iter()
                .filter(|r| r.perms.to_lowercase().contains(&needle))
                .collect()
        }
        None => regions.iter().collect(),
    };

    if filtered.is_empty() {
        println!("no memory regions found");
        return Ok(());
    }

    if args.json {
        let value = serde_json::json!(
            filtered
                .iter()
                .map(|r| serde_json::json!({
                    "start": format!("{:#x}", r.start),
                    "end": format!("{:#x}", r.end),
                    "size": r.size(),
                    "perms": r.perms,
                    "path": r.path,
                }))
                .collect::<Vec<_>>()
        );
        println!("{}", serde_json::to_string_pretty(&value)?);
    } else {
        println!("{:<16} {:<16} {:<6}  PATH", "START", "END", "PERMS");
        for r in &filtered {
            let path = r.path.as_deref().unwrap_or("-");
            println!("{:016x} {:016x} {:<6}  {}", r.start, r.end, r.perms, path);
        }
        println!("showing {} region(s)", filtered.len());
    }
    Ok(())
}

// ── Adb Implementation ───────────────────────────────────────────────────────

fn run_adb(args: AdbArgs) -> Result<()> {
    match args.sub {
        AdbSubCommand::List => adb_list_devices(),
        AdbSubCommand::Ping(cmd) => adb_ping_device(cmd.serial),
    }
}

fn adb_list_devices() -> Result<()> {
    let output = Command::new("adb")
        .args(["devices", "-l"])
        .output()
        .context("failed to run 'adb devices' — is adb on PATH?")?;
    if !output.status.success() {
        bail!(
            "adb devices failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    // Lines: <serial> <state> [usb:...] [product:...] [model:...] [device:...]
    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut devices: Vec<(String, String, String)> = Vec::new(); // serial, state, model
    for line in stdout.lines().skip(1) {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let mut fields = line.split_whitespace();
        let serial = fields.next().unwrap_or("").to_owned();
        let state = fields.next().unwrap_or("").to_owned();
        let model = fields
            .filter_map(|f| f.strip_prefix("model:"))
            .next()
            .unwrap_or("")
            .to_owned();
        if !serial.is_empty() {
            devices.push((serial, state, model));
        }
    }

    if devices.is_empty() {
        println!("no ADB devices found");
        println!("ensure the ADB daemon is running and devices are connected");
        return Ok(());
    }

    println!("{:<24}  {:<12}  MODEL", "DEVICE", "STATE");
    for (serial, state, model) in &devices {
        let model = if model.is_empty() { "-" } else { model };
        println!("{serial:<24}  {state:<12}  {model}");
    }
    println!("found {} device(s)", devices.len());
    Ok(())
}

fn adb_ping_device(serial: Option<String>) -> Result<()> {
    let start = Instant::now();
    let mut cmd = Command::new("adb");
    if let Some(s) = &serial {
        cmd.arg("-s").arg(s);
    }
    cmd.arg("get-state");
    let output = cmd
        .output()
        .context("failed to run 'adb get-state' — is adb on PATH?")?;
    let elapsed = start.elapsed();
    if !output.status.success() {
        bail!(
            "adb get-state failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let state = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    let target = serial.clone().unwrap_or_else(|| "default".to_owned());
    println!("ADB ping {target}:");
    println!("  state:   {state}");
    println!("  latency: {} ms", elapsed.as_millis());
    println!(
        "  result:  {}",
        if state == "device" {
            "OK"
        } else {
            "UNKNOWN/OFFLINE"
        }
    );
    Ok(())
}

// ── Bot Implementation ───────────────────────────────────────────────────────

/// Memory-field resolver for the bot engine: resolves a field name to an
/// absolute address + byte size using the game offsets YAML (if configured).
struct CliActionContext {
    reader: Box<dyn MemoryReader>,
    pid: u32,
    fields: HashMap<String, (u64, u32)>,
}

impl spectre_bot::ActionContext for CliActionContext {
    fn resolve_field(&self, field_name: &str) -> Result<Vec<u8>> {
        let (addr, size) = self.fields.get(field_name).ok_or_else(|| {
            anyhow!("unknown field '{field_name}' (no game offsets loaded for the bot?)")
        })?;
        self.reader.read_bytes(self.pid, *addr, *size)
    }
}

/// Input simulator for bot actions.
///
/// TODO(bot-input): only the `adb` backend is implemented (via `adb shell
/// input`). Native Windows/Linux input simulation is not wired yet; those
/// backends fail at runtime with a clear error.
struct CliInputSimulator {
    backend: String,
}

impl CliInputSimulator {
    fn new(backend: String) -> Self {
        Self { backend }
    }

    fn run_input(&self, args: &[&str]) -> Result<()> {
        if self.backend != "adb" {
            bail!(
                "input backend '{}' is not implemented yet (only 'adb' is supported)",
                self.backend
            );
        }
        let status = Command::new("adb")
            .arg("shell")
            .arg("input")
            .args(args)
            .status()
            .context("failed to run 'adb shell input'")?;
        if !status.success() {
            bail!("adb shell input failed (exit {status})");
        }
        Ok(())
    }
}

impl spectre_bot::InputSimulator for CliInputSimulator {
    fn click(&self, x: u32, y: u32) -> Result<()> {
        // Touch backends have no distinct mouse buttons — treat click as tap.
        self.run_input(&["tap", &x.to_string(), &y.to_string()])
    }

    fn tap_hold(&self, x: u32, y: u32, millis: u64) -> Result<()> {
        self.run_input(&[
            "swipe",
            &x.to_string(),
            &y.to_string(),
            &x.to_string(),
            &y.to_string(),
            &millis.to_string(),
        ])
    }

    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, millis: u64) -> Result<()> {
        self.run_input(&[
            "swipe",
            &x1.to_string(),
            &y1.to_string(),
            &x2.to_string(),
            &y2.to_string(),
            &millis.to_string(),
        ])
    }

    fn scroll(&self, delta: i32) -> Result<()> {
        let keycode = if delta >= 0 { "KEYCODE_PAGE_UP" } else { "KEYCODE_PAGE_DOWN" };
        self.run_input(&["keyevent", keycode])
    }

    fn key(&self, key: &str) -> Result<()> {
        let keycode = format!("KEYCODE_{}", key.to_uppercase());
        self.run_input(&["keyevent", &keycode])
    }
}

fn run_bot(args: BotArgs) -> Result<()> {
    let config = spectre_bot::BotConfig::from_yaml_file(&args.config)
        .with_context(|| format!("failed to load bot config '{}'", args.config))?;
    let instance = args.name.clone().unwrap_or_else(|| "default".to_owned());
    let enabled: usize = config.tasks.iter().filter(|t| t.enabled).count();
    info!(
        "loaded bot config '{}': {} task(s), {enabled} enabled, backend '{}'",
        args.config,
        config.tasks.len(),
        config.input_backend
    );

    if args.dry_run {
        print_bot_summary(&config, &instance);
        return Ok(());
    }

    let (ctx, input, hooks) = build_bot_runtime(&config)?;
    let engine_reader: Box<dyn MemoryReader> = create_reader(false, None, None)?;
    let engine = spectre_bot::BotEngine::new(engine_reader, Box::new(input), Box::new(ctx), hooks);

    if args.once {
        println!("running bot '{instance}' once...");
        run_bot_tasks(&config, &engine)?;
        println!("bot finished");
    } else {
        println!(
            "running bot '{instance}' every {} ms — press Ctrl-C to stop",
            config.default_interval_ms
        );
        loop {
            run_bot_tasks(&config, &engine)?;
            std::thread::sleep(Duration::from_millis(config.default_interval_ms as u64));
        }
    }
    Ok(())
}

fn print_bot_summary(config: &spectre_bot::BotConfig, instance: &str) {
    println!("config validated successfully:");
    println!("  instance:         {instance}");
    println!("  input backend:    {}", config.input_backend);
    println!("  default interval: {} ms", config.default_interval_ms);
    println!("  memory poll:      {} ms", config.memory_poll_ms);
    println!("  enabled:          {}", config.enabled);
    println!("  tasks:            {}", config.tasks.len());
    for t in &config.tasks {
        println!(
            "    - {} (interval={} ms, enabled={}, actions={})",
            t.name,
            t.interval_ms,
            t.enabled,
            t.actions.len()
        );
    }
}

fn run_bot_tasks(config: &spectre_bot::BotConfig, engine: &spectre_bot::BotEngine) -> Result<()> {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .context("failed to create tokio runtime")?;
    for task in &config.tasks {
        if !task.enabled {
            continue;
        }
        let results = rt.block_on(engine.execute_actions(&task.actions));
        for result in results {
            match result {
                spectre_bot::ActionResult::Ok => {}
                spectre_bot::ActionResult::Warning(w) => {
                    println!("task '{}': warning: {w}", task.name)
                }
                spectre_bot::ActionResult::Error(e) => {
                    eprintln!("task '{}': error: {e}", task.name)
                }
                spectre_bot::ActionResult::Stop => {
                    println!("task '{}': stopped", task.name);
                    break;
                }
            }
        }
    }
    Ok(())
}

/// Build the bot engine components (context, input simulator, hooks).
///
/// The target pid comes from `metadata.pid` (numeric) or `metadata.process`
/// (process-name lookup); field addresses come from `metadata.offsets` (a game
/// offsets YAML) resolved as `base_offset + field.offset` absolute addresses.
fn build_bot_runtime(
    config: &spectre_bot::BotConfig,
) -> Result<(
    CliActionContext,
    CliInputSimulator,
    spectre_bot::HookRegistry,
)> {
    let meta = config.metadata.as_ref();
    let pid = match meta
        .and_then(|m| m.get("pid"))
        .and_then(|s| s.parse::<u32>().ok())
    {
        Some(pid) => pid,
        None => {
            let proc_name = meta
                .and_then(|m| m.get("process"))
                .map(|s| s.as_str())
                .unwrap_or("game");
            let reader = create_reader(false, None, None)?;
            let processes = reader.find_process(proc_name)?;
            match processes.first() {
                Some(p) => p.pid,
                None => bail!(
                    "cannot resolve bot target pid: set metadata.pid or metadata.process in the bot config"
                ),
            }
        }
    };

    let reader = create_reader(false, None, None)?;
    let fields = load_bot_fields(meta)?;
    let input = CliInputSimulator::new(config.input_backend.clone());
    Ok((
        CliActionContext {
            reader,
            pid,
            fields,
        },
        input,
        spectre_bot::HookRegistry::new(),
    ))
}

fn load_bot_fields(meta: Option<&HashMap<String, String>>) -> Result<HashMap<String, (u64, u32)>> {
    // TODO(bot-fields): richer resolution (struct base pointers, per-struct
    // selection) once the bot engine API stabilizes. For now every field is
    // resolved as an absolute `base_offset + field.offset` address, which is
    // correct for offset files that use absolute bases.
    let mut fields = HashMap::new();
    let Some(offsets_path) = meta.and_then(|m| m.get("offsets")).cloned() else {
        return Ok(fields);
    };
    let game = meta
        .and_then(|m| m.get("game"))
        .map(|s| s.as_str())
        .unwrap_or("bot");
    let offsets = parse_offsets_file(&offsets_path, game)?;
    for sd in &offsets.structures {
        for fd in &sd.fields {
            let addr = sd.base_offset + fd.offset;
            let size = field_type_to_value_type(fd.field_type).size();
            fields.entry(fd.name.clone()).or_insert((addr, size));
        }
    }
    Ok(fields)
}

// ── Lua Script Execution ─────────────────────────────────────────────────────

/// Adapts `CliInputSimulator` to the Lua `BotApi` trait.
struct LuaBotApi {
    input: CliInputSimulator,
}

impl spectre_lua::BotApi for LuaBotApi {
    fn click(&self, x: u32, y: u32) -> anyhow::Result<bool> {
        self.input.run_input(&["tap", &x.to_string(), &y.to_string()])?;
        Ok(true)
    }

    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, duration_ms: u32) -> anyhow::Result<bool> {
        self.input.run_input(&[
            "swipe",
            &x1.to_string(),
            &y1.to_string(),
            &x2.to_string(),
            &y2.to_string(),
            &duration_ms.to_string(),
        ])?;
        Ok(true)
    }

    fn wait(&self, ms: u32) -> anyhow::Result<()> {
        std::thread::sleep(Duration::from_millis(ms as u64));
        Ok(())
    }

    fn log(&self, message: &str) -> anyhow::Result<()> {
        println!("[lua] {message}");
        Ok(())
    }
}

/// Execute a Lua bot script through the spectre-lua sandbox.
fn run_script(args: ScriptArgs) -> Result<()> {
    let backend = args.input_backend.unwrap_or_else(|| "adb".to_owned());
    let input = CliInputSimulator::new(backend);
    let bot = LuaBotApi { input };
    let reader: Box<dyn MemoryReader + Send + 'static> = create_reader(false, None, None)?;

    let sandbox = spectre_lua::LuaSandbox::create(reader, Box::new(bot))
        .context("failed to create Lua sandbox")?;
    sandbox
        .run_file(&args.script)
        .with_context(|| format!("failed to execute Lua script '{}'", args.script))?;
    Ok(())
}

// ── Value Search (Cheat-Engine style) ────────────────────────────────────────

/// Deserialized value type + bytes for a search request.
struct SearchValue {
    value_type: ValueType,
    /// Raw little-endian bytes of the target value.
    bytes: Vec<u8>,
    /// Human-readable type name for output.
    type_name: String,
}

/// Parse `type` + `value` (decimal, 0x-hex, or float) into a concrete value.
fn parse_search_value(type_name: &str, value_str: &str) -> Result<SearchValue> {
    let vt = match type_name.to_lowercase().as_str() {
        "u8" => ValueType::U8,
        "u16" => ValueType::U16,
        "u32" => ValueType::U32,
        "u64" => ValueType::U64,
        "i8" => ValueType::I8,
        "i16" => ValueType::I16,
        "i32" => ValueType::I32,
        "i64" => ValueType::I64,
        "f32" => ValueType::F32,
        "f64" => ValueType::F64,
        _ => bail!("unknown value type '{type_name}' (use u8..u64, i8..i64, f32, f64)"),
    };

    let bytes = match vt {
        ValueType::U8 | ValueType::I8 => {
            let n = parse_strict_u64(value_str).ok_or_else(|| anyhow!("invalid u8 value '{value_str}'"))?;
            vec![n as u8]
        }
        ValueType::U16 | ValueType::I16 => {
            let n = parse_strict_u64(value_str).ok_or_else(|| anyhow!("invalid u16 value '{value_str}'"))?;
            (n as u16).to_le_bytes().to_vec()
        }
        ValueType::U32 | ValueType::I32 => {
            let n = parse_strict_u64(value_str).ok_or_else(|| anyhow!("invalid u32 value '{value_str}'"))?;
            (n as u32).to_le_bytes().to_vec()
        }
        ValueType::U64 | ValueType::I64 => {
            let n = parse_strict_u64(value_str).ok_or_else(|| anyhow!("invalid u64 value '{value_str}'"))?;
            n.to_le_bytes().to_vec()
        }
        ValueType::F32 => {
            let f: f32 = value_str
                .parse()
                .map_err(|_| anyhow!("invalid f32 value '{value_str}'"))?;
            f.to_le_bytes().to_vec()
        }
        ValueType::F64 => {
            let f: f64 = value_str
                .parse()
                .map_err(|_| anyhow!("invalid f64 value '{value_str}'"))?;
            f.to_le_bytes().to_vec()
        }
        ValueType::Bytes(_) => bail!("byte arrays are not supported in search"),
    };

    Ok(SearchValue { value_type: vt, bytes, type_name: type_name.to_lowercase() })
}

fn search_state_path(explicit: &Option<String>) -> String {
    explicit.clone().unwrap_or_else(|| ".spectre-search.json".to_owned())
}

/// Load previously found addresses.
fn load_search_state(path: &str) -> Result<Vec<u64>> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("cannot read search state '{}' (run search without --continue first)", path))?;
    let addrs: Vec<String> = serde_json::from_str(&text)
        .with_context(|| format!("invalid search state in '{}'", path))?;
    Ok(addrs
        .iter()
        .filter_map(|s| parse_u64(s))
        .collect())
}

/// Persist addresses for the next refinement step.
fn save_search_state(path: &str, addrs: &[u64]) -> Result<()> {
    let hex: Vec<String> = addrs.iter().map(|a| format!("{a:#x}")).collect();
    let json = serde_json::to_string_pretty(&hex)
        .context("failed to serialize search state")?;
    std::fs::write(path, json).with_context(|| format!("cannot write '{}'", path))?;
    Ok(())
}

/// Format one memory address for table output.
fn fmt_addr(a: u64) -> String {
    format!("{a:#014x}")
}

/// Core search: find addresses where the given value type equals `bytes`.
fn search_matches(reader: &dyn MemoryReader, pid: u32, sv: &SearchValue, limit: u32) -> Result<Vec<u64>> {
    // Build a one-field pattern: exact little-endian bytes, checked at a
    // fixed stride via the scanner's alignment (natural size alignment).
    let align = sv.value_type.size().max(1);
    let pattern = ScanPattern {
        name: "search".to_owned(),
        fields: vec![PatternField {
            name: "value".to_owned(),
            value_type: sv.value_type,
            value: ScanValue::Exact(sv.bytes.clone()),
            alignment: align,
        }],
    };
    let mut config = ScanConfig { alignment: align, little_endian: true, ..Default::default() };
        if limit > 0 {
            config.max_matches_per_pattern = limit;
        }
    let reports = scan_memory(reader, pid, vec![pattern], &config)?;
    Ok(reports
        .into_iter()
        .flat_map(|r| r.matches.into_iter().map(|m| m.address))
        .collect())
}

fn run_search(args: SearchArgs) -> Result<()> {
    let sv = parse_search_value(&args.value_type, &args.value)?;
    let state_path = search_state_path(&args.state);

    if args.continue_search {
        // Refine: only re-check previously found addresses.
        let prev = load_search_state(&state_path)?;
        info!("refining {} candidate(s)...", prev.len());
        if prev.is_empty() {
            println!("no previous results to refine");
            return Ok(());
        }
        let reader = create_reader(args.adb, None, None)?;
        if args.pid.is_none() {
            bail!("--continue requires --pid to re-read the target process");
        }
        let pid = args.pid.unwrap();
        let mut kept: Vec<u64> = Vec::new();
        for addr in &prev {
            let is_match = reader
                .read_bytes(pid, *addr, sv.value_type.size())
                .map(|b| b == sv.bytes)
                .unwrap_or(false);
            if is_match {
                kept.push(*addr);
                if args.limit > 0 && kept.len() >= args.limit as usize {
                    break;
                }
            }
        }
        save_search_state(&state_path, &kept)?;
        for a in &kept {
            println!("{}", fmt_addr(*a));
        }
        println!("-- {} result(s), saved to {state_path}", kept.len());
        return Ok(());
    }

    // New search over all readable memory.
    let pid = args.pid.ok_or_else(|| anyhow!("pid is required (or use --continue)"))?;
    let reader = create_reader(args.adb, None, None)?;
    info!(
        "searching pid {pid} for {} = {}...",
        sv.type_name,
        args.value
    );
    let found = search_matches(reader.as_ref(), pid, &sv, args.limit)?;
    save_search_state(&state_path, &found)?;

    for a in found.iter().take(if args.limit > 0 { args.limit as usize } else { usize::MAX }) {
        println!("{}", fmt_addr(*a));
    }
    println!("-- {} result(s), saved to {state_path}", found.len());
    Ok(())
}


#[cfg(test)]
mod tests {
    use super::*;

    fn offsets() -> GameOffsets {
        GameOffsets {
            game: "test".to_owned(),
            version: "1.0".to_owned(),
            structures: vec![StructDef {
                name: "Player".to_owned(),
                base_offset: 0x1000,
                fields: vec![
                    FieldDef { name: "level".to_owned(), field_type: FieldType::U32, offset: 0x00, desc: None },
                    FieldDef { name: "gold".to_owned(), field_type: FieldType::U64, offset: 0x10, desc: None },
                    FieldDef { name: "hp".to_owned(), field_type: FieldType::F32, offset: 0x18, desc: None },
                ],
            }],
        }
    }

    #[test]
    fn patterns_include_geometry_gaps() {
        let patterns = build_scan_patterns(&offsets());
        assert_eq!(patterns.len(), 1);
        let p = &patterns[0];
        // level(4) + gap(0x10-4=12) + gold(8) + gap(0x18-0x18=0) + hp(4)
        let expected_span: u64 = 28;
        // Sum individual value sizes; PatternField alignment is 1 so span
        // equals the sum.
        assert_eq!(p.span(), expected_span, "span must cover all real fields plus gaps");
        // Fields: level, gap, gold, hp (gap between level and gold only).
        let names: Vec<&str> = p.fields.iter().map(|f| f.name.as_str()).collect();
        assert_eq!(names, vec!["level", "gap", "gold", "hp"]);
        // The gap must be 12 bytes (0x10 - 4).
        assert!(matches!(p.fields[1].value_type, ValueType::Bytes(12)));
    }

    #[test]
    fn span_respects_unsorted_field_offsets() {
        // Sorted internally even if the YAML lists fields out of order.
        let mut go = offsets();
        go.structures[0].fields.swap(0, 2); // hp first, level last
        let p = &build_scan_patterns(&go)[0];
        let names: Vec<&str> = p.fields.iter().map(|f| f.name.as_str()).collect();
        assert_eq!(names[0], "level", "fields must be sorted by offset");
    }

    #[test]
    fn empty_offsets_yield_empty_patterns() {
        let go = GameOffsets { game: "x".into(), version: "1".into(), structures: vec![] };
        assert!(build_scan_patterns(&go).is_empty());
    }

    #[test]
    fn search_value_parses_numeric_types() {
        let v = parse_search_value("u32", "42").unwrap();
        assert_eq!(v.bytes, 42u32.to_le_bytes().to_vec());
        assert_eq!(v.value_type.size(), 4);

        let v16 = parse_search_value("u16", "0x10").unwrap();
        assert_eq!(v16.bytes, 16u16.to_le_bytes().to_vec());

        let v64 = parse_search_value("i64", "1234567890").unwrap();
        assert_eq!(v64.bytes, 1234567890i64.to_le_bytes().to_vec());

        let f = parse_search_value("f32", "9999.5").unwrap();
        assert_eq!(f.bytes, 9999.5f32.to_le_bytes().to_vec());
    }

    #[test]
    fn search_value_rejects_bad_input() {
        assert!(parse_search_value("u32", "abc").is_err());
        assert!(parse_search_value("f32", "not-a-float").is_err());
        assert!(parse_search_value("strange", "1").is_err());
    }

    #[test]
    fn hex_bytes_formats_space_separated_pairs() {
        assert_eq!(hex_bytes(&[]), "");
        assert_eq!(hex_bytes(&[0x00]), "00");
        assert_eq!(hex_bytes(&[0xde, 0xad, 0xbe, 0xef]), "de ad be ef");
    }

    #[test]
    fn hex_preview_truncates_long_input() {
        assert_eq!(hex_preview(&[], 4), "-");
        assert_eq!(hex_preview(&[1, 2, 3, 4], 4), "01 02 03 04");
        assert_eq!(hex_preview(&[1, 2, 3, 4, 5], 4), "01 02 03 04 …(5 bytes)");
    }

    #[test]
    fn dumpdiff_table_adds_base_to_offsets() {
        let old = vec![0u8; 64];
        let mut new = old.clone();
        new[0x10] = 0xAB;
        let diff = spectre_core::diff_dumps(&old, &new);
        let text = render_dumpdiff_table(&diff, 0x7FF0000, old.len(), new.len());
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].starts_with("1 changed region(s), 1 changed byte(s)"));
        assert_eq!(lines[1], "0x7FF0010  old: 00  new: ab");
    }

    #[test]
    fn dumpdiff_json_has_offset_address_and_full_hex() {
        let old = vec![0u8; 8];
        let new = vec![0xFFu8; 48];
        let diff = spectre_core::diff_dumps(&old, &new);
        let v = dumpdiff_to_json(&diff, 0x1000, ("a.bin", 8), ("b.bin", 48));
        assert_eq!(v["region_count"], 1);
        let r = &v["regions"][0];
        assert_eq!(r["offset"], 0);
        assert_eq!(r["address"], "0x1000");
        assert_eq!(r["len"], 48);
        // JSON is never truncated.
        assert_eq!(r["new"].as_str().unwrap(), hex_bytes(&new));
    }

    #[test]
    fn search_state_roundtrip_via_tempfile() {
        let dir = std::env::temp_dir().join(format!("spectre-state-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("state.json");
        let path_str = path.to_string_lossy().to_string();

        save_search_state(&path_str, &[0x1000, 0x7ff0000]).unwrap();
        let loaded = load_search_state(&path_str).unwrap();
        assert_eq!(loaded, vec![0x1000, 0x7ff0000]);
        std::fs::remove_dir_all(&dir).ok();
    }
}
